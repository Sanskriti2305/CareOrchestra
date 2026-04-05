import os
import json
import logging
import datetime
from pathlib import Path
import google.cloud.logging
from dotenv import load_dotenv

# --- Setup Logging and Environment ---
try:
    cloud_logging_client = google.cloud.logging.Client()
    cloud_logging_client.setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)
    logging.info("Cloud logging not available, using standard logging.")

load_dotenv()

# ---------------------------------------------------------------------------
# Dummy Patient Database (Kept exactly as per your details)
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
# Tool Functions for Gemini Coordinator
# ---------------------------------------------------------------------------

def fetch_patient_from_db(session_id: str = "session_001") -> dict:
    """
    Simulates a database lookup for the current session's patient.
    Always call this first to get the patient's name and medication details.
    """
    patient = DUMMY_PATIENT_DB.get(session_id, DEFAULT_PATIENT)
    logging.info(f"[DB Lookup] Resolved patient: {json.dumps(patient)}")
    return patient


def save_medication_response(
    patient_id: str,
    patient_name: str,
    medication: str,
    medication_taken: bool,
    raw_response: str,
) -> dict:
    """
    Builds and saves a structured medication check-in record.
    Call this after the patient confirms whether they took their medication.
    
    Args:
        patient_id: The ID of the patient.
        patient_name: The name of the patient.
        medication: The medication name being tracked.
        medication_taken: True if patient confirmed taking medication.
        raw_response: The patient's verbatim reply text.
    """
    now = datetime.datetime.utcnow()

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

    # In a real app, this would be an INSERT INTO BigQuery or Postgres
    logging.info(f"[Medication Record Saved] {json.dumps(medication_record)}")

    return {
        "status":            "success",
        "medication_record": medication_record,
    }


class MedicationAgent:
    """
    Main class-based wrapper for the Medication Agent logic.
    """
    def __init__(self):
        self.agent_name = "MedicationAgent"

    async def check_medication_adherence(self, patient_id: str) -> dict:
        """Helper method for internal app logic."""
        # For now, returns a simple status
        return {"status": "active", "patient_id": patient_id}