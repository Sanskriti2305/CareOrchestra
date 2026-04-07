"""
Unit tests for agent coordination fixes.

Covers:
- Fix 1: Double escalation prevention
- Fix 2: call_analysis_agent vitals/adherence mapping
- Fix 3: response.text None guard in CoordinatorAgent
- Fix 4: EscalationAgent triggers ReportingAgent after alert
- Fix 5: SymptomsAgent tool registration
- Fix 6: CareOrchestraApp initialises all agents
- Fix 7: Risk vocabulary — adherence uses 'adherence_risk', not 'risk_level'
- Fix 8: EscalationAgent labels patient correctly in email

NOTE: conftest.py in this directory pre-injects google.* and openai stubs so
that module-level BigQueryClient / genai.Client instantiation is a no-op.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fix 1 — Double escalation prevention
# ---------------------------------------------------------------------------

class TestDoubleEscalationPrevention:
    """send_to_monitoring_agent must not set escalation_needed=True when
    MonitoringAgent has already escalated internally."""

    @pytest.mark.asyncio
    async def test_escalation_not_duplicated_on_critical(self):
        """When MonitoringAgent action='escalated', escalation_needed must be False."""
        import apps.adk_app.agents.coordinator as coord_mod

        monitoring_response = {
            "risk_level": "critical",
            "action": "escalated",
            "message": "Care team alerted.",
            "escalation": {"escalation_status": "sent"},
        }

        mock_instance = MagicMock()
        mock_instance.process_summary = AsyncMock(return_value=monitoring_response)

        with patch.object(coord_mod, "MonitoringAgent", return_value=mock_instance):
            result = await coord_mod.send_to_monitoring_agent("P001", "chest pain summary")

        assert result["escalation_needed"] is False, (
            "escalation_needed should be False when MonitoringAgent already escalated"
        )

    @pytest.mark.asyncio
    async def test_escalation_not_duplicated_on_high(self):
        """When MonitoringAgent action='alerted', escalation_needed must be False."""
        import apps.adk_app.agents.coordinator as coord_mod

        monitoring_response = {
            "risk_level": "high",
            "action": "alerted",
            "message": "Notified care team.",
        }
        mock_instance = MagicMock()
        mock_instance.process_summary = AsyncMock(return_value=monitoring_response)

        with patch.object(coord_mod, "MonitoringAgent", return_value=mock_instance):
            result = await coord_mod.send_to_monitoring_agent("P002", "high BP summary")

        assert result["escalation_needed"] is False

    @pytest.mark.asyncio
    async def test_escalation_needed_when_not_yet_escalated(self):
        """If risk is high but monitoring didn't escalate, Coordinator must be told."""
        import apps.adk_app.agents.coordinator as coord_mod

        monitoring_response = {
            "risk_level": "high",
            "action": "logged",   # did NOT escalate
            "message": "Logged for review.",
        }
        mock_instance = MagicMock()
        mock_instance.process_summary = AsyncMock(return_value=monitoring_response)

        with patch.object(coord_mod, "MonitoringAgent", return_value=mock_instance):
            result = await coord_mod.send_to_monitoring_agent("P003", "high risk summary")

        assert result["escalation_needed"] is True

    @pytest.mark.asyncio
    async def test_low_risk_never_triggers_escalation(self):
        import apps.adk_app.agents.coordinator as coord_mod

        monitoring_response = {"risk_level": "low", "action": "logged", "message": "Stable."}
        mock_instance = MagicMock()
        mock_instance.process_summary = AsyncMock(return_value=monitoring_response)

        with patch.object(coord_mod, "MonitoringAgent", return_value=mock_instance):
            result = await coord_mod.send_to_monitoring_agent("P004", "all good summary")

        assert result["escalation_needed"] is False


# ---------------------------------------------------------------------------
# Fix 2 — call_analysis_agent vitals + adherence mapping
# ---------------------------------------------------------------------------

