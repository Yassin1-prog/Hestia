"""Live agent streams: calendar availability, the narrated outreach agent and the NDJSON endpoints."""

import asyncio
import json
from datetime import datetime

import httpx
from fastapi.testclient import TestClient

from backend.main import app
from backend.outreach import OutreachContext, OutreachSettings, ResendEmailSender, UserContact
from backend.outreach.availability import (
    TIMEZONE,
    check_availability,
    find_free_slots,
    parse_ics,
    sample_week,
)
from backend.outreach.live import stream_listing_outreach

# Sunday 15 Nov 2026, 12:00 Athens time.
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=TIMEZONE)

LISTING = {
    "url": "https://www.spitogatos.gr/aggelia/123",
    "price": 600,
    "sqm": 65,
    "floor": "2nd",
    "features": [],
    "agent_name": "Maria",
    "agent_phone": None,
    "agent_email": "maria@gmail.com",
    "missing_info": ["Are pets allowed?"],
    "agentic_score": 8,
    "score_reason": "Good match.",
}
CTX = OutreachContext(user=UserContact(name="Nikos", email="nikos@example.org"))

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:1
DTSTART;TZID=Europe/Athens:20261116T180000
DTEND;TZID=Europe/Athens:20261116T200000
SUMMARY:Yoga
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;TZID=Europe/Athens:20261117T183000
DTEND;TZID=Europe/Athens:20261117T193000
RRULE:FREQ=DAILY;COUNT=2
SUMMARY:Standup
END:VEVENT
BEGIN:VEVENT
UID:3
DTSTART;VALUE=DATE:20261119
DTEND;VALUE=DATE:20261120
TRANSP:TRANSPARENT
SUMMARY:Birthday
END:VEVENT
END:VCALENDAR
"""


def collect(gen):
    async def run():
        return [e async for e in gen]

    return asyncio.run(run())


def test_sample_week_skips_busy_evenings_and_spreads_slots():
    slots, conflicts = find_free_slots(sample_week(NOW.date()), NOW)
    labels = [s.label for s in slots]
    # Mon 16: gym 18:00-19:30 leaves < 1h, Tue 17 free from 18:00, Wed 18: dinner, Thu 19 free.
    assert labels == ["Tue 17 Nov, 18:00-20:00", "Thu 19 Nov, 18:00-20:00", "Fri 20 Nov, 18:00-20:00"]
    assert any("Gym" in c for c in conflicts) and any("Dinner" in c for c in conflicts)


def test_parse_ics_expands_recurrences_and_ignores_free_events():
    start = datetime(2026, 11, 15, tzinfo=TIMEZONE)
    end = datetime(2026, 11, 23, tzinfo=TIMEZONE)
    blocks = parse_ics(ICS, start, end)
    assert [b.title for b in blocks] == ["Yoga", "Standup", "Standup"]  # Birthday is TRANSPARENT.
    slots, _ = find_free_slots(blocks, NOW)
    # Mon: yoga until 20:00 → too late. Tue/Wed: standup 18:30 blocks the start, 20:00-20:30 too short.
    assert slots[0].label.startswith("Thu 19 Nov, 18:00")


def test_check_availability_reads_calendar_and_falls_back_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if "good" in str(request.url):
            return httpx.Response(200, content=ICS)
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            good = await check_availability("webcal://calendar.google.com/good.ics", client, now=NOW)
            bad = await check_availability("https://calendar.google.com/bad.ics", client, now=NOW)
            none = await check_availability(None, client, now=NOW)
        return good, bad, none

    good, bad, none = asyncio.run(run())
    assert good.source == "google" and good.events == 3 and good.error is None
    assert bad.source == "sample" and bad.error
    assert none.source == "sample" and none.error is None


def test_stream_outreach_dry_run_narrates_every_step():
    events = collect(
        stream_listing_outreach(
            LISTING,
            CTX,
            settings=OutreachSettings(dry_run=True, channels=["email"]),
            client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
            now=NOW,
        )
    )
    started = [e["step"] for e in events if e["type"] == "step" and e["status"] == "running"]
    assert started == ["brief", "calendar", "contact", "draft", "send"]
    draft = next(e for e in events if e["type"] == "draft")
    assert "Tue 17 Nov, 18:00-20:00" in draft["body"] and draft["to"] == "maria@gmail.com"
    result = events[-1]
    assert result["type"] == "result" and result["status"] == "dry_run"
    assert result["viewing_windows"][0] == "Tue 17 Nov, 18:00-20:00"


def test_stream_outreach_sends_with_resend():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "re_1"})

    events = collect(
        stream_listing_outreach(
            LISTING,
            CTX,
            settings=OutreachSettings(dry_run=False, channels=["email"]),
            email=ResendEmailSender(api_key="re_test", from_email="agent@example.org"),
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            now=NOW,
        )
    )
    assert len(sent) == 1 and sent[0]["to"] == ["maria@gmail.com"]
    assert events[-1]["status"] == "contacted"
    assert events[-1]["attempts"][0]["provider_id"] == "re_1"


def test_stream_outreach_demo_listing_is_never_sent():
    demo = {**LISTING, "agent_email": "eleni@example.com", "url": "https://x.gr/a?demo=1"}
    events = collect(
        stream_listing_outreach(
            demo,
            CTX,
            demo=True,
            settings=OutreachSettings(dry_run=False, channels=["email"]),
            client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
            now=NOW,
        )
    )
    assert events[-1]["status"] == "dry_run" and events[-1]["dry_run"] is True


def test_stream_outreach_without_email_reports_no_contact():
    events = collect(
        stream_listing_outreach(
            {**LISTING, "agent_email": None},
            CTX,
            settings=OutreachSettings(dry_run=True, channels=["email"]),
            client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
            now=NOW,
        )
    )
    assert any(e["type"] == "step" and e["step"] == "contact" and e["status"] == "failed" for e in events)
    assert not any(e["type"] == "draft" for e in events)
    assert events[-1]["status"] == "no_contact"


def test_api_outreach_stream_is_ndjson(monkeypatch):
    monkeypatch.setenv("OUTREACH_DRY_RUN", "true")
    monkeypatch.setenv("OUTREACH_CHANNELS", "email")
    with TestClient(app) as client:
        res = client.post(
            "/api/outreach/stream",
            json={"user": {"name": "Nikos", "email": "nikos@example.org"}, "properties": [LISTING]},
        )
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in res.text.splitlines() if line]
    assert lines[0]["type"] == "step" and lines[-1]["type"] == "result"


def test_api_search_stream_relays_progress_and_errors(monkeypatch):
    import backend.agent as agent

    def fake_run_search(request, emit=None, verbose=False):
        emit({"type": "step", "step": "understand", "status": "running", "title": "Reading", "detail": None})
        emit({"type": "log", "step": "understand", "text": "Area: Pangrati", "kind": "info"})
        return agent.SearchOutcome(properties=[LISTING], scanned=12, rejected=11)

    monkeypatch.setattr(agent, "run_search", fake_run_search)
    with TestClient(app) as client:
        res = client.post("/api/search/stream", json={"request": "Pangrati"})
    lines = [json.loads(line) for line in res.text.splitlines() if line]
    assert [e["type"] for e in lines] == ["step", "log", "result"]
    assert lines[-1]["stats"] == {"scanned": 12, "rejected": 11}

    def broken(request, emit=None, verbose=False):
        raise RuntimeError("Set GEMINI_API_KEY in .env")

    monkeypatch.setattr(agent, "run_search", broken)
    with TestClient(app) as client:
        res = client.post("/api/search/stream", json={"request": "Pangrati"})
    assert json.loads(res.text.splitlines()[-1]) == {"type": "error", "detail": "Set GEMINI_API_KEY in .env"}


def test_user_questions_override_ranker_questions_in_email():
    from backend.outreach import compose_email

    ctx = CTX.model_copy(update={"questions": ["Are pets allowed?", "Is there parking?", "is there parking? "]})
    body = compose_email(LISTING, "Maria", ctx).text
    assert "- Is there parking?" in body and body.count("parking") == 1

    events = collect(
        stream_listing_outreach(
            LISTING,
            ctx,
            settings=OutreachSettings(dry_run=True, channels=["email"]),
            client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
            now=NOW,
        )
    )
    texts = [e["text"] for e in events if e["type"] == "log"]
    assert "Your question: Is there parking?" in texts
    assert "Is there parking?" in next(e for e in events if e["type"] == "draft")["body"]


def test_reporter_agent_events_carry_hub():
    from backend.streaming import StepReporter

    seen = []
    StepReporter(seen.append).agent("inspect", "listing-1", "Agent 1", "running", "Opening", hub="Orchestrator")
    assert seen == [{
        "type": "agent", "step": "inspect", "agent": "listing-1", "label": "Agent 1",
        "status": "running", "detail": "Opening", "hub": "Orchestrator",
    }]


def test_cleared_questions_mean_viewing_request_only():
    from backend.outreach import compose_email

    body = compose_email(LISTING, "Maria", CTX.model_copy(update={"questions": []})).text
    assert "questions about the property" not in body and "pets" not in body
