"""Analysis Agent - Assesses patient risk from vitals, medications, and history."""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Optional


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class FindingSeverity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    WARNING = "warning"
    ALERT = "alert"
    HIGH = "high"
    CRITICAL = "critical"


class Finding:
    """A single clinical finding."""

    def __init__(
        self,
        domain: str,
        code: str,
        description: str,
        severity: str,
        value: Optional[float] = None,
        threshold: Optional[float] = None,
    ):
        self.domain = domain
        self.code = code
        self.description = description
        self.severity = severity
        self.value = value
        self.threshold = threshold

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "code": self.code,
            "description": self.description,
            "severity": self.severity,
            "value": self.value,
            "threshold": self.threshold,
        }


# Points added to a domain score per finding, keyed by severity label
_SEVERITY_SCORE: dict[str, float] = {
    "critical": 50.0,
    "alert": 30.0,
    "high": 20.0,
    "warning": 30.0,
    "moderate": 10.0,
    "low": 5.0,
}

# Composite score thresholds that map to each risk level
_RISK_THRESHOLDS = {
    RiskLevel.CRITICAL: 60.0,
    RiskLevel.HIGH: 40.0,
    RiskLevel.MODERATE: 10.0,
}

# Well-known chronic conditions that contribute to history risk score
_KNOWN_CONDITIONS = {
    "diabetes",
    "heart_disease",
    "hypertension",
    "copd",
    "renal_failure",
    "heart_failure",
}


