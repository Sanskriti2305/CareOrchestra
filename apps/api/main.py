# api/main.py
from fastapi import FastAPI
import sys
from apps.adk_app.agents.coordinator import CoordinatorAgent

app = FastAPI()

orchestra = CoordinatorAgent()

@app.get("/main-adk")
async def handle_message(message: str, patient_id: str):
    try:
        payload = {
            "message": message, 
            "patient_id": patient_id  
        }
        
        # 4. Run the logic
        result = await orchestra.coordinate(payload)
        
        return {"status": "success", "response": result}
        
    except Exception as e:
        # This will print the EXACT error in your terminal so you can see it
        import traceback
        print(f"CRITICAL ERROR: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}