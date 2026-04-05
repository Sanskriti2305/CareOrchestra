"""Monitoring Agent - Watches for patient events and triggers analysis."""


class MonitoringAgent:
    """
    Collects, validates, and routes the summarized data from the Coordinator.
    """
    def process_summary(self, patient_id: str, summary: str):
        # 1. Validate the summary (Is it clinical? Is it high risk?)
        # 2. Logic: Should this go to an emergency alert or just a daily log?
        
        # Example logic:
        if "chest pain" in summary.lower() or "can't breathe" in summary.lower():
            return "URGENT: Escalating to emergency nursing team immediately."
        
        return "Everything looks stable based on your report. I've logged this for your doctor to review."