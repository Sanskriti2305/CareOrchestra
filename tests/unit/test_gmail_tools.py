"""Unit tests for the real Gmail integration (GmailSender).

Covers:
- Mock-mode paths return True / "sent" without any API calls.
- Real-mode _build_credentials raises RuntimeError when no creds path given.
- Real-mode send_alert calls the Gmail API with correctly encoded MIME and
  userId="me".
- Real-mode send_report constructs a multipart/alternative message.
- Real-mode send_bulk_alerts returns "sent"/"failed" per recipient.
- HttpError from the Gmail API is caught and returns False (no raise).

NOTE: conftest.py pre-injects google.* stubs, so importing GmailSender at
module level is safe even without live credentials.
"""

from __future__ import annotations

import asyncio
import base64
import sys
import types
from email import message_from_bytes
from email.header import decode_header
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_real_sender(mock_service=None):
    """Return a GmailSender in real mode with a stubbed Gmail API service."""
    from apps.adk_app.tools.gmail_tools.alert_sender import GmailSender

    sender = GmailSender.__new__(GmailSender)
    sender.sender_email = "alerts@test.com"
    sender.use_mock = False
    sender._service = mock_service or MagicMock()
    return sender


def _decode_raw(raw_b64: str):
    """Decode a base64url-encoded raw MIME message into an email.Message."""
    raw_bytes = base64.urlsafe_b64decode(raw_b64 + "==")
    return message_from_bytes(raw_bytes)


def _decode_subject(msg) -> str:
    """Return the fully decoded (unicode) subject from an email.Message."""
    parts = decode_header(msg["Subject"] or "")
    decoded = []
    for fragment, charset in parts:
        if isinstance(fragment, bytes):
            decoded.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(fragment)
    return "".join(decoded)


# ---------------------------------------------------------------------------
# Mock-mode tests
# ---------------------------------------------------------------------------

class TestGmailSenderMockMode:
    """All public methods must succeed in mock mode without any API calls."""

    @pytest.mark.asyncio
    async def test_send_alert_mock_returns_true(self, capsys):
        from apps.adk_app.tools.gmail_tools.alert_sender import GmailSender

        sender = GmailSender("alerts@test.com", use_mock=True)
        result = await sender.send_alert("doc@test.com", "Patient X", "alert body")

        assert result is True
        captured = capsys.readouterr().out
        assert "[MOCK]" in captured
        assert "doc@test.com" in captured

    @pytest.mark.asyncio
    async def test_send_report_mock_returns_true(self, capsys):
        from apps.adk_app.tools.gmail_tools.alert_sender import GmailSender

        sender = GmailSender("alerts@test.com", use_mock=True)
        result = await sender.send_report("doc@test.com", "doctor_summary", "report body")

        assert result is True
        captured = capsys.readouterr().out
        assert "[MOCK]" in captured
        assert "doctor_summary" in captured

    @pytest.mark.asyncio
    async def test_send_bulk_alerts_mock_returns_sent_for_all(self):
        from apps.adk_app.tools.gmail_tools.alert_sender import GmailSender

        sender = GmailSender("alerts@test.com", use_mock=True)
        recipients = ["a@test.com", "b@test.com", "c@test.com"]
        results = await sender.send_bulk_alerts(recipients, "subject", "body")

        assert results == {r: "sent" for r in recipients}

    def test_mock_mode_does_not_call_build_credentials(self):
        """Constructing in mock mode must not attempt to load any credentials."""
        from apps.adk_app.tools.gmail_tools.alert_sender import GmailSender

        sender = GmailSender("alerts@test.com", use_mock=True)
        assert sender._service is None


# ---------------------------------------------------------------------------
# Real-mode credential building
# ---------------------------------------------------------------------------

class TestBuildCredentials:
    """_build_credentials must raise RuntimeError when config is missing."""

    def test_raises_when_no_credentials_path(self):
        from apps.adk_app.tools.gmail_tools.alert_sender import GmailSender

        # Ensure env vars are absent
        env_patch = {
            "GMAIL_CREDENTIALS_PATH": "",
            "GOOGLE_APPLICATION_CREDENTIALS": "",
        }
        with patch.dict("os.environ", env_patch, clear=False):
            with pytest.raises(RuntimeError, match="No Gmail credentials path"):
                GmailSender("alerts@test.com", use_mock=False)

    def test_raises_when_key_file_not_found(self, tmp_path):
        from apps.adk_app.tools.gmail_tools.alert_sender import GmailSender

        nonexistent = str(tmp_path / "missing.json")
        env_patch = {
            "GMAIL_CREDENTIALS_PATH": nonexistent,
            "GOOGLE_APPLICATION_CREDENTIALS": "",
        }

        # Patch the service_account attribute on the already-registered
        # google.oauth2 stub module so the local import inside _build_credentials
        # picks it up via attribute access on the parent package.
        import sys as _sys
        google_oauth2_mod = _sys.modules["google.oauth2"]
        mock_sa = MagicMock()
        mock_sa.Credentials.from_service_account_file.side_effect = FileNotFoundError

        with patch.dict("os.environ", env_patch, clear=False):
            with patch.object(google_oauth2_mod, "service_account", mock_sa):
                with pytest.raises(RuntimeError, match="not found"):
                    GmailSender("alerts@test.com", use_mock=False)


