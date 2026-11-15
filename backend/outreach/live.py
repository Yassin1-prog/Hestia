"""Live outreach agent: the same work as `ListingOutreachAgent`, narrated step by step.

`stream_listing_outreach()` is an async generator of progress events (format in
backend/streaming.py) that the UI renders while the agent works on one approved listing:

    brief     read the listing + the user's profile
    calendar  check the user's calendar and pick free viewing slots (availability.py)
    contact   verify the landlord's e-mail (portal / no-reply addresses are filtered out)
    draft     compose the e-mail (emits a `draft` event with the exact subject + body)
    send      deliver via Resend (or report the dry run), then a final `result` event
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import httpx

from backend.outreach.availability import Availability, check_availability
from backend.outreach.channels import ResendEmailSender, TwilioSmsSender
from backend.outreach.contacts import ContactEmail, extract_contacts, to_dict
from backend.outreach.messages import OutreachContext, _questions, compose_email, greeting_name
from backend.outreach.service import (
    SCAM_LOCK_DETAIL,
    Channel,
    ListingOutreachAgent,
    OutreachSettings,
    _overall_status,
    flagged_as_scam,
)

Event = dict[str, Any]

SOURCE_LABEL = {
    "google": "your Google Calendar",
    "ical": "your calendar",
    "sample": "a sample work week",
}


def _step(step: str, title: str, detail: str) -> Event:
    return {"type": "step", "step": step, "status": "running", "title": title, "detail": detail}


def _done(step: str, detail: str, status: str = "done") -> Event:
    return {"type": "step", "step": step, "status": status, "detail": detail}


def _log(step: str, text: str, kind: str = "info") -> Event:
    return {"type": "log", "step": step, "text": text, "kind": kind}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _recipient(to: Optional[str], intended: Optional[str]) -> str:
    """'maria@x.gr', or 'maria@x.gr (demo redirect to team@y.com)' when overridden."""
    if intended and to and to != intended:
        return f"{intended} (demo redirect to {to})"
    return to or intended or "the landlord"


def _listing_line(listing: dict[str, Any]) -> str:
    bits = []
    if listing.get("sqm"):
        bits.append(f"{listing['sqm']} m²")
    if listing.get("price"):
        bits.append(f"€{listing['price']}/mo")
    if listing.get("floor"):
        bits.append(f"{listing['floor']} floor" if "floor" not in str(listing["floor"]).lower() else listing["floor"])
    where = listing.get("location") or listing.get("title")
    return " · ".join(([where] if where else []) + bits) or str(listing.get("url") or "the listing")


async def stream_listing_outreach(
    listing: Any,
    context: OutreachContext,
    *,
    calendar_url: Optional[str] = None,
    channels: Optional[list[Channel]] = None,
    force_dry_run: bool = False,
    demo: bool = False,
    settings: Optional[OutreachSettings] = None,
    sms: Optional[TwilioSmsSender] = None,
    email: Optional[ResendEmailSender] = None,
    client: Optional[httpx.AsyncClient] = None,
    now: Optional[datetime] = None,
) -> AsyncIterator[Event]:
    """Contacts one landlord, yielding progress events. `demo` listings are never sent."""
    listing = to_dict(listing)
    scam_locked = flagged_as_scam(listing)
    settings = (settings or OutreachSettings.from_env()).model_copy()
    settings.dry_run = settings.dry_run or force_dry_run or demo or scam_locked
    chosen = [c for c in (channels or settings.channels) if c in settings.channels]
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=20.0)

    try:
        # 1. Brief -------------------------------------------------------------------------
        yield _step("brief", "Reading the listing", "Collecting what the landlord needs to know")
        yield _log("brief", f"Listing: {_listing_line(listing)}")
        if scam_locked:
            risk = listing.get("scam_risk_pct")
            yield _log(
                "brief",
                "Oumi Iris flagged this listing as a possible scam"
                + (f" ({risk}% risk)" if risk is not None else "")
                + ": the e-mail will be drafted but not sent",
                "warn",
            )
        user = context.user
        yield _log("brief", f"Writing on behalf of {user.name}" + (f" <{user.email}>" if user.email else ""))
        questions = _questions(listing, context)
        if context.questions is not None and not questions:
            yield _log("brief", "You cleared the questions: asking only for a viewing", "ok")
        elif context.questions:
            ranker = {q.strip().lower() for q in listing.get("missing_info") or [] if isinstance(q, str)}
            yours = [q for q in questions if q.lower() not in ranker]
            yield _log(
                "brief",
                f"{_plural(len(questions), 'question')} approved by you"
                + (f", {len(yours)} of them your own" if yours else ""),
                "ok",
            )
            for q in yours[:3]:
                yield _log("brief", f"Your question: {q}")
        else:
            source = "the ranker" if listing.get("missing_info") else "the default checklist"
            yield _log("brief", f"{_plural(len(questions), 'open question')} from {source}")
        yield _done("brief", "Listing and profile loaded")

        # 2. Calendar ----------------------------------------------------------------------
        yield _step("calendar", "Checking your calendar", "Looking for free evenings and weekend slots")
        if context.viewing_windows:
            yield _log("calendar", "Using the viewing windows you provided", "ok")
            windows = list(context.viewing_windows)
            for w in windows:
                yield _log("calendar", f"Free: {w}", "ok")
            yield _done("calendar", f"{len(windows)} viewing windows ready")
        else:
            connected = bool((calendar_url or "").strip() or os.getenv("GOOGLE_CALENDAR_ICS_URL", "").strip())
            yield (
                _log("calendar", "Connecting to your Google Calendar (iCal feed)")
                if connected
                else _log("calendar", "No calendar connected: using a sample work week", "warn")
            )
            availability: Availability = await check_availability(calendar_url, http, now=now)
            if availability.error:
                yield _log("calendar", f"{availability.error}: falling back to a sample work week", "warn")
            yield _log(
                "calendar",
                f"Read {availability.events} events from {SOURCE_LABEL[availability.source]}, "
                f"{availability.window_start:%a} {availability.window_start.day} {availability.window_start:%b}"
                f" to {availability.window_end:%a} {availability.window_end.day} {availability.window_end:%b}",
            )
            for conflict in availability.conflicts[:3]:
                yield _log("calendar", f"Busy {conflict}", "warn")
            windows = [s.label for s in availability.slots]
            for w in windows:
                yield _log("calendar", f"Free: {w}", "ok")
            yield _done(
                "calendar",
                f"Found {len(windows)} free viewing slot{'' if len(windows) == 1 else 's'}"
                if windows
                else "No free slot this week: asking the landlord to suggest a time",
            )
            context = context.model_copy(update={"viewing_windows": windows})

        # 3. Contact -----------------------------------------------------------------------
        yield _step("contact", "Verifying the landlord's contact", "Checking the e-mail on the listing")
        contacts = extract_contacts(listing)
        if demo and not contacts.email and listing.get("agent_email"):
            # Demo listings use placeholder addresses the extractor rejects; nothing is sent anyway.
            contacts.emails.append(ContactEmail(address=str(listing["agent_email"]), source="agent_email"))
            yield _log("contact", "Demo listing: placeholder address, nothing will be sent", "warn")
        if contacts.email:
            yield _log("contact", f"Found {contacts.email} (from {contacts.emails[0].source})", "ok")
            yield _log("contact", "Portal and no-reply addresses filtered out")
            name = greeting_name(contacts.name)
            yield _log(
                "contact",
                f"Greeting the landlord as {name}" if name else "Agency listing: using a neutral greeting",
            )
            if settings.override_email and not settings.dry_run:
                yield _log("contact", f"Demo safety: delivering to {settings.override_email} instead", "warn")
            yield _done("contact", f"Landlord reachable at {contacts.email}")
        else:
            yield _log("contact", "No usable e-mail address on the listing", "warn")
            yield _done("contact", "No e-mail address to contact", status="failed")

        if "email" not in chosen:
            yield _log("contact", "E-mail outreach is disabled on the server (OUTREACH_CHANNELS)", "warn")

        # 4. Draft -------------------------------------------------------------------------
        if contacts.email and "email" in chosen:
            yield _step("draft", "Writing the e-mail", "Composing the viewing request")
            content = compose_email(listing, contacts.name, context)
            n = len(context.viewing_windows)
            yield _log(
                "draft",
                f"Proposing {n} viewing slot{'' if n == 1 else 's'} from your calendar"
                if n
                else "Asking the landlord to suggest a viewing time",
            )
            if questions:
                yield _log("draft", f"Adding {_plural(len(questions), 'question')} for the landlord")
            if user.email:
                yield _log("draft", "Reply-To set to your address, so the landlord answers you directly")
            yield {
                "type": "draft",
                "channel": "email",
                "to": contacts.email,
                "subject": content.subject,
                "body": content.text,
            }
            yield _done("draft", "E-mail drafted")

        # 5. Send --------------------------------------------------------------------------
        agent = ListingOutreachAgent(
            listing, context, chosen, settings,
            sms or TwilioSmsSender.from_env(), email or ResendEmailSender.from_env(),
        )
        attempts = []
        if contacts.has_contact and chosen:
            yield _step(
                "send",
                "Sending the e-mail",
                "Held back: Oumi Iris flagged this listing"
                if scam_locked
                else ("Composed for review only (dry run)" if settings.dry_run else "Handing the e-mail to Resend"),
            )
            attempts = await agent.send(http, contacts)
            for a in attempts:
                label = "E-mail" if a.channel == "email" else "SMS"
                who = _recipient(a.to, a.intended_to)
                if a.status == "sent":
                    provider = f" (id {a.provider_id})" if a.provider_id else ""
                    yield _log("send", f"{label} delivered to {who}{provider}", "ok")
                elif a.status == "dry_run":
                    reason = "Oumi Iris scam lock" if a.detail == SCAM_LOCK_DETAIL else "dry run"
                    yield _log("send", f"{label} to {who} composed but not sent ({reason})", "warn")
                elif a.status == "skipped":
                    yield _log("send", f"{label} skipped: {a.detail}", "warn")
                else:
                    yield _log("send", f"{label} failed: {a.detail}", "warn")
            status = _overall_status(attempts)
            yield _done(
                "send",
                {
                    "contacted": "E-mail sent to the landlord",
                    "dry_run": "Composed, not sent (Oumi Iris scam lock)"
                    if scam_locked
                    else "Composed, not sent (dry run)",
                    "no_contact": "Nothing to send",
                    "failed": "Sending failed",
                }[status],
                status="failed" if status == "failed" else "done",
            )
        result = agent.result(contacts, attempts)
        yield {
            "type": "result",
            **result.model_dump(mode="json"),
            "dry_run": settings.dry_run,
            "viewing_windows": list(context.viewing_windows),
        }
    finally:
        if owns_client:
            await http.aclose()
