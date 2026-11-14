"""Outreach channel adapters: Twilio (SMS) and Resend (e-mail).

Both are called through their REST APIs with `httpx` rather than the vendor SDKs:
  * no extra dependencies (httpx is already used by `backend/decision.py`),
  * natively async, so one agent per listing can run concurrently,
  * trivially testable with `httpx.MockTransport` (see `tests/test_outreach.py`).

Credentials are read from the environment (see `.env.example`). Missing credentials never
raise: `send()` returns a failed `SendResult` explaining which variable to set.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
from pydantic import BaseModel

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
RESEND_API_URL = "https://api.resend.com/emails"


class SendResult(BaseModel):
    ok: bool
    provider_id: Optional[str] = None
    detail: Optional[str] = None


def _env(name: str) -> Optional[str]:
    value = os.getenv(name, "").strip()
    return value or None


def _error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        body = exc.response.json()
        message = body.get("message") or body.get("error") or body
    except ValueError:
        message = exc.response.text
    return f"HTTP {exc.response.status_code}: {message}"


class TwilioSmsSender:
    """Sends SMS via `POST /Accounts/{sid}/Messages.json` (Basic auth: SID + auth token)."""

    def __init__(
        self,
        account_sid: Optional[str],
        auth_token: Optional[str],
        from_number: Optional[str] = None,
        messaging_service_sid: Optional[str] = None,
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.messaging_service_sid = messaging_service_sid

    @classmethod
    def from_env(cls) -> "TwilioSmsSender":
        return cls(
            account_sid=_env("TWILIO_ACCOUNT_SID"),
            auth_token=_env("TWILIO_AUTH_TOKEN"),
            from_number=_env("TWILIO_FROM_NUMBER"),
            messaging_service_sid=_env("TWILIO_MESSAGING_SERVICE_SID"),
        )

    @property
    def missing_config(self) -> Optional[str]:
        if not self.account_sid or not self.auth_token:
            return "Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env"
        if not self.from_number and not self.messaging_service_sid:
            return "Set TWILIO_FROM_NUMBER (or TWILIO_MESSAGING_SERVICE_SID) in .env"
        return None

    async def send(self, client: httpx.AsyncClient, to: str, body: str) -> SendResult:
        if self.missing_config:
            return SendResult(ok=False, detail=self.missing_config)
        data = {"To": to, "Body": body}
        if self.messaging_service_sid:
            data["MessagingServiceSid"] = self.messaging_service_sid
        else:
            data["From"] = self.from_number  # type: ignore[assignment]
        try:
            resp = await client.post(
                f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages.json",
                data=data,
                auth=(self.account_sid, self.auth_token),  # type: ignore[arg-type]
            )
            resp.raise_for_status()
            payload = resp.json()
            return SendResult(ok=True, provider_id=payload.get("sid"), detail=payload.get("status"))
        except httpx.HTTPStatusError as exc:
            return SendResult(ok=False, detail=f"Twilio {_error_detail(exc)}")
        except httpx.HTTPError as exc:
            return SendResult(ok=False, detail=f"Twilio request failed: {exc!r}")


class ResendEmailSender:
    """Sends e-mail via `POST https://api.resend.com/emails` (Bearer API key)."""

    def __init__(self, api_key: Optional[str], from_email: Optional[str]) -> None:
        self.api_key = api_key
        # `onboarding@resend.dev` works without a verified domain, but Resend then only
        # delivers to the e-mail address that owns the Resend account.
        self.from_email = from_email or "Relocation Agent <onboarding@resend.dev>"

    @classmethod
    def from_env(cls) -> "ResendEmailSender":
        return cls(api_key=_env("RESEND_API_KEY"), from_email=_env("RESEND_FROM_EMAIL"))

    @property
    def missing_config(self) -> Optional[str]:
        return None if self.api_key else "Set RESEND_API_KEY in .env"

    async def send(
        self,
        client: httpx.AsyncClient,
        to: str,
        subject: str,
        text: str,
        html: str,
        reply_to: Optional[str] = None,
    ) -> SendResult:
        if self.missing_config:
            return SendResult(ok=False, detail=self.missing_config)
        payload = {"from": self.from_email, "to": [to], "subject": subject, "text": text, "html": html}
        if reply_to:
            payload["reply_to"] = reply_to  # Landlord replies go straight to the user's inbox.
        try:
            resp = await client.post(
                RESEND_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return SendResult(ok=True, provider_id=resp.json().get("id"))
        except httpx.HTTPStatusError as exc:
            return SendResult(ok=False, detail=f"Resend {_error_detail(exc)}")
        except httpx.HTTPError as exc:
            return SendResult(ok=False, detail=f"Resend request failed: {exc!r}")
