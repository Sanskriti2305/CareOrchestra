"""Vitals service - Manages vitals data operations backed by BigQuery."""

import os
import logging
import datetime
from ..tools.bigquery_tools.client import BigQueryClient

logger = logging.getLogger(__name__)

bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)


class VitalsService:
    """Service for vitals data operations."""

    async def get_recent_vitals(self, patient_id: str, limit: int = 10) -> list:
        """
        Get recent vital readings for patient.

        Args:
            patient_id: Patient identifier
            limit: Number of readings to retrieve

        Returns:
            List of recent vital readings
        """
        try:
            safe_limit = max(1, min(int(limit), 100))  # clamp to 1-100 to prevent injection
            query = f"""
            SELECT vital_type, value, unit, measured_at
            FROM `{bq_client.project_id}.{bq_client.dataset_id}.vitals`
            WHERE patient_id = @patient_id
            ORDER BY measured_at DESC
            LIMIT {safe_limit}
            """
            return await bq_client.query(query, {"patient_id": patient_id})
        except Exception as e:
            logger.error(f"get_recent_vitals error: {e}")
            return []

    async def get_vitals_by_type(self, patient_id: str, vital_type: str, days: int = 30) -> list:
        """
        Get vitals of specific type over a time period.

        Args:
            patient_id: Patient identifier
            vital_type: Type of vital (bp_systolic, heart_rate, glucose, spo2, etc.)
            days: Number of days to retrieve

        Returns:
            List of readings in chronological order
        """
        try:
            safe_days = max(1, min(int(days), 365))  # clamp to 1-365 to prevent injection
            query = f"""
            SELECT value, unit, measured_at
            FROM `{bq_client.project_id}.{bq_client.dataset_id}.vitals`
            WHERE patient_id = @patient_id
              AND vital_type = @vital_type
              AND measured_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {safe_days} DAY)
            ORDER BY measured_at ASC
            """
            return await bq_client.query(
                query,
                {"patient_id": patient_id, "vital_type": vital_type}
            )
        except Exception as e:
            logger.error(f"get_vitals_by_type error: {e}")
            return []

    async def record_vital(self, patient_id: str, vital_data: dict) -> bool:
        """
        Record a new vital reading.

        Args:
            patient_id: Patient identifier
            vital_data: dict with keys 'vital_type', 'value', 'unit', and optionally 'measured_at'

        Returns:
            True if insert succeeded, False otherwise
        """
        try:
            row = {
                "patient_id": patient_id,
                "vital_type": vital_data["vital_type"],
                "value": vital_data["value"],
                "unit": vital_data.get("unit", ""),
                "measured_at": vital_data.get(
                    "measured_at",
                    datetime.datetime.utcnow().isoformat()
                ),
            }
            return await bq_client.insert("vitals", [row])
        except Exception as e:
            logger.error(f"record_vital error: {e}")
            return False
