"""Medication Agent - Tracks medication adherence using Gemini with BigQuery-backed tools."""

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

async def get_patient_medications(patient_id: str) -> dict:
    """
    Fetch active medications for the patient from BigQuery.
    Returns the current medication list with dosage and frequency details.
    Always call this first to know what medications the patient should be taking.

    Args:
        patient_id: The patient's unique identifier.
    """
    try:
        logger.info(f"Fetching medications for patient_id=***{patient_id[-4:]}")

        query = f"""
        SELECT
            medication_id,
            medication_name,
            dosage,
            frequency,
            start_date,
            end_date
        FROM `{bq_client.project_id}.{bq_client.dataset_id}.medications`
        WHERE patient_id = @patient_id
          AND start_date <= CURRENT_TIMESTAMP()
          AND (end_date IS NULL OR end_date > CURRENT_TIMESTAMP())
        ORDER BY start_date DESC
        """

        results = await bq_client.query(query, {"patient_id": patient_id})

        if not results:
            logger.warning(f"No active medications for patient_id=***{patient_id[-4:]}")
            return {
                "patient_id": patient_id,
                "medications": [],
                "count": 0,
                "message": "No active medications found"
            }

        medications = [
            {
                "medication_id": str(row.get("medication_id", "")),
                "name": row.get("medication_name", "Unknown"),
                "dosage": row.get("dosage", "N/A"),
                "frequency": row.get("frequency", "N/A"),
                "start_date": str(row.get("start_date", "N/A")),
            }
            for row in results
        ]

        return {
            "patient_id": patient_id,
            "medications": medications,
            "count": len(medications)
        }

    except Exception as e:
        logger.error(f"Error fetching medications: {str(e)}")
        return {"status": "error", "message": str(e)}


async def get_adherence_summary(patient_id: str) -> dict:
    """
    Fetch recent medication adherence history from BigQuery (last 7 days).
    Call this to understand whether the patient has a history of missing doses
    before starting the check-in conversation.

    Args:
        patient_id: The patient's unique identifier.
    """
    try:
        query = f"""
        SELECT
            medication_name,
            taken,
            scheduled_time
        FROM `{bq_client.project_id}.{bq_client.dataset_id}.medication_logs`
        WHERE patient_id = @patient_id
          AND scheduled_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        ORDER BY scheduled_time DESC
        LIMIT 50
        """

        results = await bq_client.query(query, {"patient_id": patient_id})

        if not results:
            return {
                "patient_id": patient_id,
                "adherence_rate": None,
                "total_scheduled": 0,
                "total_taken": 0,
                "message": "No medication logs found in the last 7 days"
            }

        total = len(results)
        taken_count = sum(1 for r in results if r.get("taken"))
        adherence_rate = round((taken_count / total) * 100, 1) if total > 0 else None

        risk_level = "good"
        if adherence_rate is not None:
            if adherence_rate < 50:
                risk_level = "poor"
            elif adherence_rate < 80:
                risk_level = "fair"
            elif adherence_rate < 95:
                risk_level = "moderate"

        return {
            "patient_id": patient_id,
            "adherence_rate": adherence_rate,
            "total_scheduled": total,
            "total_taken": taken_count,
            "total_missed": total - taken_count,
            "risk_level": risk_level,
            "period": "7 days"
        }

    except Exception as e:
        logger.error(f"Error fetching adherence summary: {str(e)}")
        return {"status": "error", "message": str(e)}


async def log_medication_taken(
    patient_id: str,
    medication_id: str,
    medication_name: str,
    taken: bool,
    raw_response: str,
) -> dict:
    """
    Save a medication check-in record to BigQuery after confirming with the patient.
    Call this once the patient has confirmed whether or not they took a specific medication.

    Args:
        patient_id: The patient's unique identifier.
        medication_id: The ID of the medication being logged.
        medication_name: The human-readable name of the medication.
        taken: True if the patient confirmed taking the medication, False otherwise.
        raw_response: The patient's verbatim reply to be stored for audit purposes.
    """
    try:
        now = datetime.datetime.utcnow()

        row = {
            "patient_id": patient_id,
            "medication_id": medication_id,
            "medication_name": medication_name,
            "scheduled_time": now.isoformat(),
            "taken": taken,
            "actual_time": now.isoformat() if taken else None,
            "raw_response": raw_response,
            "follow_up_message": (
                "Great job! Keep it up."
                if taken
                else "Please take your medicines on time tomorrow."
            ),
            "reminder_sent": True,
            "created_at": now.isoformat(),
        }

        success = await bq_client.insert("medication_logs", [row])
        logger.info(
            f"[Medication Log] patient=***{patient_id[-4:]} med={medication_name} taken={taken}"
        )

        return {
            "status": "saved" if success else "insert_failed",
            "medication_record": row,
        }

    except Exception as e:
        logger.error(f"Error logging medication: {str(e)}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# System Instruction
# ---------------------------------------------------------------------------

MEDICATION_SYSTEM_INSTRUCTION = """You are the Medication Agent for CareOrchestra, a chronic care monitoring system.

Your job:
1. Call get_patient_medications first to load the patient's active medication list
2. Call get_adherence_summary to understand their recent adherence history
3. Ask the patient whether they have taken each of their medications today — one at a time
4. After the patient responds, call log_medication_taken to record their answer
5. Provide warm, supportive feedback based on their response:
   - If taken: Acknowledge positively and encourage continuation
   - If missed: Express understanding, remind about importance, and gently suggest taking it if safe
6. Flag any adherence concerns (e.g., multiple missed doses, adherence rate below 80%) clearly

Rules:
- Ask about one medication at a time
- Never shame the patient for missing doses
- Be warm, supportive, and non-judgmental
- Always log the patient's response before moving to the next medication
- If adherence rate is below 80%, explicitly note it as a clinical concern"""


# ---------------------------------------------------------------------------
# MedicationAgent Class
# ---------------------------------------------------------------------------

class MedicationAgent:
    """
    Manages medication reminders and adherence tracking using Gemini 2.5 Flash
    with BigQuery-backed tool functions.
    Follows the same pattern as CoordinatorAgent.
    """

    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.tools = [get_patient_medications, get_adherence_summary, log_medication_taken]
        self.history: list[types.Content] = []  # per-instance conversation history

    async def check_adherence(self, event: dict) -> dict:
        """
        Run a medication check-in conversation turn for the patient.

        Args:
            event: dict with 'patient_id' and 'message' keys.

        Returns:
            dict with 'status', 'agent', and 'message_to_patient' keys.
        """
        patient_id = event.get("patient_id")
        user_message = event.get("message")

        try:
            self.history.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"[Patient ID: {patient_id}] {user_message}")]
                )
            )

            response = await self.client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=self.history,
                config=types.GenerateContentConfig(
                    system_instruction=MEDICATION_SYSTEM_INSTRUCTION,
                    tools=self.tools,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=False
                    ),
                    temperature=0.5,
                ),
            )

            self.history.append(
                types.Content(
                    role="model",
                    parts=[types.Part(text=response.text)]
                )
            )

            return {
                "status": "success",
                "agent": "MedicationAgent (Gemini 2.5 Flash)",
                "message_to_patient": response.text
            }

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"MedicationAgent Error: {error_details}")
            return {"status": "error", "message": str(e), "trace": error_details}

    async def check_medication_adherence(self, patient_id: str) -> dict:
        """
        Programmatic adherence check (non-conversational).
        Used by other agents or services to get adherence status directly.

        Args:
            patient_id: The patient's unique identifier.
        """
        return await get_adherence_summary(patient_id)