"""Monitoring Agent - Watches for patient events and triggers analysis."""

import logging
from .vitals import get_patient_vitals
from .escalation import EscalationAgent

logger = logging.getLogger(__name__)

# Keywords in the coordinator summary that indicate an emergency
_EMERGENCY_PHRASES = [
    "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "shortness of breath", "unconscious", "passed out", "seizure",
    "severe pain", "vomiting blood", "heart racing", "palpitations",
]

# Vitals issue levels that require immediate escalation
_ESCALATION_LEVELS = {"crisis", "critical", "severe_tachycardia", "severe_bradycardia",
                      "severe_hyperglycemia", "severe_hypoglycemia"}

# Vitals issue levels that represent a high-risk (non-emergency) concern
_HIGH_RISK_LEVELS = {"high", "warning", "tachycardia", "bradycardia"}


class MonitoringAgent:
    """
    Evaluates patient status by combining the coordinator's conversation summary
    with objective vitals data from BigQuery.  Routes high-risk cases to the
    EscalationAgent so a clinician can be notified.
    """

    async def process_summary(self, patient_id: str, summary: str) -> dict:
        """
        Assess the patient's overall status and decide whether escalation is needed.

        Steps:
        1. Check the coordinator summary for emergency keywords.
        2. Fetch the patient's latest vitals from BigQuery.
        3. Identify any critical or high-risk vitals issues.
        4. Escalate to EscalationAgent if the situation is urgent.
        5. Return a structured response for the Coordinator to relay to the patient.

        Args:
            patient_id: The patient's unique identifier.
            summary: Natural-language summary produced by the Coordinator.

        Returns:
            dict with 'risk_level', 'action', and 'message' keys.
        """
        summary_lower = summary.lower()

        # --- Step 1: keyword scan of the conversation summary ---
        emergency_keyword_hit = any(phrase in summary_lower for phrase in _EMERGENCY_PHRASES)

        # --- Step 2: fetch objective vitals ---
        vitals_data = await get_patient_vitals(patient_id)
        issues = vitals_data.get("issues", [])

        # --- Step 3: classify vitals severity ---
        critical_issues = [i for i in issues if i.get("level") in _ESCALATION_LEVELS]
        high_risk_issues = [i for i in issues if i.get("level") in _HIGH_RISK_LEVELS]

        # --- Step 4: determine overall risk level and act ---
        if emergency_keyword_hit or critical_issues:
            risk_level = "critical"
            issue_descriptions = "; ".join(
                f"{i['type']} ({i['level']}): {i['value']}" for i in critical_issues
            )
            alert_summary = {
                "coordinator_summary": summary,
                "critical_vitals": issue_descriptions or "emergency keyword detected in report",
                "all_vitals": vitals_data.get("latest", {}),
            }

            escalation_agent = EscalationAgent()
            escalation_result = await escalation_agent.escalate_alert(
                patient_id=patient_id,
                risk_level="critical",
                alert_summary=alert_summary,
            )

            logger.warning(
                f"[Monitoring] CRITICAL escalation triggered for patient=***{patient_id[-4:]} "
                f"escalation_status={escalation_result.get('escalation_status')}"
            )

            return {
                "risk_level": "critical",
                "action": "escalated",
                "escalation": escalation_result,
                "message": (
                    "I've flagged this as urgent and alerted your care team immediately. "
                    "Please seek emergency care or call 911 if you feel in danger."
                ),
            }

        if high_risk_issues:
            risk_level = "high"
            issue_descriptions = "; ".join(
                f"{i['type']} ({i['level']}): {i['value']}" for i in high_risk_issues
            )
            alert_summary = {
                "coordinator_summary": summary,
                "high_risk_vitals": issue_descriptions,
                "all_vitals": vitals_data.get("latest", {}),
            }

            escalation_agent = EscalationAgent()
            escalation_result = await escalation_agent.escalate_alert(
                patient_id=patient_id,
                risk_level="high",
                alert_summary=alert_summary,
            )

            logger.info(
                f"[Monitoring] HIGH risk alert for patient=***{patient_id[-4:]} "
                f"issues={issue_descriptions}"
            )

            return {
                "risk_level": "high",
                "action": "alerted",
                "escalation": escalation_result,
                "message": (
                    "Some of your recent readings need attention. "
                    "I've notified your care team and they will follow up with you soon."
                ),
            }

        # --- Step 5: stable / routine ---
        logger.info(
            f"[Monitoring] Stable assessment for patient=***{patient_id[-4:]}"
        )
        return {
            "risk_level": "low",
            "action": "logged",
            "message": (
                "Everything looks stable based on your report. "
                "I've logged this for your doctor to review at your next check-in."
            ),
        }