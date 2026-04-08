"""Gmail integration for alert delivery."""

import asyncio
import base64
import logging
import os
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

logger = logging.getLogger(__name__)

# Gmail API scope required for sending mail
_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


@dataclass
class EmailMessage:
    """Email message structure."""

    sender: str
    recipient: str
    subject: str
    body: str
    priority: str = "normal"  # low, normal, high


class GmailSender:
    """Service for sending alerts via Gmail.

    In *mock* mode (``use_mock=True``, the default) every send call simply
    logs to stdout and returns ``True`` — no credentials are needed.

    In *real* mode (``use_mock=False``) the class uses a Google Workspace
    **Service Account with Domain-Wide Delegation** to impersonate
    ``sender_email`` and send via the Gmail REST API.  The service-account
    JSON path is resolved from (in order of priority):

    1. The ``credentials_path`` constructor argument.
    2. The ``GMAIL_CREDENTIALS_PATH`` environment variable.
    3. The ``GOOGLE_APPLICATION_CREDENTIALS`` environment variable.

    The account being impersonated is resolved from (in order):

    1. The ``delegated_account`` constructor argument.
    2. The ``GMAIL_DELEGATED_ACCOUNT`` environment variable.
    3. The ``sender_email`` value (same address used as the From header).
    """

    def __init__(
        self,
        sender_email: str,
        use_mock: bool = True,
        credentials_path: Optional[str] = None,
        delegated_account: Optional[str] = None,
    ):
        """
        Initialise GmailSender.

        Args:
            sender_email: The ``From`` address used in outgoing messages.
            use_mock: When ``True`` (default) no real API calls are made.
            credentials_path: Path to the service-account JSON key file.
                Defaults to ``GMAIL_CREDENTIALS_PATH`` or
                ``GOOGLE_APPLICATION_CREDENTIALS`` env vars.
            delegated_account: The Workspace email the service account will
                impersonate.  Defaults to ``GMAIL_DELEGATED_ACCOUNT`` env var,
                then ``sender_email``.
        """
        self.sender_email = sender_email
        self.use_mock = use_mock
        self._service = None

        if not use_mock:
            self._service = self._build_credentials(credentials_path, delegated_account)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_credentials(
        self,
        credentials_path: Optional[str],
        delegated_account: Optional[str],
    ):
        """Load service-account credentials and return a Gmail API resource.

        Raises:
            RuntimeError: if the credentials file cannot be found or loaded.
        """
        # Resolve credential file path
        creds_file = (
            credentials_path
            or os.getenv("GMAIL_CREDENTIALS_PATH")
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        if not creds_file:
            raise RuntimeError(
                "No Gmail credentials path provided.  Set GMAIL_CREDENTIALS_PATH "
                "or GOOGLE_APPLICATION_CREDENTIALS, or pass credentials_path."
            )

        # Resolve the delegated (impersonated) account
        subject = (
            delegated_account
            or os.getenv("GMAIL_DELEGATED_ACCOUNT")
            or self.sender_email
        )

        try:
            from google.oauth2 import service_account  # type: ignore
            from googleapiclient.discovery import build  # type: ignore

            credentials = service_account.Credentials.from_service_account_file(
                creds_file, scopes=_GMAIL_SCOPES
            ).with_subject(subject)

            return build("gmail", "v1", credentials=credentials, cache_discovery=False)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Gmail service-account key file not found: {creds_file}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to build Gmail API client: {exc}") from exc

    async def _send_message(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> bool:
        """Encode and deliver a single email via the Gmail API.

        Args:
            recipient: Destination email address.
            subject: Email subject line.
            body_text: Plain-text body.
            body_html: Optional HTML body.  When provided a
                ``multipart/alternative`` message is constructed.

        Returns:
            ``True`` on successful delivery, ``False`` on error.
        """
        try:
            if body_html:
                msg: MIMEMultipart | MIMEText = MIMEMultipart("alternative")
                msg["To"] = recipient
                msg["From"] = self.sender_email
                msg["Subject"] = subject
                msg.attach(MIMEText(body_text, "plain"))
                msg.attach(MIMEText(body_html, "html"))
            else:
                msg = MIMEText(body_text, "plain")
                msg["To"] = recipient
                msg["From"] = self.sender_email
                msg["Subject"] = subject

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            service = self._service

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute(),
            )
            logger.info(f"[GmailSender] Email sent to {recipient}: {subject!r}")
            return True
        except Exception as exc:  # includes googleapiclient.errors.HttpError
            logger.error(f"[GmailSender] Failed to send email to {recipient}: {exc}")
            return False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def send_alert(
        self, recipient: str, patient_name: str, alert_content: str
    ) -> bool:
        """Send an alert email to a doctor.

        Args:
            recipient: Doctor's email address.
            patient_name: Patient identifier used in the subject line.
            alert_content: Formatted alert message body.

        Returns:
            ``True`` on success (or in mock mode).
        """
        if self.use_mock:
            print(f"[MOCK] Sending alert email to {recipient}")
            print(f"[MOCK] Patient: {patient_name}")
            print(f"[MOCK] Content: {alert_content[:100]}...")
            return True

        subject = f"\u26a0\ufe0f CareOrchestra Alert \u2014 {patient_name}"
        return await self._send_message(recipient, subject, alert_content)

    async def send_report(
        self, recipient: str, report_type: str, report_content: str
    ) -> bool:
        """Send a clinical report via email.

        Args:
            recipient: Recipient email address.
            report_type: Type of report (e.g. ``doctor_summary``,
                ``nurse_handoff``, ``vitals_report``).
            report_content: Report body in plain text.

        Returns:
            ``True`` on success (or in mock mode).
        """
        if self.use_mock:
            print(f"[MOCK] Sending {report_type} to {recipient}")
            return True

        subject = f"CareOrchestra Report \u2014 {report_type}"
        html_body = f"<html><body><pre>{report_content}</pre></body></html>"
        return await self._send_message(
            recipient, subject, report_content, body_html=html_body
        )

    async def send_bulk_alerts(
        self, recipients: List[str], subject: str, content: str
    ) -> dict:
        """Send an alert to multiple recipients concurrently.

        Args:
            recipients: List of destination email addresses.
            subject: Email subject line.
            content: Email body.

        Returns:
            Dict mapping each recipient address to ``"sent"`` or ``"failed"``.
        """
        if self.use_mock:
            results = {}
            for recipient in recipients:
                print(f"[MOCK] Sending bulk alert to {recipient}")
                results[recipient] = "sent"
            return results

        tasks = [
            self._send_message(recipient, subject, content)
            for recipient in recipients
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            recipient: "sent" if outcome is True else "failed"
            for recipient, outcome in zip(recipients, outcomes)
        }
