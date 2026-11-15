"""Live outreach agent: the same work as `ListingOutreachAgent`, narrated step by step.

`stream_listing_outreach()` is an async generator of progress events (format in
backend/streaming.py) that the UI renders while the agent works on one approved listing:

    brief     read the listing + the user's profile
    calendar  check the user's calendar and pick free viewing slots (availability.py)
    contact   verify the landlord's e-mail (portal / no-reply addresses are filtered out)
    draft     compose the e-mail (emits a `draft` event with the exact subject + body)
    send      deliver via Resend (or report the dry run), then a final `result` event

With the "call" channel the agent phones the landlord instead of e-mailing them (one or the
other, never both): after `calendar` it runs a `call` step that writes the voice agent's brief
(a `call` event with the system prompt + opening line), which the browser hands to Vapi.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import httpx

from backend.outreach.availability import Availability, check_availability
from backend.outreach.channels import ResendEmailSender, TwilioSmsSender
from backend.outreach.contacts import ContactEmail, ExtractedContacts, extract_contacts, to_dict
from backend.outreach.messages import OutreachContext, _questions, compose_email, greeting_name
from backend.outreach.service import (
    SCAM_LOCK_DETAIL,
    Channel,
    ChannelAttempt,
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


# The UI shows this service's logo next to the step / line (see backend/streaming.py).
GOOGLE_CALENDAR = "google_calendar"
CALENDAR = "calendar"


def _step(step: str, title: str, detail: str, sources: Optional[list[str]] = None) -> Event:
    event: Event = {"type": "step", "step": step, "status": "running", "title": title, "detail": detail}
    if sources:
        event["sources"] = sources
    return event


def _done(step: str, detail: str, status: str = "done", sources: Optional[list[str]] = None) -> Event:
    event: Event = {"type": "step", "step": step, "status": status, "detail": detail}
    if sources is not None:
        event["sources"] = sources
    return event


def _log(step: str, text: str, kind: str = "info", source: Optional[str] = None) -> Event:
    event: Event = {"type": "log", "step": step, "text": text, "kind": kind}
    if source:
        event["source"] = source
    return event


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


def _call_brief(
    listing: dict[str, Any], contacts: ExtractedContacts, context: OutreachContext, questions: list[str]
) -> tuple[str, str]:
    """The voice agent's system prompt and opening line for a call to this landlord.

    The landlord may have several flats on offer, so the apartment is always named by its area
    and price (and size, floor when known), never by the price alone.
    """
    user = context.user
    area = str(listing.get("location") or "").strip()
    size = f"{listing['sqm']} square metre " if listing.get("sqm") else ""
    price = f"{listing['price']} euros a month" if listing.get("price") else ""
    apartment = f"{size}apartment" + (f" in {area}" if area else "") + (f" for {price}" if price else "")
    facts = [
        f"Area: {area}" if area else None,
        f"Monthly rent: {price}" if price else None,
        f"Size: {listing['sqm']} m²" if listing.get("sqm") else None,
        f"Floor: {listing['floor']}" if listing.get("floor") else None,
        f"Listing: {listing['url']}" if listing.get("url") else None,
    ]
    landlord = greeting_name(contacts.name)
    windows = list(context.viewing_windows)[:3]
    asks = "\n".join(f"- {q}" for q in questions) or "- (no open questions: only ask for a viewing)"
    slots = (
        "Propose one of these viewing slots from the client's calendar: " + "; ".join(windows) + "."
        if windows
        else "The client's calendar has no free slot this week: ask the landlord to suggest a viewing time."
    )
    prompt = (
        f"You are Domus AI, a polite, friendly real estate assistant on a phone call with "
        f"{landlord or 'the landlord'} about their {apartment}. "
        f"You are calling on behalf of your client, {user.name}, who is looking to rent it.\n\n"
        "The apartment:\n" + "\n".join(f"- {f}" for f in facts if f) + "\n\n"
        "Goals, in order:\n"
        "1. Make sure the landlord knows which apartment you mean: always refer to it by its area "
        "and price (never by the price alone), then confirm it is still available.\n"
        f"2. Ask these open questions, one at a time, and listen to each answer:\n{asks}\n"
        f"3. {slots}\n"
        f"4. Confirm what was agreed, say {user.name} will follow up"
        + (f" by e-mail at {user.email}" if user.email else "")
        + ", thank them and say goodbye.\n\n"
        "Keep every turn short and natural (one or two sentences), never invent facts about the "
        "client or the apartment, and if the apartment is no longer available, thank them and end the call."
    )
    first = (
        f"Hello{f' {landlord}' if landlord else ''}! I'm calling on behalf of {user.name} about your "
        f"{apartment}. Is it still available?"
    )
    return prompt, first


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
    # A voice call replaces the e-mail: the agent contacts the landlord one way, never both.
    # Without an explicit request the agent e-mails (calls are always asked for by the UI).
    calling = bool(channels) and "call" in channels
    call_enabled = "call" in settings.channels
    chosen = ["call"] if calling else [c for c in chosen if c != "call"]
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
                + (": the call will not be placed" if calling else ": the e-mail will be drafted but not sent"),
                "warn",
            )
        user = context.user
        yield _log(
            "brief",
            f"{'Calling' if calling else 'Writing'} on behalf of {user.name}"
            + (f" <{user.email}>" if user.email else ""),
        )
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
        feed = (calendar_url or "").strip() or os.getenv("GOOGLE_CALENDAR_ICS_URL", "").strip()
        google = GOOGLE_CALENDAR if "google.com" in feed else None
        # While the agent looks at the calendar the UI shows the Google Calendar logo (when that is
        # the feed) next to a generic calendar icon.
        yield _step(
            "calendar", "Checking your calendar", "Looking for free evenings and weekend slots",
            sources=[s for s in (google, CALENDAR) if s],
        )
        if context.viewing_windows:
            yield _log("calendar", "Using the viewing windows you provided", "ok")
            windows = list(context.viewing_windows)
            for w in windows:
                yield _log("calendar", f"Free: {w}", "ok")
            yield _done("calendar", f"{len(windows)} viewing windows ready")
        else:
            if feed:
                yield _log(
                    "calendar",
                    "Connecting to your Google Calendar (iCal feed)" if google else "Connecting to your calendar (iCal feed)",
                    source=google,
                )
            else:
                yield _log("calendar", "No calendar connected: using a sample work week", "warn")
            availability: Availability = await check_availability(calendar_url, http, now=now)
            if availability.error:
                yield _log("calendar", f"{availability.error}: falling back to a sample work week", "warn")
            yield _log(
                "calendar",
                f"Read {availability.events} events from {SOURCE_LABEL[availability.source]}, "
                f"{availability.window_start:%a} {availability.window_start.day} {availability.window_start:%b}"
                f" to {availability.window_end:%a} {availability.window_end.day} {availability.window_end:%b}",
                source=GOOGLE_CALENDAR if availability.source == "google" else None,
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
                # Keep the Google Calendar logo only if the feed was actually read.
                sources=[GOOGLE_CALENDAR, CALENDAR] if availability.source == "google" else [CALENDAR],
            )
            context = context.model_copy(update={"viewing_windows": windows})

        agent = ListingOutreachAgent(
            listing, context, chosen, settings,
            sms or TwilioSmsSender.from_env(), email or ResendEmailSender.from_env(),
        )

        # 3'. Voice call (instead of contact -> draft -> send) -------------------------------
        if calling:
            yield _step("call", "Calling the landlord", "Preparing the voice agent (Vapi)")
            contacts = extract_contacts(listing)
            phone = contacts.sms_phone or (contacts.phones[0].e164 if contacts.phones else None)
            who = greeting_name(contacts.name) or "the landlord"
            yield _log(
                "call",
                f"Calling {who}" + (f" ({phone} on the listing)" if phone else " (no phone number on the listing)"),
            )
            yield _log("call", "Live web call: you play the landlord through your microphone", "warn")
            if not call_enabled:
                yield _log("call", "Voice calls are disabled on the server (OUTREACH_CHANNELS)", "warn")
                yield _done("call", "Voice calls are disabled on the server", status="failed")
                attempt = ChannelAttempt(
                    channel="call", status="skipped", intended_to=phone,
                    detail="Voice calls are disabled on the server (add call to OUTREACH_CHANNELS)",
                )
            elif scam_locked:
                yield _log("call", "Oumi Iris scam lock: the call is not placed", "warn")
                yield _done("call", "Held back: Oumi Iris flagged this listing", status="failed")
                attempt = ChannelAttempt(channel="call", status="dry_run", intended_to=phone, detail=SCAM_LOCK_DETAIL)
            else:
                prompt, first = _call_brief(listing, contacts, context, questions)
                n = len(context.viewing_windows)
                yield _log(
                    "call",
                    f"Voice brief ready: {_plural(len(questions), 'question')}, "
                    + (f"{_plural(n, 'viewing slot')} from your calendar" if n else "asking for a viewing time"),
                    "ok",
                )
                yield {
                    "type": "call",
                    "to": phone,
                    "landlord": contacts.name,
                    "system_prompt": prompt,
                    "first_message": first,
                    "questions": questions,
                    "viewing_windows": list(context.viewing_windows),
                }
                yield _done("call", "Voice agent on the line")
                attempt = ChannelAttempt(
                    channel="call",
                    status="sent",
                    to=phone,
                    intended_to=phone,
                    provider_id="vapi-web-call",
                    detail="Live voice call started in the browser",
                    body=first,
                )
            result = agent.result(contacts, [attempt])
            yield {
                "type": "result",
                **result.model_dump(mode="json"),
                "dry_run": settings.dry_run,
                "viewing_windows": list(context.viewing_windows),
            }
            return

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
