import logging
import os
from typing import Optional, List, Dict, Any
from google.cloud import bigquery


logger = logging.getLogger(__name__)


class BigQueryClient:
    """Client for BigQuery data operations."""

    def __init__(self, project_id: str, dataset_id: str):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.mock_mode = os.getenv("USE_MOCK_DATA", "true").lower() == "true"
        self.client = None

        if not self.mock_mode:
            try:
                self.client = bigquery.Client(project=self.project_id)
            except Exception as exc:
                self.mock_mode = True
                logger.warning(
                    "BigQuery client unavailable, falling back to mock mode: %s",
                    exc,
                )
        else:
            logger.info("BigQuery client running in mock mode.")

    def _table_ref(self, table: str) -> str:
        """Return full table reference"""
        return f"{self.project_id}.{self.dataset_id}.{table}"

    async def query(
        self,
        sql: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict]:
        """Execute SQL query"""

        if self.client is None:
            return []

        job_config = bigquery.QueryJobConfig()

        # Optional parameterized query
        if parameters:
            job_config.query_parameters = [
                bigquery.ScalarQueryParameter(k, "STRING", v)
                for k, v in parameters.items()
            ]

        query_job = self.client.query(sql, job_config=job_config)
        results = query_job.result()

        return [dict(row.items()) for row in results]

    async def insert(self, table: str, rows: List[Dict]) -> bool:
        """Insert rows into BigQuery"""

        if self.client is None:
            return True

        table_ref = self._table_ref(table)

        errors = self.client.insert_rows_json(table_ref, rows)

        if errors:
            print("Insert errors:", errors)
            return False

        return True

    async def update(
        self,
        table: str,
        where_clause: str,
        updates: Dict
    ) -> int:
        """Update rows using SQL"""

        if self.client is None:
            return 0

        table_ref = self._table_ref(table)

        # Build SET clause
        set_clause = ", ".join(
            [f"{key} = @{key}" for key in updates.keys()]
        )

        sql = f"""
        UPDATE `{table_ref}`
        SET {set_clause}
        WHERE {where_clause}
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(k, "STRING", v)
                for k, v in updates.items()
            ]
        )

        query_job = self.client.query(sql, job_config=job_config)
        result = query_job.result()

        return result.num_dml_affected_rows