class AnalysisAgent:
    """
    Analyzes aggregated patient data from vitals, medication, and history
    sources to produce a composite risk score and clinical recommendations.
    """

    async def analyze_patient_status(
        self,
        patient_id: str,
        vitals_data: dict,
        medication_data: dict,
        event: dict,
    ) -> dict:
        """
        Analyze overall patient status and produce a risk assessment.

        Args:
            patient_id: Patient identifier.
            vitals_data: Output from VitalsAgent — contains a ``findings`` list
                or a flat vitals dict (e.g. ``{"heart_rate": 130}``).
            medication_data: Output from MedicationAgent — may contain
                ``findings``, ``adherence_score``, and ``interactions``.
            event: Event dict; optionally contains a ``patient_history`` key.

        Returns:
            Assessment dict with keys: patient_id, assessed_at, risk_level,
            composite_score, domain_scores, findings, recommendations,
            reasoning, escalate.
        """
        patient_history: dict = (
            event.get("patient_history", {}) if isinstance(event, dict) else {}
        )

        vitals_score, vitals_findings = self._score_vitals(vitals_data)
        medication_score, medication_findings = self._score_medications(medication_data)
        history_score, history_findings = self._score_history(patient_history)

        domain_scores = {
            "vitals": round(vitals_score, 1),
            "medication": round(medication_score, 1),
            "history": round(history_score, 1),
        }

        composite_score = round(
            min(
                vitals_score * 0.5 + medication_score * 0.3 + history_score * 0.2,
                100.0,
            ),
            1,
        )

        all_findings = vitals_findings + medication_findings + history_findings

        has_critical_finding = any(
            f.get("severity") == FindingSeverity.CRITICAL.value
            for f in all_findings
        )

        if has_critical_finding or composite_score >= _RISK_THRESHOLDS[RiskLevel.CRITICAL]:
            risk_level = RiskLevel.CRITICAL
        elif composite_score >= _RISK_THRESHOLDS[RiskLevel.HIGH]:
            risk_level = RiskLevel.HIGH
        elif composite_score >= _RISK_THRESHOLDS[RiskLevel.MODERATE]:
            risk_level = RiskLevel.MODERATE
        else:
            risk_level = RiskLevel.LOW

        escalate = risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

        recommendations = self._generate_recommendations(
            risk_level, all_findings, medication_data
        )
        reasoning = self._build_reasoning(
            patient_id, composite_score, domain_scores, risk_level, all_findings
        )

        return {
            "patient_id": patient_id,
            "assessed_at": datetime.datetime.utcnow().isoformat(),
            "risk_level": risk_level.value,
            "composite_score": composite_score,
            "domain_scores": domain_scores,
            "findings": all_findings,
            "recommendations": recommendations,
            "reasoning": reasoning,
            "escalate": escalate,
        }

    async def assess_risk_level(
        self,
        vitals_data: dict,
        medication_data: dict,
        patient_history: dict,
    ) -> str:
        """
        Lightweight risk-level check without a full analysis payload.

        Returns:
            Risk level string: ``"low"``, ``"moderate"``, ``"high"``, or
            ``"critical"``.
        """
        result = await self.analyze_patient_status(
            "_assess",
            vitals_data,
            medication_data,
            {"patient_history": patient_history},
        )
        return result["risk_level"]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _score_vitals(self, vitals_data: dict) -> tuple[float, list]:
        raw_findings = vitals_data.get("findings", [])
        if not raw_findings:
            raw_findings = self._parse_flat_vitals(vitals_data)

        findings: list[dict] = []
        score = 0.0

        for f in raw_findings:
            severity = str(f.get("severity", "low")).lower()
            score += _SEVERITY_SCORE.get(severity, 0.0)
            findings.append(
                {
                    "domain": "vitals",
                    "code": f.get("code", "VITAL_ABNORMAL"),
                    "description": f.get("description", ""),
                    "severity": severity,
                    "value": f.get("value"),
                    "threshold": f.get("threshold"),
                }
            )

        return min(score, 100.0), findings

    def _score_medications(self, medication_data: dict) -> tuple[float, list]:
        findings: list[dict] = []
        score = 0.0

        adherence = medication_data.get("adherence_score")
        if adherence is not None:
            if adherence < 50:
                score += 30.0
                findings.append(
                    {
                        "domain": "medication",
                        "code": "ADHERENCE_POOR",
                        "description": f"Poor medication adherence: {adherence}%",
                        "severity": "high",
                    }
                )
            elif adherence < 80:
                score += 15.0
                findings.append(
                    {
                        "domain": "medication",
                        "code": "ADHERENCE_FAIR",
                        "description": f"Below-target medication adherence: {adherence}%",
                        "severity": "moderate",
                    }
                )

        for f in medication_data.get("findings", []):
            severity = str(f.get("severity", "low")).lower()
            score += _SEVERITY_SCORE.get(severity, 0.0) * 0.5
            findings.append(
                {
                    "domain": "medication",
                    "code": f.get("code", "MED_FINDING"),
                    "description": f.get("description", ""),
                    "severity": severity,
                }
            )

        for interaction in medication_data.get("interactions", []):
            sev = str(interaction.get("severity", "low")).lower()
            score += _SEVERITY_SCORE.get(sev, 0.0)
            drugs = ", ".join(interaction.get("drugs", []))
            findings.append(
                {
                    "domain": "medication",
                    "code": "DRUG_INTERACTION",
                    "description": interaction.get(
                        "description", f"Drug interaction: {drugs}"
                    ),
                    "severity": sev,
                }
            )

        return min(score, 100.0), findings

    def _score_history(self, patient_history: dict) -> tuple[float, list]:
        if not patient_history:
            return 0.0, []

        findings: list[dict] = []
        score = 0.0

        if patient_history.get("previous_cardiac_event"):
            score += 20.0
            findings.append(
                {
                    "domain": "history",
                    "code": "CARDIAC_HISTORY",
                    "description": "Previous cardiac event on record",
                    "severity": "moderate",
                }
            )

        age = patient_history.get("age", 0)
        if age >= 75:
            score += 15.0
            findings.append(
                {
                    "domain": "history",
                    "code": "AGE_HIGH_RISK",
                    "description": f"Advanced age: {age} years",
                    "severity": "moderate",
                }
            )
        elif age >= 65:
            score += 10.0
            findings.append(
                {
                    "domain": "history",
                    "code": "AGE_ELEVATED_RISK",
                    "description": f"Age-related risk: {age} years",
                    "severity": "low",
                }
            )

        for condition in patient_history.get("conditions", []):
            if condition.lower() in _KNOWN_CONDITIONS:
                score += 5.0
                findings.append(
                    {
                        "domain": "history",
                        "code": f"CONDITION_{condition.upper()}",
                        "description": f"Chronic condition: {condition}",
                        "severity": "low",
                    }
                )

        return min(score, 100.0), findings

    @staticmethod
    def _parse_flat_vitals(vitals_data: dict) -> list:
        """Convert a flat vitals dict into a list of finding dicts."""
        findings: list[dict] = []

        hr = (
            vitals_data["heart_rate"] if vitals_data.get("heart_rate") is not None
            else vitals_data.get("hr")
        )
        spo2 = (
            vitals_data["spo2"] if vitals_data.get("spo2") is not None
            else vitals_data.get("oxygen_saturation")
        )
        sbp = next(
            (vitals_data[k] for k in ("sbp", "systolic", "bp_systolic") if vitals_data.get(k) is not None),
            None,
        )
        glucose = (
            vitals_data["glucose"] if vitals_data.get("glucose") is not None
            else vitals_data.get("blood_glucose")
        )

        if hr is not None:
            if hr > 150:
                findings.append(
                    {
                        "code": "HR_ELEVATED",
                        "description": f"Severe tachycardia: {hr} bpm",
                        "severity": "critical",
                        "value": hr,
                        "threshold": 100,
                    }
                )
            elif hr > 130:
                findings.append(
                    {
                        "code": "HR_ELEVATED",
                        "description": f"Tachycardia: {hr} bpm",
                        "severity": "alert",
                        "value": hr,
                        "threshold": 100,
                    }
                )
            elif hr > 100:
                findings.append(
                    {
                        "code": "HR_ELEVATED",
                        "description": f"Elevated heart rate: {hr} bpm",
                        "severity": "warning",
                        "value": hr,
                        "threshold": 100,
                    }
                )
            elif hr < 40:
                findings.append(
                    {
                        "code": "HR_BRADYCARDIA",
                        "description": f"Severe bradycardia: {hr} bpm",
                        "severity": "high",
                        "value": hr,
                        "threshold": 60,
                    }
                )
            elif hr < 60:
                findings.append(
                    {
                        "code": "HR_BRADYCARDIA",
                        "description": f"Bradycardia: {hr} bpm",
                        "severity": "moderate",
                        "value": hr,
                        "threshold": 60,
                    }
                )

        if spo2 is not None and spo2 < 95:
            if spo2 < 85:
                findings.append(
                    {
                        "code": "SPO2_LOW",
                        "description": f"Critical hypoxemia: SpO2 {spo2}%",
                        "severity": "critical",
                        "value": spo2,
                        "threshold": 95,
                    }
                )
            elif spo2 < 90:
                findings.append(
                    {
                        "code": "SPO2_LOW",
                        "description": f"Low oxygen saturation: SpO2 {spo2}%",
                        "severity": "high",
                        "value": spo2,
                        "threshold": 95,
                    }
                )
            else:
                findings.append(
                    {
                        "code": "SPO2_LOW",
                        "description": f"Borderline SpO2: {spo2}%",
                        "severity": "moderate",
                        "value": spo2,
                        "threshold": 95,
                    }
                )

        if sbp is not None and sbp >= 130:
            if sbp >= 180:
                findings.append(
                    {
                        "code": "SBP_ELEVATED",
                        "description": f"Hypertensive crisis: {sbp} mmHg",
                        "severity": "critical",
                        "value": sbp,
                        "threshold": 130,
                    }
                )
            elif sbp >= 160:
                findings.append(
                    {
                        "code": "SBP_ELEVATED",
                        "description": f"Severe hypertension: {sbp} mmHg",
                        "severity": "alert",
                        "value": sbp,
                        "threshold": 130,
                    }
                )
            elif sbp >= 140:
                findings.append(
                    {
                        "code": "SBP_ELEVATED",
                        "description": f"Stage 2 hypertension: {sbp} mmHg",
                        "severity": "high",
                        "value": sbp,
                        "threshold": 130,
                    }
                )
            else:
                findings.append(
                    {
                        "code": "SBP_ELEVATED",
                        "description": f"Elevated systolic BP: {sbp} mmHg",
                        "severity": "moderate",
                        "value": sbp,
                        "threshold": 130,
                    }
                )

        if glucose is not None:
            if glucose >= 400:
                findings.append(
                    {
                        "code": "GLUCOSE_HIGH",
                        "description": f"Severe hyperglycemia: {glucose} mg/dL",
                        "severity": "critical",
                        "value": glucose,
                        "threshold": 200,
                    }
                )
            elif glucose >= 200:
                findings.append(
                    {
                        "code": "GLUCOSE_HIGH",
                        "description": f"High blood glucose: {glucose} mg/dL",
                        "severity": "high",
                        "value": glucose,
                        "threshold": 200,
                    }
                )
            elif glucose < 54:
                findings.append(
                    {
                        "code": "GLUCOSE_LOW",
                        "description": f"Severe hypoglycemia: {glucose} mg/dL",
                        "severity": "critical",
                        "value": glucose,
                        "threshold": 70,
                    }
                )
            elif glucose < 70:
                findings.append(
                    {
                        "code": "GLUCOSE_LOW",
                        "description": f"Low blood glucose: {glucose} mg/dL",
                        "severity": "high",
                        "value": glucose,
                        "threshold": 70,
                    }
                )

        return findings

    def _generate_recommendations(
        self, risk_level: RiskLevel, findings: list, medication_data: dict
    ) -> list:
        recommendations: list[str] = []

        if risk_level == RiskLevel.CRITICAL:
            recommendations.append(
                "IMMEDIATE medical evaluation required — activate emergency protocol."
            )
            recommendations.append("IMMEDIATE notification to on-call physician.")
        elif risk_level == RiskLevel.HIGH:
            recommendations.append("URGENT clinical review required within 1 hour.")
            recommendations.append("URGENT notification to attending physician.")
        elif risk_level == RiskLevel.MODERATE:
            recommendations.append("Schedule clinical review within 24 hours.")
            recommendations.append("Increase monitoring frequency.")
        else:
            recommendations.append("Continue routine monitoring schedule.")

        for finding in findings:
            code = finding.get("code", "")
            if "ADHERENCE" in code:
                recommendations.append(
                    "Review medication adherence barriers with patient and pharmacist."
                )
            elif code == "DRUG_INTERACTION":
                recommendations.append(
                    "Consult pharmacist to review drug interaction and adjust regimen."
                )
            elif "CARDIAC" in code:
                recommendations.append(
                    "Cardiology review recommended given cardiac history."
                )

        recommendations.append("Document findings in patient clinical record.")

        return recommendations

    def _build_reasoning(
        self,
        patient_id: str,
        composite_score: float,
        domain_scores: dict,
        risk_level: RiskLevel,
        findings: list,
    ) -> list:
        reasoning = [
            f"Patient {patient_id} — composite risk score: {composite_score:.1f}/100.",
            (
                f"Domain scores — vitals: {domain_scores['vitals']}, "
                f"medication: {domain_scores['medication']}, "
                f"history: {domain_scores['history']}."
            ),
            f"Risk level classified as {risk_level.value.upper()} based on score and finding severity.",
        ]

        critical_findings = [
            f for f in findings if f.get("severity") == FindingSeverity.CRITICAL.value
        ]
        if critical_findings:
            codes = ", ".join(f["code"] for f in critical_findings)
            reasoning.append(
                f"Critical findings detected: {codes} — overriding to CRITICAL risk."
            )

        vitals_count = len([f for f in findings if f.get("domain") == "vitals"])
        if domain_scores["vitals"] > 0:
            reasoning.append(
                f"Vitals score {domain_scores['vitals']} driven by {vitals_count} finding(s)."
            )

        if domain_scores["medication"] > 0:
            reasoning.append(
                f"Medication score {domain_scores['medication']} driven by adherence/interaction concerns."
            )

        return reasoning