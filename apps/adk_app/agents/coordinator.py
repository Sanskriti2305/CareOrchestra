import os
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv
from .monitoring import MonitoringAgent

load_dotenv()
logger = logging.getLogger(__name__)


def get_patient_profile(patient_id: str) -> dict:
    """
    Retrieves the patient's condition, name, and care plan.
    Always call this first to greet the patient personally.
    """
    return {
        "name": "John Doe",
        "condition": "Hypertension",
        "last_visit": "2024-01-10",
        "target_bp": "130/80"
    }


def send_to_monitoring_agent(patient_id: str, summary: str) -> dict:
    """
    Sends the patient's collected symptoms and status to the Monitoring Agent.
    Call this once you have collected enough information (2-3 messages).
    Returns a clinical recommendation or an escalation flag.
    """
    monitor = MonitoringAgent()
    return monitor.process_summary(patient_id, summary)


SYSTEM_INSTRUCTION = """You are the Coordinator Agent for CareOrchestra, a chronic care system.

Your job:
1. Call get_patient_profile first to load the patient's details
2. Greet the patient warmly by name and ask how they are doing today
3. Ask ONE follow-up question at a time to understand:
   - Any symptoms they are experiencing
   - Their energy and mood
   - Whether they have taken their medications
4. After 2-3 exchanges call send_to_monitoring_agent with a clear summary
5. Relay the monitoring agent's response back in warm, simple language

Rules:
- One question per turn only
- Never diagnose or alarm unnecessarily
- Be warm, human, and concise"""


class CoordinatorAgent:
    def __init__(self):
        # new SDK — only one client, no GenerativeModel, no start_chat
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.tools = [get_patient_profile, send_to_monitoring_agent]
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
                "agent": "Coordinator (Gemini 2.0 Flash)",
                "message_to_patient": response.text
            }

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Gemini Error: {error_details}")
            return {"status": "error", "message": str(e), "trace": error_details}