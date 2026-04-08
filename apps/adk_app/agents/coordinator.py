import os
import logging
import datetime
import concurrent.futures
import asyncio
from google import genai
from google.genai import types
from dotenv import load_dotenv
from ..tools.bigquery_tools.client import BigQueryClient
from .monitoring import MonitoringAgent
from .vitals import VitalsAgent, get_patient_vitals
from .medication import MedicationAgent, get_adherence_summary
from .analysis import AnalysisAgent
from .escalation import EscalationAgent
from .Symptoms_agent import assess_symptoms

load_dotenv()
logger = logging.getLogger(__name__)


# Initialize once (global is fine in Cloud Run)
bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)



def _calculate_age(dob) -> int:
    """Return the current age in years from a date of birth.

    Accepts a ``datetime.date`` object or any value whose first 10 characters
    are a valid ISO-8601 date string (YYYY-MM-DD).  Returns 0 when the value
    is absent or cannot be parsed.
    """
    if not dob:
        return 0
    try:
        if not isinstance(dob, datetime.date):
            dob = datetime.date.fromisoformat(str(dob)[:10])
        today = datetime.date.today()
        # Subtract 1 when the birthday hasn't occurred yet this year
        birthday_passed = (today.month, today.day) >= (dob.month, dob.day)
        return today.year - dob.year - (0 if birthday_passed else 1)
    except Exception:
        return 0


async def get_patient_profile(patient_id: str) -> dict:
    """
    Fetch patient profile from BigQuery.
    Always call this first to load the patient's name and chronic conditions.

    Args:
        patient_id: The patient's unique identifier.
    """
    try:
        logger.info(f"Fetching patient profile for patient_id={patient_id}")

        query = f"""
        SELECT 
            first_name,
            last_name,
            chronic_conditions,
            date_of_birth,
            updated_at
        FROM `{bq_client.project_id}.{bq_client.dataset_id}.patients`
        WHERE patient_id = @patient_id
        LIMIT 1
        """

        results = await bq_client.query(
            query,
            {"patient_id": patient_id}
        )

        if not results:
            logger.warning(f"No patient found for patient_id={patient_id}")
            return {
                "name": "Patient",
                "age": 0,
                "condition": "Unknown",
                "last_visit": "N/A",
                "target_bp": "N/A"
            }

        patient = results[0]

        full_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()

        age = _calculate_age(patient.get("date_of_birth"))

        logger.info(f"Patient found: {full_name}, age={age}")

        return {
            "name": full_name or "Patient",
            "age": age,
            "condition": patient.get("chronic_conditions", "Unknown"),
            "last_visit": str(patient.get("updated_at", "N/A")),
            "target_bp": "130/80"  # can be dynamic later
        }

    except Exception as e:
        logger.error(f"Error fetching patient: {str(e)}")
        return {
            "name": "Patient",
            "age": 0,
            "condition": "Unknown",
            "last_visit": "N/A",
            "target_bp": "N/A"
        }


async def call_vitals_agent(patient_id: str) -> dict:
    """
    Run the Vitals Agent to obtain an objective clinical assessment of the
    patient's recent vital signs (blood pressure, heart rate, glucose, SpO2).
    Call this early in the conversation to understand the patient's clinical
    baseline before asking about symptoms.

    Args:
        patient_id: The patient's unique identifier.
    """
    agent = VitalsAgent()
    return await agent.analyze_vitals(patient_id)


async def call_medication_agent(patient_id: str) -> dict:
    """
    Retrieve the patient's medication adherence summary for the last 7 days.
    Call this to understand whether the patient has a history of missing doses
    before asking about medications in the conversation.

    Args:
        patient_id: The patient's unique identifier.
    """
    agent = MedicationAgent()
    return await agent.check_medication_adherence(patient_id)


