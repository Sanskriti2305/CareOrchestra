import os
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv
from ..tools.bigquery_tools.client import BigQueryClient
from .monitoring import MonitoringAgent
from .vitals import VitalsAgent
from .medication import MedicationAgent

load_dotenv()
logger = logging.getLogger(__name__)


# Initialize once (global is fine in Cloud Run)
bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)


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


async def send_to_monitoring_agent(patient_id: str, summary: str) -> dict:
    """
    Send the patient's collected symptoms and status to the Monitoring Agent.
    Call this once you have collected enough information (2-3 messages).
    Returns a clinical recommendation or an escalation flag.

    Args:
        patient_id: The patient's unique identifier.
        summary: A clear natural-language summary of what the patient reported.
    """
    monitor = MonitoringAgent()
    return await monitor.process_summary(patient_id, summary)


SYSTEM_INSTRUCTION = """You are the Coordinator Agent for CareOrchestra, a chronic care system.

Your job:
1. Call get_patient_profile first to load the patient's name and conditions
2. Call call_vitals_agent to retrieve the patient's current vital signs
3. Call call_medication_agent to check their recent medication adherence
4. Greet the patient warmly by name and ask how they are doing today
5. Ask ONE follow-up question at a time to understand:
   - Any symptoms they are experiencing
   - Their energy and mood
   - Whether they have taken their medications today
6. After 2-3 exchanges call send_to_monitoring_agent with a clear summary that
   includes both what the patient reported AND the objective vitals/adherence data
7. Relay the monitoring agent's response back in warm, simple language

Rules:
- One question per turn only
- Never diagnose or alarm unnecessarily
- Be warm, human, and concise"""


class CoordinatorAgent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.tools = [
            get_patient_profile,
            call_vitals_agent,
            call_medication_agent,
            send_to_monitoring_agent,
        ]
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