class TestCallAnalysisAgent:
    """call_analysis_agent must correctly translate vitals issues and
    adherence data before handing them to AnalysisAgent."""

    @pytest.mark.asyncio
    async def test_critical_vitals_issue_maps_to_critical_finding(self):
        import apps.adk_app.agents.coordinator as coord_mod

        vitals_response = {
            "status": "alert",
            "patient_id": "P001",
            "latest": {},
            "issues": [
                {"type": "blood_pressure", "level": "crisis", "value": "185/122 mmHg"}
            ],
        }
        adherence_response = {"adherence_rate": 90}

        with (
            patch.object(coord_mod, "get_patient_vitals", AsyncMock(return_value=vitals_response)),
            patch.object(coord_mod, "get_adherence_summary", AsyncMock(return_value=adherence_response)),
        ):
            result = await coord_mod.call_analysis_agent("P001")

        assert result["risk_level"] in ("critical", "high")
        assert result["escalate"] is True

    @pytest.mark.asyncio
    async def test_clean_vitals_produce_low_risk(self):
        import apps.adk_app.agents.coordinator as coord_mod

        vitals_response = {"status": "normal", "patient_id": "P002", "latest": {}, "issues": []}
        adherence_response = {"adherence_rate": 95}

        with (
            patch.object(coord_mod, "get_patient_vitals", AsyncMock(return_value=vitals_response)),
            patch.object(coord_mod, "get_adherence_summary", AsyncMock(return_value=adherence_response)),
        ):
            result = await coord_mod.call_analysis_agent("P002")

        assert result["risk_level"] == "low"
        assert result["escalate"] is False

    @pytest.mark.asyncio
    async def test_poor_adherence_raises_risk(self):
        import apps.adk_app.agents.coordinator as coord_mod

        vitals_response = {"status": "normal", "patient_id": "P003", "latest": {}, "issues": []}

        # Good adherence baseline
        with (
            patch.object(coord_mod, "get_patient_vitals", AsyncMock(return_value=vitals_response)),
            patch.object(coord_mod, "get_adherence_summary", AsyncMock(return_value={"adherence_rate": 95})),
        ):
            result_good = await coord_mod.call_analysis_agent("P003")

        # Poor adherence should produce a higher composite score than good adherence
        with (
            patch.object(coord_mod, "get_patient_vitals", AsyncMock(return_value=vitals_response)),
            patch.object(coord_mod, "get_adherence_summary", AsyncMock(return_value={"adherence_rate": 40})),
        ):
            result_poor = await coord_mod.call_analysis_agent("P003")

        assert result_poor["composite_score"] > result_good["composite_score"], (
            "Poor adherence should produce a higher risk score than good adherence"
        )

    @pytest.mark.asyncio
    async def test_all_vitals_level_keys_map_without_keyerror(self):
        """Every level that VitalsAgent can produce must survive the mapping."""
        import apps.adk_app.agents.coordinator as coord_mod

        levels = [
            "crisis", "critical", "severe_tachycardia", "severe_bradycardia",
            "severe_hyperglycemia", "severe_hypoglycemia",
            "high", "warning", "tachycardia", "bradycardia", "low",
        ]
        adherence_response = {"adherence_rate": None}

        for level in levels:
            vitals_response = {
                "issues": [{"type": "heart_rate", "level": level, "value": "120 bpm"}],
                "latest": {},
            }
            with (
                patch.object(coord_mod, "get_patient_vitals", AsyncMock(return_value=vitals_response)),
                patch.object(coord_mod, "get_adherence_summary", AsyncMock(return_value=adherence_response)),
            ):
                result = await coord_mod.call_analysis_agent("P_LEVEL")
            assert "risk_level" in result, f"Missing risk_level for vitals level={level}"


# ---------------------------------------------------------------------------
# Fix 3 — response.text None guard
# ---------------------------------------------------------------------------

class TestCoordinatorNoneTextGuard:
    """CoordinatorAgent must not crash or corrupt history when response.text is None."""

    @pytest.mark.asyncio
    async def test_none_response_text_returns_empty_string(self):
        import apps.adk_app.agents.coordinator as coord_mod

        mock_response = MagicMock()
        mock_response.text = None

        mock_aio = MagicMock()
        mock_aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio = mock_aio

        with patch.object(coord_mod.genai, "Client", return_value=mock_client):
            agent = coord_mod.CoordinatorAgent()
            result = await agent.coordinate({"patient_id": "P001", "message": "hello"})

        assert result["status"] == "success"
        assert result["message_to_patient"] == ""

    @pytest.mark.asyncio
    async def test_none_text_does_not_corrupt_history(self):
        """History should contain an empty string Part, not None."""
        import apps.adk_app.agents.coordinator as coord_mod

        mock_response = MagicMock()
        mock_response.text = None

        mock_aio = MagicMock()
        mock_aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio = mock_aio

        with patch.object(coord_mod.genai, "Client", return_value=mock_client):
            agent = coord_mod.CoordinatorAgent()
            await agent.coordinate({"patient_id": "P001", "message": "hello"})

        model_turns = [c for c in agent.history if hasattr(c, "role") and c.role == "model"]
        assert len(model_turns) == 1


