"""Escalation Agent - Handles high-risk scenarios and alerts doctors."""

import os
import logging
import datetime
from ..tools.bigquery_tools.client import BigQueryClient
from ..tools.gmail_tools.alert_sender import GmailSender

logger = logging.getLogger(__name__)

_bq_client = BigQueryClient(
    project_id=os.getenv("GCP_PROJECT_ID"),
    dataset_id="careorchestra"
)


class EscalationAgent:
    """
    Manages critical alerts:
    - Identifies high-risk situations requiring immediate attention
    - Formats alerts for clinician consumption
    - Routes alerts to appropriate healthcare providers via email
    - Logs escalation events to BigQuery for audit purposes
    """

    def __init__(self):
        sender_email = os.getenv("SENDER_EMAIL", "alerts@careorchestra.app")
        use_mock = os.getenv("GMAIL_MOCK", "true").lower() != "false"
        self._gmail = GmailSender(sender_email=sender_email, use_mock=use_mock)

    async def escalate_alert(
        self,
        patient_id: str,
        risk_level: str,
        alert_summary: dict
    ) -> dict:
        """
        Escalate a patient alert to the healthcare provider.

        Fetches the patient's escalation contacts, sends an alert email,
        and logs the escalation event to BigQuery.

        Args:
            patient_id: Patient identifier.
            risk_level: Risk level — 'high' or 'critical'.
            alert_summary: Dict summarising the findings (vitals, summary text, etc.).

        Returns:
            dict with 'escalation_status', 'contacts_notified', and 'logged' keys.
        """
        contacts = await self.get_escalation_contacts(patient_id)
        if not contacts:
            default_email = os.getenv("DEFAULT_DOCTOR_EMAIL", "")
            if default_email:
                contacts = [{"email": default_email, "name": "Care Team"}]

        # Build a readable alert body
        alert_content = self._format_alert(patient_id, risk_level, alert_summary)

        notified = []
        for contact in contacts:
            email = contact.get("email", "")
            name = contact.get("name", "Care Team")
            if not email:
                continue
            success = await self._gmail.send_alert(
                recipient=email,
                patient_name=f"Patient {patient_id}",
                alert_content=alert_content,
            )
            if success:
                notified.append(email)
                logger.info(
                    f"[Escalation] Alert sent to {name} <{email}> "
                    f"for patient=***{patient_id[-4:]} risk={risk_level}"
                )

        # Log escalation event to BigQuery
        logged = await self._log_escalation(patient_id, risk_level, alert_content, notified)

        return {
            "escalation_status": "sent" if notified else "no_contacts",
            "contacts_notified": notified,
            "logged": logged,
        }

    async def send_alert_to_doctor(
        self,
        doctor_email: str,
        patient_name: str,
        alert_content: str
    ) -> bool:
        """
        Send an alert email to a specific doctor.

        Args:
            doctor_email: Doctor's email address.
            patient_name: Patient name for the email subject.
            alert_content: Formatted alert message body.

        Returns:
            True if the email was sent successfully, False otherwise.
        """
        return await self._gmail.send_alert(
            recipient=doctor_email,
            patient_name=patient_name,
            alert_content=alert_content,
        )

    async def get_escalation_contacts(self, patient_id: str) -> list:
        """
        Retrieve escalation contacts for the patient from BigQuery.

        Queries the ``escalation_contacts`` table first; falls back to the
        patient's primary doctor field in the ``patients`` table if that
        table does not exist or has no rows.

        Args:
            patient_id: Patient identifier.

        Returns:
            List of dicts with 'email' and 'name' keys.
        """
        try:
            query = f"""
            SELECT contact_email AS email, contact_name AS name
            FROM `{_bq_client.project_id}.{_bq_client.dataset_id}.escalation_contacts`
            WHERE patient_id = @patient_id
            ORDER BY priority ASC
            LIMIT 5
            """
            results = await _bq_client.query(query, {"patient_id": patient_id})
            if results:
                return [{"email": r.get("email", ""), "name": r.get("name", "Care Team")}
                        for r in results if r.get("email")]
        except Exception:
            # Table may not exist yet — fall through to patient record lookup
            pass

        try:
            query = f"""
            SELECT doctor_email AS email, CONCAT(doctor_first_name, ' ', doctor_last_name) AS name
            FROM `{_bq_client.project_id}.{_bq_client.dataset_id}.patients`
            WHERE patient_id = @patient_id
            LIMIT 1
            """
            results = await _bq_client.query(query, {"patient_id": patient_id})
            if results and results[0].get("email"):
                return [{"email": results[0]["email"], "name": results[0].get("name", "Doctor")}]
        except Exception:
            pass

        return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _format_alert(self, patient_id: str, risk_level: str, alert_summary: dict) -> str:
        """Build a human-readable alert body for the email."""
        lines = [
            f"CareOrchestra Clinical Alert",
            f"=============================",
            f"Patient ID : {patient_id}",
            f"Risk Level : {risk_level.upper()}",
            f"Timestamp  : {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            "",
        ]

        if "coordinator_summary" in alert_summary:
            lines += ["Patient Report:", alert_summary["coordinator_summary"], ""]

        for key in ("critical_vitals", "high_risk_vitals"):
            if key in alert_summary:
                label = "Critical Vitals" if "critical" in key else "High-Risk Vitals"
                lines += [f"{label}:", alert_summary[key], ""]

        if "all_vitals" in alert_summary:
            vitals = alert_summary["all_vitals"]
            lines.append("Latest Readings:")
            for vtype, val in vitals.items():
                lines.append(f"  {vtype}: {val}")
            lines.append("")

        lines.append("Please review and take appropriate action.")
        return "\n".join(lines)

    async def _log_escalation(
        self,
        patient_id: str,
        risk_level: str,
        alert_content: str,
        notified: list,
    ) -> bool:
        """Persist the escalation event to BigQuery for audit purposes."""
        try:
            row = {
                "patient_id": patient_id,
                "risk_level": risk_level,
                "alert_content": alert_content[:1000],  # cap to avoid oversized rows
                "contacts_notified": ", ".join(notified),
                "created_at": datetime.datetime.utcnow().isoformat(),
            }
            return await _bq_client.insert("escalation_logs", [row])
        except Exception as e:
            logger.error(f"Failed to log escalation: {e}")
            return False
