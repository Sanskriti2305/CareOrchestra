import os
import logging
import concurrent.futures
import asyncio
from google import genai
from google.genai import types
from dotenv import load_dotenv
from ..tools.bigquery_tools.client import BigQueryClient
from .monitoring import MonitoringAgent
from .escalation import EscalationAgent
load_dotenv()
logger = logging.getLogger(__name__)


# Initialize once (global is fine in Cloud Run)
bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)


async def get_patient_profile(patient_id: str) -> dict:
    """
    Fetch patient profile from BigQuery
    """
    try:
        logger.info(f"Fetching patient profile for patient_id={patient_id}")

        query = f"""
        SELECT 
            first_name,
            last_name,
            chronic_conditions,
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
                "condition": "Unknown",
                "last_visit": "N/A",
                "target_bp": "N/A"
            }

        patient = results[0]

        full_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()

        logger.info(f"Patient found: {full_name}")

        return {
            "name": full_name or "Patient",
            "condition": patient.get("chronic_conditions", "Unknown"),
            "last_visit": str(patient.get("updated_at", "N/A")),
            "target_bp": "130/80"  # can be dynamic later
        }

    except Exception as e:
        logger.error(f"Error fetching patient: {str(e)}")
        return {
            "name": "Patient",
            "condition": "Unknown",
            "last_visit": "N/A",
            "target_bp": "N/A"
        }

def send_to_monitoring_agent(patient_id: str, summary: str) -> dict:
    """
    Sends the patient's collected symptoms and status to the Monitoring Agent.
    Call this once you have collected enough information (2-3 messages).
    Returns a clinical recommendation and an escalation flag.
    """
    monitor = MonitoringAgent()
    clinical_response = monitor.process_summary(patient_id, summary)

    escalation_needed = (
        "URGENT" in clinical_response
        or "escalat" in clinical_response.lower()
    )
    risk_level = "critical" if escalation_needed else "low"

    return {
        "clinical_response": clinical_response,
        "escalation_needed": escalation_needed,
        "risk_level": risk_level,
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

    logger.info(
        f"[Coordinator] Escalation triggered for patient=***{patient_id[-4:] if len(patient_id) >= 4 else patient_id} "
        f"risk={risk_level} status={result.get('escalation_status')}"
    )
    return result


SYSTEM_INSTRUCTION = """You are the Coordinator Agent for CareOrchestra, a chronic care system.

Your job:
1. Call get_patient_profile first to load the patient's details
2. Greet the patient warmly by name and ask how they are doing today
3. Ask ONE follow-up question at a time to understand:
   - Any symptoms they are experiencing
   - Their energy and mood
   - Whether they have taken their medications
4. After 2-3 exchanges call send_to_monitoring_agent with a clear summary
5. If send_to_monitoring_agent returns escalation_needed=True, immediately call
   escalate_patient with the patient_id, risk_level, and symptom summary
6. Relay the monitoring agent's response back in warm, simple language

Rules:
- One question per turn only
- Never diagnose or alarm unnecessarily
- Be warm, human, and concise"""


class CoordinatorAgent:
    def __init__(self):
        # new SDK — only one client, no GenerativeModel, no start_chat
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.tools = [get_patient_profile, send_to_monitoring_agent, escalate_patient]
        self.history: list[types.Content] = []   # we own the chat history

    async def coordinate(self, event: dict) -> dict:
        patient_id = event.get("patient_id")
        user_message = event.get("message")

        try:
            # append user turn
            self.history.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"[Patient ID: {patient_id}] {user_message}")]
                )
            )

            # single call — no start_chat, no send_message
            response = self.client.models.generate_content(
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
            self.history.append(
                types.Content(
                    role="model",
                    parts=[types.Part(text=response.text)]
                )
            )

            return {
                "status": "success",
                "agent": "Coordinator (Gemini 2.5 Flash)",
                "message_to_patient": response.text
            }

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Gemini Error: {error_details}")
            return {"status": "error", "message": str(e), "trace": error_details}