async def call_analysis_agent(patient_id: str) -> dict:
    """
    Run the Analysis Agent to produce a composite risk score from the patient's
    raw vitals and medication adherence data.  Call this after call_vitals_agent
    and call_medication_agent to get a structured risk assessment before
    deciding whether to escalate.

    Args:
        patient_id: The patient's unique identifier.

    Returns:
        Dict with 'risk_level', 'composite_score', 'domain_scores', 'findings',
        'recommendations', 'reasoning', and 'escalate' keys.
    """
    vitals_raw = await get_patient_vitals(patient_id)
    adherence_raw = await get_adherence_summary(patient_id)

    # Convert vitals issues to the format AnalysisAgent expects
    _LEVEL_MAP = {
        "crisis": "critical",
        "critical": "critical",
        "severe_tachycardia": "critical",
        "severe_bradycardia": "critical",
        "severe_hyperglycemia": "critical",
        "severe_hypoglycemia": "critical",
        "high": "high",
        "warning": "warning",
        "tachycardia": "moderate",
        "bradycardia": "moderate",
        "low": "low",
    }
    _CODE_MAP = {
        "blood_pressure": "SBP_ELEVATED",
        "glucose": "GLUCOSE_HIGH",
        "spo2": "SPO2_LOW",
        "heart_rate": "HR_ELEVATED",
    }
    findings = []
    for issue in vitals_raw.get("issues", []):
        findings.append({
            "code": _CODE_MAP.get(issue.get("type", ""), issue.get("type", "VITAL_ABNORMAL").upper()),
            "description": f"{issue.get('type', 'vital')} abnormality: {issue.get('value', '')}",
            "severity": _LEVEL_MAP.get(issue.get("level", "low"), "low"),
            "value": None,
            "threshold": None,
        })

    vitals_data = {"findings": findings}

    # Convert adherence data to the format AnalysisAgent expects
    medication_data = {
        "adherence_score": adherence_raw.get("adherence_rate"),
        "findings": [],
        "interactions": [],
    }

    agent = AnalysisAgent()
    return await agent.analyze_patient_status(patient_id, vitals_data, medication_data, {})


async def send_to_monitoring_agent(patient_id: str, summary: str) -> dict:
    """
    Send the patient's collected symptoms and status to the Monitoring Agent.
    Call this once you have collected enough information (2-3 messages).
    Returns a clinical recommendation and an escalation flag.
    If the returned dict has escalation_needed=True, call escalate_patient next.

    Note: escalation_needed is False when the Monitoring Agent has already
    dispatched an escalation alert internally, to prevent duplicate notifications.

    Args:
        patient_id: The patient's unique identifier.
        summary: A clear natural-language summary of what the patient reported.
    """
    monitor = MonitoringAgent()
    result = await monitor.process_summary(patient_id, summary)

    risk_level = result.get("risk_level", "low")

    # MonitoringAgent escalates internally for high/critical cases.
    # Only set escalation_needed=True when it hasn't already done so, to
    # prevent a second alert being sent by the Coordinator.
    already_escalated = result.get("action") in ("escalated", "alerted")
    escalation_needed = risk_level in ("high", "critical") and not already_escalated

    return {
        **result,
        "escalation_needed": escalation_needed,
        "patient_id": patient_id,
    }


def escalate_patient(patient_id: str, risk_level: str, summary: str) -> dict:
    """
    Escalate a high-risk patient to the healthcare team.
    Call this immediately when send_to_monitoring_agent returns
    escalation_needed=True.

    Args:
        patient_id: Patient identifier.
        risk_level: Risk level string (e.g. ``"high"`` or ``"critical"``).
        summary: Plain-text summary of the patient's reported symptoms.

    Returns:
        Escalation confirmation dict.
    """
    agent = EscalationAgent()
    alert_summary = {"summary": summary, "source": "coordinator_agent"}

    async def _run() -> dict:
        return await agent.escalate_alert(patient_id, risk_level, alert_summary)

    try:
        # Run the coroutine safely regardless of whether we are already inside
        # a running event loop.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: asyncio.run(_run()))
                result = future.result(timeout=30)
        else:
            result = asyncio.run(_run())

    except Exception as exc:
        logger.error(f"[Coordinator] Escalation failed: {exc}")
        result = {"escalation_status": "error", "error": str(exc)}

    masked_id = patient_id[-4:] if len(patient_id) >= 4 else patient_id
    logger.info(
        f"[Coordinator] Escalation triggered for patient=***{masked_id} "
        f"risk={risk_level} status={result.get('escalation_status')}"
    )
    return result