# ---------------------------------------------------------------------------
# Real-mode send_alert
# ---------------------------------------------------------------------------

class TestSendAlertRealMode:
    """send_alert must encode a correctly-addressed MIME message and call
    the Gmail API with userId='me'."""

    @pytest.mark.asyncio
    async def test_send_alert_calls_api_with_correct_payload(self):
        mock_execute = MagicMock(return_value={"id": "msg123"})
        mock_send = MagicMock()
        mock_send.return_value.execute = mock_execute
        mock_messages = MagicMock()
        mock_messages.return_value.send = mock_send
        mock_users = MagicMock()
        mock_users.return_value.messages = mock_messages

        mock_service = MagicMock()
        mock_service.users = mock_users

        sender = _make_real_sender(mock_service)
        result = await sender.send_alert("doc@clinic.com", "Patient 001", "High BP detected.")

        assert result is True
        mock_send.assert_called_once()

        # Verify the raw payload decodes to a valid email
        call_kwargs = mock_send.call_args
        body_arg = call_kwargs.kwargs.get("body") or (call_kwargs.args[0] if call_kwargs.args else None)
        assert body_arg is not None, "send() was not called with a body argument"
        raw = body_arg["raw"]
        email_msg = _decode_raw(raw)
        subject = _decode_subject(email_msg)
        assert email_msg["To"] == "doc@clinic.com"
        assert "CareOrchestra Alert" in subject
        assert "Patient 001" in subject

    @pytest.mark.asyncio
    async def test_send_alert_returns_false_on_http_error(self):
        """When the Gmail API raises an exception, send_alert must return False."""
        mock_execute = MagicMock(side_effect=Exception("API error"))
        mock_send = MagicMock()
        mock_send.return_value.execute = mock_execute
        mock_messages = MagicMock()
        mock_messages.return_value.send = mock_send
        mock_service = MagicMock()
        mock_service.users.return_value.messages = mock_messages

        sender = _make_real_sender(mock_service)
        result = await sender.send_alert("doc@clinic.com", "Patient 002", "body")

        assert result is False


# ---------------------------------------------------------------------------
# Real-mode send_report
# ---------------------------------------------------------------------------

class TestSendReportRealMode:
    """send_report must build a multipart/alternative message with both
    plain-text and HTML parts."""

    @pytest.mark.asyncio
    async def test_send_report_uses_multipart_message(self):
        captured_body: list[dict] = []

        def capture_send(userId, body):  # noqa: N803
            captured_body.append(body)
            return MagicMock(execute=MagicMock(return_value={"id": "r1"}))

        mock_messages = MagicMock()
        mock_messages.return_value.send = capture_send
        mock_service = MagicMock()
        mock_service.users.return_value.messages = mock_messages

        sender = _make_real_sender(mock_service)
        result = await sender.send_report("doc@clinic.com", "doctor_summary", "Report here.")

        assert result is True
        assert captured_body, "send() was never called"
        raw = captured_body[0]["raw"]
        email_msg = _decode_raw(raw)
        assert email_msg.get_content_type() == "multipart/alternative"
        payloads = email_msg.get_payload()
        content_types = {p.get_content_type() for p in payloads}
        assert "text/plain" in content_types
        assert "text/html" in content_types


# ---------------------------------------------------------------------------
# Real-mode send_bulk_alerts
# ---------------------------------------------------------------------------

class TestSendBulkAlertsRealMode:
    """send_bulk_alerts must return 'sent'/'failed' per recipient."""

    @pytest.mark.asyncio
    async def test_bulk_alerts_all_sent(self):
        mock_execute = MagicMock(return_value={"id": "x"})
        mock_send_fn = MagicMock()
        mock_send_fn.return_value.execute = mock_execute
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.send = mock_send_fn

        sender = _make_real_sender(mock_service)
        recipients = ["a@test.com", "b@test.com"]
        results = await sender.send_bulk_alerts(recipients, "Alert", "Body text")

        assert results["a@test.com"] == "sent"
        assert results["b@test.com"] == "sent"

    @pytest.mark.asyncio
    async def test_bulk_alerts_partial_failure(self):
        call_count = 0

        def flaky_execute():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("network error")
            return {"id": "ok"}

        mock_send_obj = MagicMock()
        mock_send_obj.execute = flaky_execute
        mock_send_fn = MagicMock(return_value=mock_send_obj)
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.send = mock_send_fn

        sender = _make_real_sender(mock_service)
        recipients = ["ok@test.com", "fail@test.com", "ok2@test.com"]
        results = await sender.send_bulk_alerts(recipients, "Subject", "Body")

        assert results["ok@test.com"] == "sent"
        assert results["fail@test.com"] == "failed"
        assert results["ok2@test.com"] == "sent"

    @pytest.mark.asyncio
    async def test_bulk_alerts_no_longer_returns_pending(self):
        """Ensure the old 'pending' stub value is gone."""
        mock_execute = MagicMock(return_value={"id": "x"})
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.send.return_value.execute = (
            mock_execute
        )

        sender = _make_real_sender(mock_service)
        results = await sender.send_bulk_alerts(["r@test.com"], "s", "b")

        assert "pending" not in results.values()
