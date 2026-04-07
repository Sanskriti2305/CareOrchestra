"""Reporting Agent - Generates doctor and nurse summaries."""

import os
import logging
import datetime
from ..tools.bigquery_tools.client import BigQueryClient

logger = logging.getLogger(__name__)

_bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)


class ReportingAgent:
    """
    Creates clinical summaries:
    - Generates concise patient update summaries for doctors
    - Creates nurse handoff reports
    - Formats vitals trends for clinical review
    - Produces medication reconciliation reports
    - Generates periodic patient summaries for scheduling
    """

    def __init__(self):
        pass

    async def generate_doctor_summary(
        self,
        patient_id: str,
        analysis: dict,
        time_period: str = "7d"
    ) -> str:
        """
        Generate a doctor-ready patient summary.

        Pulls the patient profile, latest vitals, and medication adherence from
        BigQuery and formats them into a concise clinical narrative.

        Args:
            patient_id: Patient identifier.
            analysis: Optional pre-computed analysis dict to enrich the report.
            time_period: Time period to summarise (e.g. '7d', '30d').

        Returns:
            Formatted summary string for the clinician.
        """
        days = self._period_to_days(time_period)

        profile = await self._fetch_patient_profile(patient_id)
        vitals = await self._fetch_latest_vitals(patient_id, days)
        adherence = await self._fetch_adherence(patient_id, days)
        alerts = await self._fetch_recent_alerts(patient_id, days)

        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"DOCTOR SUMMARY — {now}",
            f"{'=' * 50}",
            f"Patient   : {profile.get('name', patient_id)}",
            f"Conditions: {profile.get('condition', 'N/A')}",
            f"Period    : Last {days} day(s)",
            "",
            "VITALS",
            "------",
        ]

        if vitals:
            for vtype, info in vitals.items():
                lines.append(f"  {vtype}: {info.get('value')} {info.get('unit', '')}")
        else:
            lines.append("  No recent vitals recorded.")

        lines += ["", "ALERTS", "------"]
        if alerts:
            for a in alerts:
                lines.append(
                    f"  [{a.get('severity', '?').upper()}] {a.get('title', '')} — {a.get('created_at', '')}"
                )
        else:
            lines.append("  No alerts in this period.")

        lines += ["", "MEDICATION ADHERENCE", "--------------------"]
        rate = adherence.get("adherence_rate")
        if rate is not None:
            lines.append(
                f"  Adherence rate : {rate}%  ({adherence.get('risk_level', 'N/A')} risk)"
            )
            lines.append(
                f"  Doses taken    : {adherence.get('total_taken', 0)} / "
                f"{adherence.get('total_scheduled', 0)}"
            )
        else:
            lines.append("  No medication logs found.")

        if analysis:
            risk = analysis.get("risk_level") or analysis.get("status")
            if risk:
                lines += ["", f"ANALYSIS RISK LEVEL: {risk.upper()}"]
            recs = analysis.get("recommendations", [])
            if recs:
                lines += ["", "RECOMMENDATIONS", "---------------"]
                for r in recs:
                    lines.append(f"  • {r}")

        return "\n".join(lines)

    async def generate_nurse_handoff(self, patient_id: str) -> str:
        """
        Generate a nurse handoff report covering current status, pending actions,
        and any open alerts.

        Args:
            patient_id: Patient identifier.

        Returns:
            Formatted handoff report string.
        """
        profile = await self._fetch_patient_profile(patient_id)
        vitals = await self._fetch_latest_vitals(patient_id, days=1)
        alerts = await self._fetch_recent_alerts(patient_id, days=1)
        adherence = await self._fetch_adherence(patient_id, days=7)

        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"NURSE HANDOFF REPORT — {now}",
            f"{'=' * 50}",
            f"Patient   : {profile.get('name', patient_id)}",
            f"Conditions: {profile.get('condition', 'N/A')}",
            "",
            "CURRENT VITALS (last 24 h)",
            "--------------------------",
        ]

        if vitals:
            for vtype, info in vitals.items():
                lines.append(f"  {vtype}: {info.get('value')} {info.get('unit', '')}")
        else:
            lines.append("  No vitals recorded in the last 24 hours.")

        lines += ["", "OPEN ALERTS", "-----------"]
        if alerts:
            for a in alerts:
                ack = "✓" if a.get("acknowledged") else "✗"
                lines.append(
                    f"  [{ack}] [{a.get('severity', '?').upper()}] {a.get('title', '')} — {a.get('description', '')}"
                )
        else:
            lines.append("  No alerts in the last 24 hours.")

        lines += ["", "MEDICATION (last 7 days)", "-----------------------"]
        rate = adherence.get("adherence_rate")
        if rate is not None:
            lines.append(f"  Adherence: {rate}%")
            missed = adherence.get("total_missed", 0)
            if missed:
                lines.append(f"  ⚠ {missed} missed dose(s) — follow up with patient.")
        else:
            lines.append("  No medication log data.")

        lines += ["", "PENDING ACTIONS", "---------------"]
        unacked = [a for a in alerts if not a.get("acknowledged")]
        if unacked:
            lines.append(f"  • Review and acknowledge {len(unacked)} open alert(s).")
        if rate is not None and rate < 80:
            lines.append("  • Discuss medication adherence with patient.")
        if not vitals:
            lines.append("  • Record today's vital signs.")
        if not unacked and (rate is None or rate >= 80) and vitals:
            lines.append("  • No immediate actions required.")

        return "\n".join(lines)

    async def generate_vitals_report(self, patient_id: str, days: int = 30) -> dict:
        """
        Generate a vitals trend report for the specified number of past days.

        Args:
            patient_id: Patient identifier.
            days: Number of days to include (default 30).

        Returns:
            Dict with 'patient_id', 'period_days', 'generated_at', and per-vital
            trend summaries (min, max, average, trend direction).
        """
        try:
            query = f"""
            SELECT vital_type, value, measured_at
            FROM `{_bq_client.project_id}.{_bq_client.dataset_id}.vitals`
            WHERE patient_id = @patient_id
              AND measured_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)
            ORDER BY vital_type, measured_at ASC
            """
            rows = await _bq_client.query(query, {"patient_id": patient_id})

            trends: dict = {}
            for row in rows:
                vtype = row.get("vital_type")
                val = row.get("value")
                if vtype is None or val is None:
                    continue
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    continue
                if vtype not in trends:
                    trends[vtype] = []
                trends[vtype].append(val)

            report: dict = {}
            for vtype, values in trends.items():
                if not values:
                    continue
                avg = round(sum(values) / len(values), 1)
                direction = (
                    "increasing" if values[-1] > values[0]
                    else "decreasing" if values[-1] < values[0]
                    else "stable"
                )
                report[vtype] = {
                    "readings": len(values),
                    "min": min(values),
                    "max": max(values),
                    "average": avg,
                    "trend": direction,
                    "latest": values[-1],
                }

            return {
                "patient_id": patient_id,
                "period_days": days,
                "generated_at": datetime.datetime.utcnow().isoformat(),
                "vitals": report,
            }

        except Exception as e:
            logger.error(f"Error generating vitals report for patient {patient_id}: {e}")
            return {
                "patient_id": patient_id,
                "period_days": days,
                "generated_at": datetime.datetime.utcnow().isoformat(),
                "vitals": {},
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _period_to_days(time_period: str) -> int:
        """Convert a period string like '7d' or '30d' to an integer number of days."""
        try:
            return int(time_period.rstrip("d").rstrip("D"))
        except (ValueError, AttributeError):
            return 7

    async def _fetch_patient_profile(self, patient_id: str) -> dict:
        try:
            query = f"""
            SELECT first_name, last_name, chronic_conditions
            FROM `{_bq_client.project_id}.{_bq_client.dataset_id}.patients`
            WHERE patient_id = @patient_id
            LIMIT 1
            """
            results = await _bq_client.query(query, {"patient_id": patient_id})
            if results:
                r = results[0]
                name = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
                return {"name": name or patient_id, "condition": r.get("chronic_conditions", "N/A")}
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
        return {"name": patient_id, "condition": "N/A"}

    async def _fetch_latest_vitals(self, patient_id: str, days: int) -> dict:
        """Return the most recent reading per vital type within the last N days."""
        try:
            query = f"""
            SELECT vital_type, value, unit, measured_at
            FROM `{_bq_client.project_id}.{_bq_client.dataset_id}.vitals`
            WHERE patient_id = @patient_id
              AND measured_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)
            ORDER BY measured_at DESC
            LIMIT 50
            """
            results = await _bq_client.query(query, {"patient_id": patient_id})
            latest: dict = {}
            for row in results:
                vtype = row.get("vital_type")
                if vtype and vtype not in latest:
                    latest[vtype] = {
                        "value": row.get("value"),
                        "unit": row.get("unit", ""),
                        "measured_at": str(row.get("measured_at", "")),
                    }
            return latest
        except Exception as e:
            logger.error(f"Error fetching vitals: {e}")
            return {}

    async def _fetch_adherence(self, patient_id: str, days: int) -> dict:
        """Return adherence summary for the last N days."""
        try:
            query = f"""
            SELECT taken
            FROM `{_bq_client.project_id}.{_bq_client.dataset_id}.medication_logs`
            WHERE patient_id = @patient_id
              AND scheduled_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)
            LIMIT 100
            """
            results = await _bq_client.query(query, {"patient_id": patient_id})
            if not results:
                return {"adherence_rate": None}
            total = len(results)
            taken = sum(1 for r in results if r.get("taken"))
            rate = round((taken / total) * 100, 1)
            risk = "good" if rate >= 95 else "moderate" if rate >= 80 else "fair" if rate >= 50 else "poor"
            return {
                "adherence_rate": rate,
                "total_scheduled": total,
                "total_taken": taken,
                "total_missed": total - taken,
                "risk_level": risk,
            }
        except Exception as e:
            logger.error(f"Error fetching adherence: {e}")
            return {"adherence_rate": None}

    async def _fetch_recent_alerts(self, patient_id: str, days: int) -> list:
        """Return open alerts from the last N days."""
        try:
            query = f"""
            SELECT alert_type, severity, title, description, created_at, acknowledged
            FROM `{_bq_client.project_id}.{_bq_client.dataset_id}.alerts`
            WHERE patient_id = @patient_id
              AND created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(days)} DAY)
            ORDER BY created_at DESC
            LIMIT 20
            """
            results = await _bq_client.query(query, {"patient_id": patient_id})
            return [
                {
                    "alert_type": r.get("alert_type"),
                    "severity": r.get("severity"),
                    "title": r.get("title"),
                    "description": r.get("description"),
                    "created_at": str(r.get("created_at", "")),
                    "acknowledged": r.get("acknowledged", False),
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Error fetching alerts: {e}")
            return []
