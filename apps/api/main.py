# api/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from apps.adk_app.app import CareOrchestraApp

app = FastAPI(title="CareOrchestra API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the patient chat frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

orchestra = CareOrchestraApp()


class MessagePayload(BaseModel):
    message: str
    patient_id: str


@app.get("/main-adk")
async def handle_message(message: str, patient_id: str):
    try:
        payload = {
            "message": message,
            "patient_id": patient_id
        }

        result = await orchestra.process_event(payload)

        return {"status": "success", "response": result}

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": "An internal error occurred. Please try again."}


@app.post("/chat")
async def chat(payload: MessagePayload):
    """Patient-facing chat endpoint. Accepts JSON body with message and patient_id."""
    try:
        result = await orchestra.process_event({"message": payload.message, "patient_id": payload.patient_id})
        return {"status": "success", "response": result}
    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": "An internal error occurred. Please try again."}


@app.get("/vitals/{patient_id}")
async def analyze_vitals(patient_id: str):
    """
    Trigger a full Gemini-powered vitals analysis for the given patient.
    Returns a clinical assessment with findings and recommended actions.
    """
    try:
        vitals_agent = orchestra.agents.get("vitals")
        if not vitals_agent:
            return {"status": "error", "message": "VitalsAgent not initialized"}

        result = await vitals_agent.analyze_vitals(patient_id)
        return {"status": "success", "response": result}

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": "An internal error occurred. Please try again."}


@app.get("/vitals/{patient_id}/trend/{vital_type}")
async def check_vital_trend(patient_id: str, vital_type: str):
    """
    Check the trend for a specific vital sign over the last 7 days.
    vital_type must be one of: bp_systolic, bp_diastolic, heart_rate, glucose, spo2
    """
    try:
        vitals_agent = orchestra.agents.get("vitals")
        if not vitals_agent:
            return {"status": "error", "message": "VitalsAgent not initialized"}

        result = await vitals_agent.check_trend(patient_id, vital_type)
        return {"status": "success", "response": result}

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": "An internal error occurred. Please try again."}


@app.post("/medication/checkin")
async def medication_checkin(payload: MessagePayload):
    """
    Run a medication check-in conversation turn for the patient.
    The MedicationAgent will ask about medications, log responses to BigQuery,
    and provide supportive feedback.
    """
    try:
        medication_agent = orchestra.agents.get("medication")
        if not medication_agent:
            return {"status": "error", "message": "MedicationAgent not initialized"}

        event = {"patient_id": payload.patient_id, "message": payload.message}
        result = await medication_agent.check_adherence(event)
        return {"status": "success", "response": result}

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": "An internal error occurred. Please try again."}


@app.get("/medication/{patient_id}/adherence")
async def get_adherence(patient_id: str):
    """
    Get the medication adherence summary for the past 7 days (non-conversational).
    Returns adherence rate, total scheduled, total taken, and risk level.
    """
    try:
        medication_agent = orchestra.agents.get("medication")
        if not medication_agent:
            return {"status": "error", "message": "MedicationAgent not initialized"}

        result = await medication_agent.check_medication_adherence(patient_id)
        return {"status": "success", "response": result}

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": "An internal error occurred. Please try again."}