# ---------------------------------------------------------------------------
# Fix 4 — EscalationAgent triggers ReportingAgent
# ---------------------------------------------------------------------------

class TestEscalationTriggersReporting:
    """After a successful alert delivery, EscalationAgent must generate a
    doctor summary via ReportingAgent and include report_status in its return."""

    @pytest.mark.asyncio
    async def test_report_status_in_escalation_result(self):
        import apps.adk_app.agents.escalation as esc_mod

        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=[])
        mock_bq.insert = AsyncMock(return_value=True)

        mock_report_instance = MagicMock()
        mock_report_instance.generate_doctor_summary = AsyncMock(
            return_value="DOCTOR SUMMARY\n..."
        )

        with (
            patch.object(esc_mod, "_bq_client", mock_bq),
            patch.object(esc_mod, "ReportingAgent", return_value=mock_report_instance),
        ):
            agent = esc_mod.EscalationAgent()
            result = await agent.escalate_alert(
                patient_id="P001",
                risk_level="critical",
                alert_summary={"summary": "Patient chest pain"},
            )

        assert "report_status" in result
        mock_report_instance.generate_doctor_summary.assert_called_once_with(
            patient_id="P001",
            analysis={"summary": "Patient chest pain"},
        )

    @pytest.mark.asyncio
    async def test_report_status_sent_on_success(self):
        import apps.adk_app.agents.escalation as esc_mod

        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=[])
        mock_bq.insert = AsyncMock(return_value=True)

        mock_report_instance = MagicMock()
        mock_report_instance.generate_doctor_summary = AsyncMock(return_value="Summary")

        with (
            patch.object(esc_mod, "_bq_client", mock_bq),
            patch.object(esc_mod, "ReportingAgent", return_value=mock_report_instance),
        ):
            agent = esc_mod.EscalationAgent()
            result = await agent.escalate_alert("P001", "high", {"summary": "BP high"})

        assert result["report_status"] == "sent"


# ---------------------------------------------------------------------------
# Fix 5 — SymptomsAgent tool registration
# ---------------------------------------------------------------------------

class TestSymptomsAgentToolRegistration:
    """assess_symptoms must be registered as a tool on root_agent."""

    def test_assess_symptoms_registered_as_tool(self):
        import importlib

        # Replace the Agent stub with a trackable MagicMock instance so that
        # call_args is reliably captured when the module executes root_agent = Agent(...)
        agent_cls_mock = MagicMock()
        sys.modules["google.adk.agents"].Agent = agent_cls_mock

        # Re-execute Symptoms_agent so the module-level Agent(...) call is recorded
        import apps.adk_app.agents.Symptoms_agent as sym_mod
        importlib.reload(sym_mod)

        assert agent_cls_mock.called, "Agent constructor was never called"
        call_kwargs = agent_cls_mock.call_args.kwargs
        tools_passed = call_kwargs.get("tools", [])
        assert sym_mod.assess_symptoms in tools_passed, (
            f"assess_symptoms not in root_agent tools; got: {tools_passed}"
        )


# ---------------------------------------------------------------------------
# Fix 6 — CareOrchestraApp initialises all agents
# ---------------------------------------------------------------------------

class TestCareOrchestraAppInitialisation:
    """All expected agents must be registered in CareOrchestraApp.agents."""

    def test_all_agents_initialized(self):
        # Reload app module (stubs already in sys.modules from conftest)
        import apps.adk_app.app as app_mod
        importlib.reload(app_mod)

        # google.cloud.logging.Client is already a MagicMock from the conftest stubs;
        # just construct the app directly.
        app = app_mod.CareOrchestraApp()

        expected = {"vitals", "medication", "monitoring", "analysis", "reporting", "coordinator"}
        assert expected.issubset(set(app.agents.keys())), (
            f"Missing agents: {expected - set(app.agents.keys())}"
        )


# ---------------------------------------------------------------------------
# Fix 7 — Risk vocabulary: adherence uses 'adherence_risk', not 'risk_level'
# ---------------------------------------------------------------------------

