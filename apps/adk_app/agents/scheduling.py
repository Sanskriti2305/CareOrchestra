import asyncio
import datetime
import logging
import os
from typing import List, Dict

from ..tools.bigquery_tools.client import BigQueryClient
from ..tools.calendar_tools.scheduler import CalendarScheduler

logger = logging.getLogger(__name__)

# Global clients
_bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)
_calendar_scheduler = CalendarScheduler(use_mock=True)  # Block patient calendars


class SchedulingAgent:
    """
    Hospital API integration for critical patient scheduling.
    Realistic mock → Real hospital API when details provided.
    """

    async def get_available_slots(self, urgent: bool = False) -> List[Dict]:
        """
        Mock hospital API: /api/availability?urgent=true
        Returns dynamic slots for today/tomorrow.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        today = now.date()
        tomorrow = today + datetime.timedelta(days=1)

        # Realistic urgent slots (morning priority)
        slots = [
            {
                "id": "slot_1",
                "doctor": "Dr. Sarah Johnson (Cardiologist)",
                "time": now.replace(hour=9, minute=0, second=0, microsecond=0).isoformat(),
                "duration": 30,
                "location": "Emergency Clinic A"
            },
            {
                "id": "slot_2", 
                "doctor": "Dr. Michael Chen (Internal Medicine)",
                "time": now.replace(hour=10, minute=30, second=0, microsecond=0).isoformat(),
                "duration": 45,
                "location": "Urgent Care B"
            },
            {
                "id": "slot_3",
                "doctor": "Dr. Emily Rodriguez (ER Physician)",
                "time": tomorrow.replace(hour=8, minute=0).isoformat(),
                "duration": 30,
                "location": "Main ER"
            }
        ]
        
        logger.info(f"[Hospital API Mock] Returning {len(slots)} urgent slots")
        return slots

    async def book_slot(self, patient_id: str, slot_id: str, doctor_note: str = "") -> Dict:
        """
        Mock hospital API: /api/book → BigQuery + Calendar block.
        """
        slots = await self.get_available_slots()
        slot = next((s for s in slots if s["id"] == slot_id), None)
        
        if not slot:
            return {"status": "error", "error": "Invalid slot ID"}
        
        # 1. Log appointment to BigQuery
        appointment = {
    "appointment_id": f"apt_{patient_id}_{datetime.datetime.now().timestamp()}",
    "patient_id": patient_id,
    "provider_name": slot["doctor"],   # ✅ FIXED
    "scheduled_at": slot["time"],      # ✅ FIXED
    "location": slot["location"],
    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "completed": False
}
        
        success = await _bq_client.insert("appointments", [appointment])
        if not success:
            return {"status": "error", "error": "Failed to log appointment"}
        
        # 2. Block calendars
        calendar_event_id = await _calendar_scheduler.schedule_appointment(
            patient_name=patient_id,
            provider_name=slot["doctor"], 
            appointment_time=datetime.datetime.fromisoformat(slot["time"]),
            duration_minutes=slot["duration"],
            description=f"Critical patient {patient_id}: {doctor_note}"
        )
        
        logger.info(f"[Hospital API] Booked {patient_id} → {slot['doctor']} @ {slot['time']}")
        
        return {
            "status": "confirmed",
            "appointment": appointment,
            "calendar_event_id": calendar_event_id
        }
