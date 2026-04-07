"""Medication service - Manages medication data operations backed by BigQuery."""

import os
import logging
import datetime
from ..tools.bigquery_tools.client import BigQueryClient

logger = logging.getLogger(__name__)

bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)


class MedicationService:
    """Service for medication data operations."""

    async def get_active_medications(self, patient_id: str) -> list:
        """
        Get active medications for patient.

        Args:
            patient_id: Patient identifier

        Returns:
            List of active medications
        """
        try:
            query = f"""
            SELECT medication_id, medication_name, dosage, frequency, start_date, end_date
            FROM `{bq_client.project_id}.{bq_client.dataset_id}.medications`
            WHERE patient_id = @patient_id
              AND start_date <= CURRENT_TIMESTAMP()
              AND (end_date IS NULL OR end_date > CURRENT_TIMESTAMP())
            ORDER BY start_date DESC
            """
            return await bq_client.query(query, {"patient_id": patient_id})
        except Exception as e:
            logger.error(f"get_active_medications error: {e}")
            return []

    async def get_medication_schedule(self, patient_id: str) -> dict:
        """
        Get medication schedule for patient, annotated with today's taken status.

        Args:
            patient_id: Patient identifier

        Returns:
            Schedule dict with medications and their taken-today status
        """
        try:
            medications = await self.get_active_medications(patient_id)
            recent_logs = await self._get_todays_logs(patient_id)
            taken_ids = {str(log.get("medication_id")) for log in recent_logs if log.get("taken")}

            schedule = [
                {
                    "medication_id": str(med.get("medication_id", "")),
                    "name": med.get("medication_name", "Unknown"),
                    "dosage": med.get("dosage", "N/A"),
                    "frequency": med.get("frequency", "N/A"),
                    "taken_today": str(med.get("medication_id", "")) in taken_ids,
                }
                for med in medications
            ]

            return {"patient_id": patient_id, "schedule": schedule}
        except Exception as e:
            logger.error(f"get_medication_schedule error: {e}")
            return {}

    async def log_dose(self, patient_id: str, medication_id: str, taken_at: str = None) -> bool:
        """
        Log a medication dose as taken.

        Args:
            patient_id: Patient identifier
            medication_id: Medication identifier
            taken_at: ISO timestamp when dose was taken (defaults to now)

        Returns:
            True if insert succeeded, False otherwise
        """
        try:
            now = datetime.datetime.utcnow().isoformat()
            row = {
                "patient_id": patient_id,
                "medication_id": medication_id,
                "scheduled_time": now,
                "taken": True,
                "actual_time": taken_at or now,
                "created_at": now,
            }
            return await bq_client.insert("medication_logs", [row])
        except Exception as e:
            logger.error(f"log_dose error: {e}")
            return False

    async def get_missed_doses(self, patient_id: str, days: int = 7) -> list:
        """
        Get missed medication doses within the specified window.

        Args:
            patient_id: Patient identifier
            days: Number of days to check

        Returns:
            List of missed dose records
        """
        try:
            safe_days = max(1, min(int(days), 365))  # clamp to 1-365 to prevent injection
            query = f"""
            SELECT medication_id, medication_name, scheduled_time, taken
            FROM `{bq_client.project_id}.{bq_client.dataset_id}.medication_logs`
            WHERE patient_id = @patient_id
              AND scheduled_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {safe_days} DAY)
              AND taken = FALSE
            ORDER BY scheduled_time DESC
            """
            return await bq_client.query(query, {"patient_id": patient_id})
        except Exception as e:
            logger.error(f"get_missed_doses error: {e}")
            return []

    async def _get_todays_logs(self, patient_id: str) -> list:
        """Fetch medication logs recorded today."""
        try:
            query = f"""
            SELECT medication_id, taken
            FROM `{bq_client.project_id}.{bq_client.dataset_id}.medication_logs`
            WHERE patient_id = @patient_id
              AND DATE(scheduled_time) = CURRENT_DATE()
            """
            return await bq_client.query(query, {"patient_id": patient_id})
        except Exception as e:
            logger.error(f"_get_todays_logs error: {e}")
            return []
