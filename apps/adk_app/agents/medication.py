import os
import json
import logging
import datetime
from pathlib import Path
import google.cloud.logging
from dotenv import load_dotenv

from google.adk import Agent
from google.adk.tools.tool_context import ToolContext

# --- Setup Logging and Environment ---

cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

model_name = os.getenv("MODEL")

# ---------------------------------------------------------------------------
# Dummy Patient Database
# In production, replace with a real DB query (Cloud SQL, Firestore, etc.)
# ---------------------------------------------------------------------------

DUMMY_PATIENT_DB = {
    "session_001": {
        "patient_id": "PAT-1001",
        "name":       "Rajesh Kumar",
        "age":        58,
        "medication": "Metformin 500mg",
    },
    "session_002": {
        "patient_id": "PAT-1002",
        "name":       "Sunita Sharma",
        "age":        45,
        "medication": "Amlodipine 5mg",
    },
    "session_003": {
        "patient_id": "PAT-1003",
        "name":       "Amit Verma",
        "age":        62,
        "medication": "Atorvastatin 10mg",
    },
}

DEFAULT_PATIENT = {
    "patient_id": "PAT-0000",
    "name":       "Guest Patient",
    "age":        None,
    "medication": "prescribed medication",
}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def fetch_patient_from_db(tool_context: ToolContext) -> dict:
    """
    Simulates a DB lookup for the current session's patient.

    Reads 'session_id' from state (defaults to 'session_001' for dev/test).
    Writes patient_id, patient_name, and medication into state for use
    by save_medication_response in the same agent turn.

    In production: replace dict lookup with Cloud SQL / Firestore query.
    """
    session_id = tool_context.state.get("session_id", "session_001")
    patient    = DUMMY_PATIENT_DB.get(session_id, DEFAULT_PATIENT)

    tool_context.state["patient_id"]   = patient["patient_id"]
    tool_context.state["patient_name"] = patient["name"]
    tool_context.state["medication"]   = patient["medication"]

    logging.info(f"[DB Lookup] Resolved patient: {json.dumps(patient)}")

    return {
        "status":       "success",
        "patient_id":   patient["patient_id"],
        "patient_name": patient["name"],
        "age":          patient["age"],
        "medication":   patient["medication"],
    }


def save_medication_response(
    tool_context: ToolContext,
    medication_taken: bool,
    raw_response: str,
) -> dict:
    """
    Builds a structured medication check-in record and persists it to state.

    Patient metadata (patient_id, name, medication) is read from state,
    written there earlier in the same session by fetch_patient_from_db.

    Args:
        tool_context:     ADK ToolContext.
        medication_taken: True if patient confirmed taking medication.
        raw_response:     The patient's verbatim reply.

    Returns:
        dict with 'status' and the fully structured 'medication_record'.
    """
    now = datetime.datetime.utcnow()

    patient_id   = tool_context.state.get("patient_id",   "UNKNOWN")
    patient_name = tool_context.state.get("patient_name", "UNKNOWN")
    medication   = tool_context.state.get("medication",   "UNKNOWN")

    medication_record = {
        "patient_id":          patient_id,
        "patient_name":        patient_name,
        "medication":          medication,
        "date":                now.strftime("%Y-%m-%d"),
        "time":                now.strftime("%H:%M:%S"),
        "timezone":            "UTC",
        "medication_response": "yes" if medication_taken else "no",
        "raw_response":        raw_response,
        "reminder_sent":       True,
        "follow_up_message": (
            "Great job! Keep it up."
            if medication_taken
            else "Please take your medicines on time tomorrow."
        ),
    }

    log: list = tool_context.state.get("medication_log", [])
    log.append(medication_record)
    tool_context.state["medication_log"]    = log
    tool_context.state["medication_record"] = medication_record

    logging.info(f"[Medication Record Saved] {json.dumps(medication_record)}")

    return {
        "status":            "success",
        "medication_record": medication_record,
    }




root_agent = Agent(
    name="medication_root_agent",
    model=model_name,
    description="Medication reminder agent that greets the patient, asks about medication, logs the response, and gives feedback.",
    instruction="""
    You are a warm and caring medication reminder assistant.

    ── TURN 1 (first message from the patient) ──────────────────────────────
    When the conversation starts:

    1. Call 'fetch_patient_from_db' to get the patient's details.
    2. Greet the patient warmly by name. Example:
       "Hello Rajesh! 👋 I'm your medication reminder assistant. I'm here
        to help you stay on track with your Metformin 500mg."
    3. Ask exactly ONE question and stop:
       "Have you taken your [medication name] today?"

    ── TURN 2 (patient replies yes or no) ───────────────────────────────────
    When the patient answers:

    1. Read their reply from the conversation. Classify it:
       YES → yes, yeah, yup, yep, done, took it, had it, sure, already, etc.
       NO  → no, nope, not yet, forgot, haven't, didn't, skip, etc.

    2. Call 'save_medication_response' with:
           medication_taken → True for YES, False for NO
           raw_response     → the patient's exact reply word-for-word

    3. Reply to the patient:
       If YES → "Great! 🎉 We've made an entry for today. Keep it up —
                 consistency is the key to good health! 💊✅"
       If NO  → "No worries! We've noted today's entry. Please make sure to
                 take your medicines on time tomorrow. Your health matters! 💊"

    4. Output the medication_record from the tool as a formatted JSON block:
       ```json
       { <medication_record here> }
       ```

    ── RULES ────────────────────────────────────────────────────────────────
    - Never ask for the patient's ID — the system resolves it automatically.
    - Never answer the medication question on the patient's behalf.
    - Never call save_medication_response on Turn 1.
    - After Turn 2 is complete, the conversation is done. Do not prompt
      for more input or ask follow-up questions.
    - Always be warm, non-judgmental, and encouraging.
    """,
    tools=[fetch_patient_from_db, save_medication_response],
)