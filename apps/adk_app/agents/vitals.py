"""Vitals Agent - Analyzes vital signs using Gemini with BigQuery-backed tools."""

import os
import logging
import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv
from ..tools.bigquery_tools.client import BigQueryClient

load_dotenv()
logger = logging.getLogger(__name__)

# Initialize once at module level (same pattern as CoordinatorAgent)
bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)


# ---------------------------------------------------------------------------
# Tool Functions — called automatically by Gemini during generate_content
# ---------------------------------------------------------------------------

async def get_patient_vitals(patient_id: str) -> dict:
    """
    Fetch recent vital signs from BigQuery for the given patient.
    Returns the latest readings for BP, heart rate, glucose, and SpO2,
    along with any rule-based issues detected.
    Always call this first to understand the patient's current vital status.

    Args:
        patient_id: The patient's unique identifier.
    """
    try:
        logger.info(f"Fetching vitals for patient_id=***{patient_id[-4:]}")

        query = f"""
        SELECT
            vital_type,
            value,
            unit,
            measured_at
        FROM `{bq_client.project_id}.{bq_client.dataset_id}.vitals`
        WHERE patient_id = @patient_id
          AND measured_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        ORDER BY measured_at DESC
        LIMIT 20
        """

        results = await bq_client.query(query, {"patient_id": patient_id})

        if not results:
            logger.warning(f"No vitals found for patient_id=***{patient_id[-4:]}")
            return {
                "status": "no_data",
                "patient_id": patient_id,
                "message": "No recent vitals available"
            }

        # Keep only the most recent reading per vital type
        latest_by_type = {}
        for row in results:
            vtype = row.get("vital_type")
            if vtype not in latest_by_type:
                latest_by_type[vtype] = {
                    "value": row.get("value"),
                    "unit": row.get("unit"),
                    "measured_at": str(row.get("measured_at"))
                }

        bp_systolic = latest_by_type.get("bp_systolic", {}).get("value")
        bp_diastolic = latest_by_type.get("bp_diastolic", {}).get("value")
        heart_rate = latest_by_type.get("heart_rate", {}).get("value")
        glucose = latest_by_type.get("glucose", {}).get("value")
        spo2 = latest_by_type.get("spo2", {}).get("value")

        # Rule-based issue detection using VitalsRulesEngine thresholds
        issues = []
        if bp_systolic and bp_diastolic:
            if bp_systolic >= 180 or bp_diastolic >= 120:
                issues.append({"type": "blood_pressure", "level": "crisis",
                                "value": f"{bp_systolic}/{bp_diastolic} mmHg"})
            elif bp_systolic >= 140 or bp_diastolic >= 90:
                issues.append({"type": "blood_pressure", "level": "high",
                                "value": f"{bp_systolic}/{bp_diastolic} mmHg"})
        if glucose is not None:
            if glucose >= 400:
                issues.append({"type": "glucose", "level": "severe_hyperglycemia",
                                "value": f"{glucose} mg/dL"})
            elif glucose >= 200:
                issues.append({"type": "glucose", "level": "high",
                                "value": f"{glucose} mg/dL"})
            elif glucose < 54:
                issues.append({"type": "glucose", "level": "severe_hypoglycemia",
                                "value": f"{glucose} mg/dL"})
            elif glucose < 70:
                issues.append({"type": "glucose", "level": "low",
                                "value": f"{glucose} mg/dL"})
        if spo2 is not None:
            if spo2 < 85:
                issues.append({"type": "spo2", "level": "critical",
                                "value": f"{spo2}%"})
            elif spo2 < 90:
                issues.append({"type": "spo2", "level": "warning",
                                "value": f"{spo2}%"})
        if heart_rate is not None:
            if heart_rate > 120:
                issues.append({"type": "heart_rate", "level": "severe_tachycardia",
                                "value": f"{heart_rate} bpm"})
            elif heart_rate > 100:
                issues.append({"type": "heart_rate", "level": "tachycardia",
                                "value": f"{heart_rate} bpm"})
            elif heart_rate < 40:
                issues.append({"type": "heart_rate", "level": "severe_bradycardia",
                                "value": f"{heart_rate} bpm"})
            elif heart_rate < 60:
                issues.append({"type": "heart_rate", "level": "bradycardia",
                                "value": f"{heart_rate} bpm"})

        return {
            "status": "alert" if issues else "normal",
            "patient_id": patient_id,
            "latest": {
                "bp": f"{bp_systolic}/{bp_diastolic} mmHg" if bp_systolic and bp_diastolic else "N/A",
                "heart_rate": f"{heart_rate} bpm" if heart_rate is not None else "N/A",
                "glucose": f"{glucose} mg/dL" if glucose is not None else "N/A",
                "spo2": f"{spo2}%" if spo2 is not None else "N/A",
            },
            "issues": issues,
        }

    except Exception as e:
        logger.error(f"Error fetching vitals: {str(e)}")
        return {"status": "error", "message": str(e)}