def call_symptoms_agent(
    patient_id: str,
    raw_message: str,
    age: int,
    conditions: str,
    medications: str,
    vitals_flag: str = "normal",
) -> str:
    """
    Run the Symptoms Agent to perform a structured clinical assessment of what
    the patient just reported.  Call this after the patient has described their
    symptoms (1-2 messages), before calling send_to_monitoring_agent.

    Args:
        patient_id: The patient's unique identifier.
        raw_message: The patient's latest message describing their symptoms.
        age: Patient age in years — use the 'age' field returned by get_patient_profile.
        conditions: Comma-separated chronic conditions from get_patient_profile
                    (e.g. "hypertension,type2_diabetes").
        medications: Comma-separated current medication names, or "unknown" if not
                     available from call_medication_agent.
        vitals_flag: Severity flag derived from call_vitals_agent — pass "warning"
                     if vitals_agent reported issues, "critical" for critical issues,
                     or "normal" if no abnormalities were found.

    Returns:
        A clinical assessment string with risk score (0-100), severity level,
        escalation recommendation, and reason.  Include this in the summary you
        pass to send_to_monitoring_agent.
    """
    return assess_symptoms(
        raw_message=raw_message,
        patient_id=patient_id,
        age=age,
        conditions=conditions,
        medications=medications,
        vitals_flag=vitals_flag,
    )


SYSTEM_INSTRUCTION = """You are the Coordinator Agent for CareOrchestra, a chronic care system.

Your job:
1. Call get_patient_profile first to load the patient's name, age, and conditions
2. Call call_vitals_agent to retrieve the patient's current vital signs
3. Call call_medication_agent to check their recent medication adherence
4. Call call_analysis_agent to get a composite risk score combining vitals and medication data
5. Greet the patient warmly by name and ask how they are doing today
6. Ask ONE follow-up question at a time to understand:
   - Any symptoms they are experiencing
   - Their energy and mood
   - Whether they have taken their medications today
7. Once the patient has described any symptoms (after 1-2 symptom messages), call
   call_symptoms_agent with:
   - patient_id: the patient's ID
   - raw_message: the patient's symptom description
   - age: the 'age' value from get_patient_profile
   - conditions: the 'condition' value from get_patient_profile
   - medications: medication names if available, or "unknown"
   - vitals_flag: "warning" if call_vitals_agent reported any issues, "normal" otherwise
8. After call_symptoms_agent, call send_to_monitoring_agent with a clear summary that
   includes the patient's report, the objective vitals/adherence data, AND the
   symptoms assessment risk score and severity
9. If send_to_monitoring_agent returns escalation_needed=True, immediately call
   escalate_patient with the patient_id, risk_level, and symptom summary
10. Relay the monitoring agent's response back in warm, simple language

Rules:
- One question per turn only
- Never diagnose or alarm unnecessarily
- Be warm, human, and concise"""


class CoordinatorAgent:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.tools = [
            get_patient_profile,
            call_vitals_agent,
            call_medication_agent,
            call_analysis_agent,
            call_symptoms_agent,
            send_to_monitoring_agent,
            escalate_patient,
        ]
        self.history: list[types.Content] = []   # we own the chat history

    async def coordinate(self, event: dict) -> dict:
        patient_id = event.get("patient_id")
        user_message = event.get("message")

        try:
            if self.client is None:
                profile = await get_patient_profile(patient_id)
                assessment = assess_symptoms(
                    user_message,
                    patient_id,
                    profile.get("age", 0),
                    profile.get("condition", "Unknown"),
                    "",
                )
                return {
                    "status": "success",
                    "agent": "Coordinator (mock)",
                    "message_to_patient": assessment,
                }

            # append user turn
            self.history.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"[Patient ID: {patient_id}] {user_message}")]
                )
            )

            # async call — supports async tool functions
            response = await self.client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=self.history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=self.tools,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=False               # Gemini calls tools automatically
                    ),
                    temperature=0.7,
                ),
            )

            # append model turn to keep conversation going
            response_text = response.text or ""
            self.history.append(
                types.Content(
                    role="model",
                    parts=[types.Part(text=response_text)]
                )
            )

            return {
                "status": "success",
                "agent": "Coordinator (Gemini 2.5 Flash)",
                "message_to_patient": response_text
            }

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Gemini Error: {error_details}")
            return {"status": "error", "message": str(e), "trace": error_details}