class TestAdherenceRiskVocabulary:
    """get_adherence_summary must use 'adherence_risk' key, not 'risk_level'."""

    @pytest.mark.asyncio
    async def test_adherence_summary_uses_adherence_risk_key(self):
        import apps.adk_app.agents.medication as med_mod

        rows = [{"taken": True}] * 8 + [{"taken": False}] * 2  # 80% adherence
        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=rows)

        with patch.object(med_mod, "bq_client", mock_bq):
            result = await med_mod.get_adherence_summary("P001")

        assert "adherence_risk" in result, "Key 'adherence_risk' missing from result"
        assert "risk_level" not in result, (
            "'risk_level' should not appear in adherence summary — use 'adherence_risk'"
        )

    @pytest.mark.asyncio
    async def test_reporting_fetch_adherence_uses_adherence_risk_key(self):
        import apps.adk_app.agents.reporting as rep_mod

        rows = [{"taken": True}] * 9 + [{"taken": False}] * 1
        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=rows)

        with patch.object(rep_mod, "_bq_client", mock_bq):
            agent = rep_mod.ReportingAgent()
            result = await agent._fetch_adherence("P001", 7)

        assert "adherence_risk" in result
        assert "risk_level" not in result


# ---------------------------------------------------------------------------
# Fix 8 — EscalationAgent labels patient correctly in email
# ---------------------------------------------------------------------------

class TestEscalationPatientLabel:
    """send_alert_to_doctor must receive a 'Patient <id>' label, not a bare UUID."""

    @pytest.mark.asyncio
    async def test_patient_label_prefixed_in_email(self):
        import apps.adk_app.agents.escalation as esc_mod

        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=[])
        mock_bq.insert = AsyncMock(return_value=True)

        mock_report_instance = MagicMock()
        mock_report_instance.generate_doctor_summary = AsyncMock(return_value="Summary")

        sent_calls: list[str] = []

        async def capture_send(doctor_email, patient_name, alert_content):
            sent_calls.append(patient_name)
            return True

        with (
            patch.object(esc_mod, "_bq_client", mock_bq),
            patch.object(esc_mod, "ReportingAgent", return_value=mock_report_instance),
        ):
            agent = esc_mod.EscalationAgent()
            agent.send_alert_to_doctor = capture_send
            await agent.escalate_alert("PATIENT-XYZ", "high", {"summary": "BP elevated"})

        assert len(sent_calls) == 1
        assert sent_calls[0].startswith("Patient "), (
            f"Expected 'Patient <id>', got: {sent_calls[0]!r}"
        )
        assert "PATIENT-XYZ" in sent_calls[0]


# ---------------------------------------------------------------------------
# Fix 9 — call_symptoms_agent wired into CoordinatorAgent
# ---------------------------------------------------------------------------

class TestSymptomsAgentCoordinatorIntegration:
    """call_symptoms_agent must be registered in CoordinatorAgent.tools and
    correctly delegate to assess_symptoms."""

    def test_call_symptoms_agent_in_coordinator_tools(self):
        """call_symptoms_agent must appear in CoordinatorAgent.tools."""
        import apps.adk_app.agents.coordinator as coord_mod

        agent = coord_mod.CoordinatorAgent()
        tool_names = [getattr(t, "__name__", str(t)) for t in agent.tools]
        assert "call_symptoms_agent" in tool_names, (
            f"call_symptoms_agent not in CoordinatorAgent.tools; got: {tool_names}"
        )

    def test_call_symptoms_agent_delegates_to_assess_symptoms(self):
        """call_symptoms_agent must call assess_symptoms and return its result."""
        import apps.adk_app.agents.coordinator as coord_mod

        mock_result = "CLINICAL ASSESSMENT\nRisk Score: 30/100\nSeverity: LOW"

        with patch.object(coord_mod, "assess_symptoms", return_value=mock_result) as mock_assess:
            result = coord_mod.call_symptoms_agent(
                patient_id="P001",
                raw_message="I have a mild headache",
                age=60,
                conditions="hypertension",
                medications="Lisinopril",
                vitals_flag="normal",
            )

        assert result == mock_result
        mock_assess.assert_called_once_with(
            raw_message="I have a mild headache",
            patient_id="P001",
            age=60,
            conditions="hypertension",
            medications="Lisinopril",
            vitals_flag="normal",
        )

    def test_call_symptoms_agent_passes_vitals_flag(self):
        """vitals_flag must be forwarded to assess_symptoms unchanged."""
        import apps.adk_app.agents.coordinator as coord_mod

        captured: list[str] = []

        def capture_assess(**kwargs):
            captured.append(kwargs.get("vitals_flag", ""))
            return "CLINICAL ASSESSMENT\nRisk Score: 80/100"

        with patch.object(coord_mod, "assess_symptoms", side_effect=capture_assess):
            coord_mod.call_symptoms_agent(
                patient_id="P002",
                raw_message="chest pain",
                age=65,
                conditions="heart_disease",
                medications="aspirin",
                vitals_flag="critical",
            )

        assert captured == ["critical"], (
            f"Expected vitals_flag 'critical', got: {captured}"
        )

    def test_call_symptoms_agent_default_vitals_flag_is_normal(self):
        """When vitals_flag is omitted, it should default to 'normal'."""
        import apps.adk_app.agents.coordinator as coord_mod

        captured: list[str] = []

        def capture_assess(**kwargs):
            captured.append(kwargs.get("vitals_flag", ""))
            return "CLINICAL ASSESSMENT\nRisk Score: 10/100"

        with patch.object(coord_mod, "assess_symptoms", side_effect=capture_assess):
            coord_mod.call_symptoms_agent(
                patient_id="P003",
                raw_message="feeling a bit tired",
                age=45,
                conditions="asthma",
                medications="inhaler",
            )

        assert captured == ["normal"], (
            f"Expected default vitals_flag 'normal', got: {captured}"
        )


