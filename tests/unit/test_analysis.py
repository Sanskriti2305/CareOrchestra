"""Tests for AnalysisAgent — covers all risk tiers, overrides, and edge cases."""

import asyncio
import pytest
from analysis_agent import (
    AnalysisAgent,
    RiskLevel,
    FindingSeverity,
    Finding,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def agent():
    return AnalysisAgent()


def _event(history: dict | None = None) -> dict:
    return {"patient_history": history or {}}


CLEAN_VITALS = {
    "findings": []  # no abnormalities
}

CLEAN_MEDS = {
    "findings": [],
    "adherence_score": 95,
    "interactions": [],
}

HIGH_HR_VITALS = {
    "findings": [
        {"code": "HR_ELEVATED", "description": "Heart rate 130 bpm.",
         "severity": "warning", "value": 130, "threshold": 100}
    ]
}

CRITICAL_SPO2_VITALS = {
    "findings": [
        {"code": "SPO2_LOW", "description": "SpO2 82%.",
         "severity": "critical", "value": 82, "threshold": 90}
    ]
}

MULTI_VITAL_ALERT = {
    "findings": [
        {"code": "HR_ELEVATED",  "severity": "alert",    "value": 145, "threshold": 100,
         "description": "Tachycardia"},
        {"code": "SBP_ELEVATED", "severity": "alert",    "value": 185, "threshold": 140,
         "description": "Hypertensive urgency"},
        {"code": "SPO2_LOW",     "severity": "critical", "value": 88,  "threshold": 90,
         "description": "Hypoxaemia"},
    ]
}

POOR_ADHERENCE_MEDS = {
    "findings": [],
    "adherence_score": 40,
    "interactions": [
        {"drugs": ["warfarin", "aspirin"], "severity": "high",
         "description": "Increased bleeding risk."}
    ],
}

CARDIAC_HISTORY = {
    "conditions": ["diabetes"],
    "previous_cardiac_event": True,
    "age": 74,
}


# ──────────────────────────────────────────────────────────────────────────────
# Basic output contract
# ──────────────────────────────────────────────────────────────────────────────

class TestOutputContract:
    @pytest.mark.asyncio
    async def test_returns_required_keys(self, agent):
        result = await agent.analyze_patient_status(
            "P001", CLEAN_VITALS, CLEAN_MEDS, _event()
        )
        for key in ("patient_id", "assessed_at", "risk_level", "composite_score",
                    "domain_scores", "findings", "recommendations", "reasoning",
                    "escalate"):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_patient_id_propagated(self, agent):
        result = await agent.analyze_patient_status(
            "PATIENT-XYZ", CLEAN_VITALS, CLEAN_MEDS, _event()
        )
        assert result["patient_id"] == "PATIENT-XYZ"

    @pytest.mark.asyncio
    async def test_domain_scores_present(self, agent):
        result = await agent.analyze_patient_status(
            "P002", CLEAN_VITALS, CLEAN_MEDS, _event()
        )
        assert set(result["domain_scores"].keys()) == {"vitals", "medication", "history"}


# ──────────────────────────────────────────────────────────────────────────────
# Risk classification — score-based tiers
# ──────────────────────────────────────────────────────────────────────────────

class TestRiskClassification:
    @pytest.mark.asyncio
    async def test_clean_patient_is_low_risk(self, agent):
        result = await agent.analyze_patient_status(
            "P_CLEAN", CLEAN_VITALS, CLEAN_MEDS, _event()
        )
        assert result["risk_level"] == RiskLevel.LOW.value
        assert result["escalate"] is False

    @pytest.mark.asyncio
    async def test_single_warning_vital_moderate_or_higher(self, agent):
        result = await agent.analyze_patient_status(
            "P_WARN", HIGH_HR_VITALS, CLEAN_MEDS, _event()
        )
        assert result["risk_level"] in (RiskLevel.MODERATE.value, RiskLevel.HIGH.value)

    @pytest.mark.asyncio
    async def test_critical_spo2_triggers_critical_risk(self, agent):
        result = await agent.analyze_patient_status(
            "P_CRIT", CRITICAL_SPO2_VITALS, CLEAN_MEDS, _event()
        )
        assert result["risk_level"] == RiskLevel.CRITICAL.value
        assert result["escalate"] is True

    @pytest.mark.asyncio
    async def test_multi_alert_vitals_high_or_critical(self, agent):
        result = await agent.analyze_patient_status(
            "P_MULTI", MULTI_VITAL_ALERT, CLEAN_MEDS, _event()
        )
        assert result["risk_level"] in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)
        assert result["escalate"] is True

    @pytest.mark.asyncio
    async def test_poor_medication_adherence_raises_risk(self, agent):
        result = await agent.analyze_patient_status(
            "P_MED", CLEAN_VITALS, POOR_ADHERENCE_MEDS, _event()
        )
        # Poor adherence + drug interaction should push above LOW
        assert result["risk_level"] != RiskLevel.LOW.value

    @pytest.mark.asyncio
    async def test_cardiac_history_amplifies_risk(self, agent):
        """History alone should raise score even with clean vitals/meds."""
        result = await agent.analyze_patient_status(
            "P_HIST", CLEAN_VITALS, CLEAN_MEDS, _event(CARDIAC_HISTORY)
        )
        assert result["domain_scores"]["history"] > 0

    @pytest.mark.asyncio
    async def test_combined_signals_reach_critical(self, agent):
        result = await agent.analyze_patient_status(
            "P_ALL", MULTI_VITAL_ALERT, POOR_ADHERENCE_MEDS, _event(CARDIAC_HISTORY)
        )
        assert result["risk_level"] == RiskLevel.CRITICAL.value
        assert result["escalate"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Composite score sanity
# ──────────────────────────────────────────────────────────────────────────────

class TestCompositeScore:
    @pytest.mark.asyncio
    async def test_score_in_valid_range(self, agent):
        for vitals, meds, hist in [
            (CLEAN_VITALS, CLEAN_MEDS, {}),
            (HIGH_HR_VITALS, CLEAN_MEDS, {}),
            (MULTI_VITAL_ALERT, POOR_ADHERENCE_MEDS, CARDIAC_HISTORY),
        ]:
            result = await agent.analyze_patient_status(
                "P_RANGE", vitals, meds, _event(hist)
            )
            assert 0 <= result["composite_score"] <= 100

    @pytest.mark.asyncio
    async def test_more_findings_raises_score(self, agent):
        clean = await agent.analyze_patient_status("A", CLEAN_VITALS, CLEAN_MEDS, _event())
        multi = await agent.analyze_patient_status(
            "B", MULTI_VITAL_ALERT, POOR_ADHERENCE_MEDS, _event(CARDIAC_HISTORY)
        )
        assert multi["composite_score"] > clean["composite_score"]


# ──────────────────────────────────────────────────────────────────────────────
# Findings population
# ──────────────────────────────────────────────────────────────────────────────

class TestFindings:
    @pytest.mark.asyncio
    async def test_findings_include_domain_field(self, agent):
        result = await agent.analyze_patient_status(
            "P_F", MULTI_VITAL_ALERT, POOR_ADHERENCE_MEDS, _event(CARDIAC_HISTORY)
        )
        domains = {f["domain"] for f in result["findings"]}
        assert "vitals" in domains
        assert "medication" in domains
        assert "history" in domains

    @pytest.mark.asyncio
    async def test_each_finding_has_required_keys(self, agent):
        result = await agent.analyze_patient_status(
            "P_FK", HIGH_HR_VITALS, CLEAN_MEDS, _event()
        )
        for finding in result["findings"]:
            for key in ("domain", "code", "description", "severity"):
                assert key in finding

    @pytest.mark.asyncio
    async def test_flat_vitals_shape_parsed(self, agent):
        """VitalsAgent may return flat dict instead of findings list."""
        flat_vitals = {"heart_rate": 155, "spo2": 94, "sbp": 150}
        result = await agent.analyze_patient_status(
            "P_FLAT", flat_vitals, CLEAN_MEDS, _event()
        )
        codes = [f["code"] for f in result["findings"]]
        assert "HR_ELEVATED" in codes
        assert "SBP_ELEVATED" in codes


# ──────────────────────────────────────────────────────────────────────────────
# Recommendations
# ──────────────────────────────────────────────────────────────────────────────

class TestRecommendations:
    @pytest.mark.asyncio
    async def test_recommendations_not_empty(self, agent):
        result = await agent.analyze_patient_status(
            "P_REC", HIGH_HR_VITALS, CLEAN_MEDS, _event()
        )
        assert len(result["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_critical_risk_contains_immediate_action(self, agent):
        result = await agent.analyze_patient_status(
            "P_CRIT2", CRITICAL_SPO2_VITALS, POOR_ADHERENCE_MEDS, _event(CARDIAC_HISTORY)
        )
        assert any("IMMEDIATE" in r for r in result["recommendations"])

    @pytest.mark.asyncio
    async def test_high_risk_contains_urgent_action(self, agent):
        result = await agent.analyze_patient_status(
            "P_HIGH", MULTI_VITAL_ALERT, CLEAN_MEDS, _event()
        )
        if result["risk_level"] == RiskLevel.HIGH.value:
            assert any("URGENT" in r for r in result["recommendations"])

    @pytest.mark.asyncio
    async def test_documentation_always_recommended(self, agent):
        for vitals, meds in [(CLEAN_VITALS, CLEAN_MEDS), (CRITICAL_SPO2_VITALS, POOR_ADHERENCE_MEDS)]:
            result = await agent.analyze_patient_status("P_DOC", vitals, meds, _event())
            assert any("Document" in r for r in result["recommendations"])

    @pytest.mark.asyncio
    async def test_drug_interaction_recommendation(self, agent):
        result = await agent.analyze_patient_status(
            "P_DRUG", CLEAN_VITALS, POOR_ADHERENCE_MEDS, _event()
        )
        assert any("interaction" in r.lower() or "pharmacist" in r.lower()
                   for r in result["recommendations"])


# ──────────────────────────────────────────────────────────────────────────────
# Reasoning audit trail
# ──────────────────────────────────────────────────────────────────────────────

class TestReasoning:
    @pytest.mark.asyncio
    async def test_reasoning_is_non_empty_list(self, agent):
        result = await agent.analyze_patient_status(
            "P_R", HIGH_HR_VITALS, CLEAN_MEDS, _event()
        )
        assert isinstance(result["reasoning"], list)
        assert len(result["reasoning"]) >= 3

    @pytest.mark.asyncio
    async def test_reasoning_mentions_patient_id(self, agent):
        result = await agent.analyze_patient_status(
            "PATIENT-99", CLEAN_VITALS, CLEAN_MEDS, _event()
        )
        assert any("PATIENT-99" in r for r in result["reasoning"])

    @pytest.mark.asyncio
    async def test_reasoning_includes_score(self, agent):
        result = await agent.analyze_patient_status(
            "P_SC", HIGH_HR_VITALS, CLEAN_MEDS, _event()
        )
        assert any("score" in r.lower() for r in result["reasoning"])


# ──────────────────────────────────────────────────────────────────────────────
# Standalone assess_risk_level
# ──────────────────────────────────────────────────────────────────────────────

class TestAssessRiskLevel:
    @pytest.mark.asyncio
    async def test_returns_valid_level(self, agent):
        level = await agent.assess_risk_level(HIGH_HR_VITALS, CLEAN_MEDS, {})
        assert level in [r.value for r in RiskLevel]

    @pytest.mark.asyncio
    async def test_critical_vitals_return_high_or_critical(self, agent):
        level = await agent.assess_risk_level(CRITICAL_SPO2_VITALS, POOR_ADHERENCE_MEDS, CARDIAC_HISTORY)
        assert level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_inputs_do_not_crash(self, agent):
        result = await agent.analyze_patient_status("P_EMPTY", {}, {}, {})
        assert result["risk_level"] in [r.value for r in RiskLevel]

    @pytest.mark.asyncio
    async def test_none_adherence_ignored_gracefully(self, agent):
        meds = {"findings": [], "interactions": []}  # no adherence_score key
        result = await agent.analyze_patient_status("P_NA", CLEAN_VITALS, meds, _event())
        assert "risk_level" in result

    @pytest.mark.asyncio
    async def test_unknown_condition_in_history_ignored(self, agent):
        history = {"conditions": ["some_unknown_disease_xyz"], "age": 40}
        result = await agent.analyze_patient_status(
            "P_UNK", CLEAN_VITALS, CLEAN_MEDS, _event(history)
        )
        assert result["risk_level"] == RiskLevel.LOW.value