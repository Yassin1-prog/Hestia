"""Landlord outreach swarm: one agent per approved listing, all running concurrently.

Each per-listing agent:
  1. extracts the landlord's phone / e-mail from the agent response (`contacts.py`),
  2. composes the SMS and e-mail for that listing (`messages.py`),
  3. sends on every requested channel it has a valid contact for (`channels.py`),
  4. reports a per-channel attempt log for the live dashboard.

Safety switches (read from the environment on every run):
  * `OUTREACH_DRY_RUN` (default **true**): compose everything, send nothing. This is a hard
    kill-switch — an API request can opt *into* dry-run but never out of it.
  * `OUTREACH_OVERRIDE_PHONE` / `OUTREACH_OVERRIDE_EMAIL`: redirect every real message to a
    team member's phone / inbox (live demos, Twilio trial accounts) instead of the landlord.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Literal, Optional, Sequence

import httpx
from pydantic import BaseModel, Field

from backend.outreach.channels import ResendEmailSender, SendResult, TwilioSmsSender
from backend.outreach.contacts import ExtractedContacts, to_dict, extract_contacts
from backend.outreach.messages import OutreachContext, compose_email, compose_sms

# "call" is a live voice call the browser places through Vapi (the server only writes its brief).
Channel = Literal["sms", "email", "call"]
AttemptStatus = Literal["sent", "dry_run", "skipped", "failed"]
OutreachStatus = Literal["contacted", "dry_run", "no_contact", "failed"]


ALL_CHANNELS: tuple[Channel, ...] = ("sms", "email", "call")
DEFAULT_CHANNELS: tuple[Channel, ...] = ("email", "call")


class OutreachSettings(BaseModel):
    dry_run: bool = True
    # Channels enabled on this server (OUTREACH_CHANNELS). E-mail + voice call by default: SMS is
    # disabled for now (the Twilio adapter is kept; opt back in with OUTREACH_CHANNELS=sms,email,call).
    channels: list[Channel] = Field(default_factory=lambda: list(DEFAULT_CHANNELS))
    override_phone: Optional[str] = None
    override_email: Optional[str] = None
    max_concurrency: int = 5

    @classmethod
    def from_env(cls) -> "OutreachSettings":
        def env(name: str) -> Optional[str]:
            return os.getenv(name, "").strip() or None

        requested = (env("OUTREACH_CHANNELS") or ",".join(DEFAULT_CHANNELS)).lower().replace(" ", "").split(",")
        return cls(
            dry_run=(env("OUTREACH_DRY_RUN") or "true").lower() not in {"0", "false", "no", "off"},
            channels=[c for c in ALL_CHANNELS if c in requested],
            override_phone=env("OUTREACH_OVERRIDE_PHONE"),
            override_email=env("OUTREACH_OVERRIDE_EMAIL"),
            max_concurrency=int(env("OUTREACH_MAX_CONCURRENCY") or 5),
        )


class ChannelAttempt(BaseModel):
    channel: Channel
    status: AttemptStatus
    to: Optional[str] = Field(default=None, description="Actual recipient (after any override).")
    intended_to: Optional[str] = Field(default=None, description="The landlord's own contact.")
    provider_id: Optional[str] = Field(default=None, description="Twilio SID / Resend id / Vapi web call.")
    detail: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = Field(default=None, description="Exact text sent (or that would be).")


class PropertyOutreachResult(BaseModel):
    url: str
    status: OutreachStatus
    contacts: ExtractedContacts
    attempts: list[ChannelAttempt]


class OutreachBatchResponse(BaseModel):
    dry_run: bool
    channels: list[Channel] = Field(default_factory=list, description="Channels actually used.")
    results: list[PropertyOutreachResult]
    contacted: int = 0
    failed: int = 0
    no_contact: int = 0


def _overall_status(attempts: list[ChannelAttempt]) -> OutreachStatus:
    statuses = {a.status for a in attempts}
    if "sent" in statuses:
        return "contacted"
    if "dry_run" in statuses:
        return "dry_run"
    if statuses <= {"skipped"}:
        return "no_contact"
    return "failed"


def flagged_as_scam(listing: dict[str, Any]) -> bool:
    """True when the Oumi Iris scam check flagged the listing. Such listings are never contacted."""
    return str(listing.get("scam_verdict") or "").strip().upper() == "POSSIBLY_SCAM"


SCAM_LOCK_DETAIL = "Not sent: Oumi Iris flagged this listing as a possible scam"


class ListingOutreachAgent:
    """Owns the outreach for exactly one listing / landlord."""

    def __init__(
        self,
        listing: Any,
        context: OutreachContext,
        channels: Sequence[Channel],
        settings: OutreachSettings,
        sms: TwilioSmsSender,
        email: ResendEmailSender,
    ) -> None:
        self.listing = to_dict(listing)
        self.context = context
        self.channels = list(dict.fromkeys(channels))
        self.settings = settings
        self.sms = sms
        self.email = email
        self.scam_locked = flagged_as_scam(self.listing)

    @property
    def dry_run(self) -> bool:
        return self.settings.dry_run or self.scam_locked

    @property
    def dry_run_detail(self) -> Optional[str]:
        return SCAM_LOCK_DETAIL if self.scam_locked else None

    async def run(self, client: httpx.AsyncClient) -> PropertyOutreachResult:
        contacts = extract_contacts(self.listing)
        attempts = await self.send(client, contacts)
        return self.result(contacts, attempts)

    async def send(self, client: httpx.AsyncClient, contacts: ExtractedContacts) -> list[ChannelAttempt]:
        """Sends on every channel of this agent; SMS + e-mail go out in parallel.

        Voice calls are placed by the browser (see `live.py`), so "call" is not sent from here.
        """
        tasks = []
        if "sms" in self.channels:
            tasks.append(self._sms(client, contacts))
        if "email" in self.channels:
            tasks.append(self._email(client, contacts))
        return list(await asyncio.gather(*tasks))

    def result(self, contacts: ExtractedContacts, attempts: list[ChannelAttempt]) -> PropertyOutreachResult:
        return PropertyOutreachResult(
            url=str(self.listing.get("url") or ""),
            status=_overall_status(attempts),
            contacts=contacts,
            attempts=attempts,
        )

    async def _sms(self, client: httpx.AsyncClient, contacts: ExtractedContacts) -> ChannelAttempt:
        target = contacts.sms_phone
        if not target:
            landline = next((p.e164 for p in contacts.phones if p.kind == "landline"), None)
            detail = (
                f"Only a landline ({landline}) was found; it cannot receive SMS"
                if landline
                else "No phone number found in the listing"
            )
            return ChannelAttempt(channel="sms", status="skipped", detail=detail)

        body = compose_sms(self.listing, contacts.name, self.context)
        to = self.settings.override_phone or target
        if self.dry_run:
            return ChannelAttempt(
                channel="sms", status="dry_run", to=to, intended_to=target, body=body, detail=self.dry_run_detail
            )
        result = await self.sms.send(client, to=to, body=body)
        return self._attempt("sms", result, to, target, body=body)

    async def _email(self, client: httpx.AsyncClient, contacts: ExtractedContacts) -> ChannelAttempt:
        target = contacts.email
        if not target:
            return ChannelAttempt(channel="email", status="skipped", detail="No e-mail address found in the listing")

        content = compose_email(self.listing, contacts.name, self.context)
        to = self.settings.override_email or target
        if self.dry_run:
            return ChannelAttempt(
                channel="email", status="dry_run", to=to, intended_to=target,
                subject=content.subject, body=content.text, detail=self.dry_run_detail,
            )
        result = await self.email.send(
            client, to=to, subject=content.subject, text=content.text, html=content.html,
            reply_to=self.context.user.email,
        )
        return self._attempt("email", result, to, target, subject=content.subject, body=content.text)

    @staticmethod
    def _attempt(
        channel: Channel, result: SendResult, to: str, intended_to: str, **extra: Any
    ) -> ChannelAttempt:
        return ChannelAttempt(
            channel=channel,
            status="sent" if result.ok else "failed",
            to=to,
            intended_to=intended_to,
            provider_id=result.provider_id,
            detail=result.detail,
            **extra,
        )


async def run_outreach(
    listings: Sequence[Any],
    context: OutreachContext,
    channels: Optional[Sequence[Channel]] = None,
    *,
    force_dry_run: bool = False,
    settings: Optional[OutreachSettings] = None,
    sms: Optional[TwilioSmsSender] = None,
    email: Optional[ResendEmailSender] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> OutreachBatchResponse:
    """Runs one `ListingOutreachAgent` per approved listing, concurrently.

    `listings` are agent responses (`PropertyDetails` models or dicts). Only call this after
    the human approval gate: with dry-run off, real SMS / e-mails are sent.
    `channels` defaults to the server's enabled channels; channels disabled on the server
    (`OUTREACH_CHANNELS`) are dropped even if requested.
    """
    settings = (settings or OutreachSettings.from_env()).model_copy()
    settings.dry_run = settings.dry_run or force_dry_run
    channels = [c for c in (channels or settings.channels) if c in settings.channels]
    sms = sms or TwilioSmsSender.from_env()
    email = email or ResendEmailSender.from_env()
    semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)

    async def run_one(listing: Any) -> PropertyOutreachResult:
        async with semaphore:
            agent = ListingOutreachAgent(listing, context, channels, settings, sms, email)
            return await agent.run(http_client)

    try:
        results = list(await asyncio.gather(*(run_one(item) for item in listings)))
    finally:
        if owns_client:
            await http_client.aclose()

    return OutreachBatchResponse(
        dry_run=settings.dry_run,
        channels=channels,
        results=results,
        contacted=sum(r.status == "contacted" for r in results),
        failed=sum(r.status == "failed" for r in results),
        no_contact=sum(r.status == "no_contact" for r in results),
    )