# ---------------------------------------------------------------------------
# Fix 10 — get_patient_profile returns age
# ---------------------------------------------------------------------------

class TestPatientProfileAge:
    """get_patient_profile must compute and return the patient's age from
    date_of_birth so that call_symptoms_agent can receive a valid age."""

    @pytest.mark.asyncio
    async def test_age_returned_for_known_dob(self):
        """age must be a positive integer computed from date_of_birth."""
        import datetime
        import apps.adk_app.agents.coordinator as coord_mod

        dob = datetime.date(1965, 5, 15)
        mock_rows = [{
            "first_name": "John",
            "last_name": "Doe",
            "chronic_conditions": "hypertension,type2_diabetes",
            "date_of_birth": dob,
            "updated_at": "2025-04-01",
        }]
        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=mock_rows)

        with patch.object(coord_mod, "bq_client", mock_bq):
            result = await coord_mod.get_patient_profile("PT001")

        assert "age" in result, "age key missing from get_patient_profile result"
        assert result["age"] >= 59, (
            f"Expected age >= 59 for DOB 1965-05-15, got: {result['age']}"
        )

    @pytest.mark.asyncio
    async def test_age_zero_when_no_patient_found(self):
        """age must default to 0 when no patient row is returned."""
        import apps.adk_app.agents.coordinator as coord_mod

        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=[])

        with patch.object(coord_mod, "bq_client", mock_bq):
            result = await coord_mod.get_patient_profile("UNKNOWN")

        assert result["age"] == 0

    @pytest.mark.asyncio
    async def test_age_zero_when_dob_missing(self):
        """age must default to 0 when date_of_birth is absent from the row."""
        import apps.adk_app.agents.coordinator as coord_mod

        mock_rows = [{
            "first_name": "Jane",
            "last_name": "Smith",
            "chronic_conditions": "asthma",
            "date_of_birth": None,
            "updated_at": "2025-04-01",
        }]
        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=mock_rows)

        with patch.object(coord_mod, "bq_client", mock_bq):
            result = await coord_mod.get_patient_profile("PT002")

        assert result["age"] == 0

    @pytest.mark.asyncio
    async def test_age_from_string_dob(self):
        """age must be computed correctly when date_of_birth is a string."""
        import apps.adk_app.agents.coordinator as coord_mod

        mock_rows = [{
            "first_name": "Bob",
            "last_name": "Jones",
            "chronic_conditions": "copd",
            "date_of_birth": "1952-07-09",
            "updated_at": "2025-04-01",
        }]
        mock_bq = MagicMock()
        mock_bq.query = AsyncMock(return_value=mock_rows)

        with patch.object(coord_mod, "bq_client", mock_bq):
            result = await coord_mod.get_patient_profile("PT005")

        assert result["age"] >= 72, (
            f"Expected age >= 72 for DOB 1952-07-09, got: {result['age']}"
        )