async def get_vitals_trend(patient_id: str, vital_type: str) -> dict:
    """
    Fetch trend data for a specific vital sign over the last 7 days.
    Use this after get_patient_vitals to provide deeper context on a concerning value.

    Args:
        patient_id: The patient's unique identifier.
        vital_type: One of 'bp_systolic', 'bp_diastolic', 'heart_rate', 'glucose', 'spo2'.
    """
    try:
        query = f"""
        SELECT value, measured_at
        FROM `{bq_client.project_id}.{bq_client.dataset_id}.vitals`
        WHERE patient_id = @patient_id
          AND vital_type = @vital_type
          AND measured_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        ORDER BY measured_at ASC
        LIMIT 10
        """

        results = await bq_client.query(
            query,
            {"patient_id": patient_id, "vital_type": vital_type}
        )

        if not results:
            return {"vital_type": vital_type, "trend": "no_data", "risk": "unknown"}

        values = [float(r["value"]) for r in results]
        trend = _calculate_trend(values)

        # Risk direction depends on whether higher or lower is worse
        risk = "normal"
        rising_bad = vital_type in ("bp_systolic", "bp_diastolic", "glucose", "heart_rate")
        falling_bad = vital_type == "spo2"

        if trend == "increasing" and rising_bad:
            risk = "warning"
        elif trend == "decreasing" and falling_bad:
            risk = "warning"
        elif trend == "decreasing" and rising_bad:
            risk = "improving"

        return {
            "vital_type": vital_type,
            "trend": trend,
            "risk": risk,
            "readings_count": len(values),
            "first_value": values[0],
            "latest_value": values[-1],
        }

    except Exception as e:
        logger.error(f"Error checking trend: {str(e)}")
        return {"vital_type": vital_type, "trend": "error", "risk": "unknown", "message": str(e)}


async def save_vitals_alert(
    patient_id: str,
    alert_type: str,
    severity: str,
    title: str,
    description: str,
) -> dict:
    """
    Save a vitals alert to BigQuery when an abnormal value is detected.
    Call this whenever you identify a concerning vital sign that needs clinical attention.

    Args:
        patient_id: The patient's unique identifier.
        alert_type: Category of alert (e.g. 'blood_pressure', 'glucose', 'spo2', 'heart_rate').
        severity: Severity level — one of 'low', 'moderate', 'high', 'critical'.
        title: Short descriptive title for the alert.
        description: Detailed description of the finding and recommended action.
    """
    try:
        row = {
            "patient_id": patient_id,
            "alert_type": alert_type,
            "severity": severity,
            "title": title,
            "description": description,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "acknowledged": False,
        }
        success = await bq_client.insert("alerts", [row])
        logger.info(
            f"[Vitals Alert] patient=***{patient_id[-4:]} type={alert_type} severity={severity}"
        )
        return {"status": "saved" if success else "insert_failed", "alert": row}

    except Exception as e:
        logger.error(f"Error saving vitals alert: {str(e)}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Shared helper (module-level, not exposed as a Gemini tool)
# ---------------------------------------------------------------------------

def _calculate_trend(values: list) -> str:
    """Calculate trend direction from an ordered list of values."""
    if len(values) < 2:
        return "insufficient_data"
    if values[-1] > values[0]:
        return "increasing"
    elif values[-1] < values[0]:
        return "decreasing"
    return "stable"


# ---------------------------------------------------------------------------
# System Instruction
# ---------------------------------------------------------------------------

VITALS_SYSTEM_INSTRUCTION = """You are the Vitals Agent for CareOrchestra, a chronic care monitoring system.

Your job:
1. Call get_patient_vitals first to load the patient's recent vital sign readings
2. Analyze the values using these clinical thresholds:
   - Blood Pressure: Normal <120/80, Elevated 120-129/80, Stage 1 HT 130-139/80-89,
     Stage 2 HT 140+/90+, Crisis 180+/120+
   - Heart Rate: Normal 60-100 bpm, Tachycardia >100, Severe >120,
     Bradycardia <60, Severe <40
   - Blood Glucose: Normal fasting <100 mg/dL, Pre-diabetic 100-125,
     Diabetic concern >200, Severe >400, Hypo <70, Critical <54
   - SpO2: Normal >=95%, Warning <90%, Critical <85%
3. For any abnormal finding, call get_vitals_trend to understand whether it is worsening
4. For any high or critical severity finding, call save_vitals_alert to log it
5. Return a structured clinical assessment covering:
   - Overall status (normal / alert / critical)
   - Each finding with severity level
   - Trend context where available
   - Recommended actions

Rules:
- Be objective and clinical in your assessment
- Always escalate values that require immediate attention
- Provide clear severity classification for each finding"""


# ---------------------------------------------------------------------------
# VitalsAgent Class
# ---------------------------------------------------------------------------

class VitalsAgent:
    """
    Analyzes vital signs using Gemini 2.5 Flash with BigQuery-backed tool functions.
    Follows the same pattern as CoordinatorAgent.
    """

    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.tools = [get_patient_vitals, get_vitals_trend, save_vitals_alert]

    async def analyze_vitals(self, patient_id: str) -> dict:
        """
        Analyze patient vitals by calling Gemini with tool-backed BigQuery data.

        Args:
            patient_id: The patient's unique identifier.

        Returns:
            dict with 'status', 'agent', 'patient_id', and 'assessment' keys.
        """
        try:
            prompt = (
                f"[Patient ID: {patient_id}] "
                "Please assess this patient's vital signs and identify any concerning patterns."
            )

            response = await self.client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=prompt)]
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=VITALS_SYSTEM_INSTRUCTION,
                    tools=self.tools,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=False
                    ),
                    temperature=0.2,
                ),
            )

            return {
                "status": "success",
                "agent": "VitalsAgent (Gemini 2.5 Flash)",
                "patient_id": patient_id,
                "assessment": response.text
            }

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"VitalsAgent Error: {error_details}")
            return {"status": "error", "message": str(e), "trace": error_details}

    async def check_trend(self, patient_id: str, vital_type: str) -> dict:
        """
        Check the trend for a specific vital sign directly via BigQuery.
        Lightweight helper used by other agents without a full Gemini call.

        Args:
            patient_id: The patient's unique identifier.
            vital_type: One of 'bp_systolic', 'bp_diastolic', 'heart_rate', 'glucose', 'spo2'.
        """
        return await get_vitals_trend(patient_id, vital_type)