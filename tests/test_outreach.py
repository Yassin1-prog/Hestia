import asyncio
import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.outreach import (
    OutreachContext,
    OutreachSettings,
    ResendEmailSender,
    TwilioSmsSender,
    UserContact,
    compose_email,
    compose_sms,
    extract_contacts,
    run_outreach,
)
from backend.outreach.contacts import normalize_phone

# Shaped like `PropertyDetails` from backend/agent.py.
LISTING_MOBILE_AND_EMAIL = {
    "url": "https://www.spitogatos.gr/aggelia/1234567890",
    "price": 600,
    "sqm": 65,
    "floor": "2nd",
    "features": ["pet friendly", "bright"],
    "agent_name": "Maria Papadopoulou",
    "agent_phone": "Τηλ: 691 234 5678",
    "agent_email": "Maria.P@Gmail.com",
    "missing_info": ["Are pets allowed?", "Is there an elevator?"],
    "agentic_score": 9,
    "score_reason": "Bright, pet friendly, within budget.",
}
LISTING_LANDLINE_ONLY = {
    "url": "https://www.spitogatos.gr/aggelia/2222222222",
    "price": 550,
    "sqm": 50,
    "agent_phone": "210 123 4567",
    "agent_email": None,
    "agentic_score": 7,
    "score_reason": "Good price.",
}
LISTING_NO_CONTACT = {"url": "https://www.spitogatos.gr/aggelia/3", "agent_phone": None, "agentic_score": 5}

CTX = OutreachContext(
    user=UserContact(name="Nikos", email="nikos@example.org", phone="+306900000000"),
    viewing_windows=["Mon 18:00-20:00", "Sat 10:00-13:00", "Sun 12:00-14:00"],
)


# ---------------------------------------------------------------------------
# Contact extraction
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("6912345678", ("+306912345678", "mobile")),
        ("691 234 5678", ("+306912345678", "mobile")),
        ("+30 691-234-5678", ("+306912345678", "mobile")),
        ("0030 6912345678", ("+306912345678", "mobile")),
        ("306912345678", ("+306912345678", "mobile")),
        ("210 123 4567", ("+302101234567", "landline")),
        ("+44 7700 900123", ("+447700900123", "unknown")),
        ("600", None),
        ("12345", None),
        ("+30 691 234", None),  # Greek number with too few digits.
        ("1234567890", None),  # 10 digits but not a Greek prefix.
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_extract_contacts_from_structured_fields():
    contacts = extract_contacts(LISTING_MOBILE_AND_EMAIL)
    assert contacts.name == "Maria Papadopoulou"
    assert contacts.sms_phone == "+306912345678"
    assert contacts.email == "maria.p@gmail.com"
    assert contacts.phones[0].source == "agent_phone"
    # Listing-ID digits in the URL must never be mistaken for a phone number.
    assert all("1234567890" not in p.e164 for p in contacts.phones)


def test_extract_contacts_falls_back_to_free_text_and_filters_portal_contacts():
    response = {
        "url": "https://www.xe.gr/property/d/6999999999",
        "agent_phone": None,
        "score_reason": "Call the owner on 6987 654 321 or 210-987-6543, mail owner@yahoo.gr. "
        "Portal support: info@spitogatos.gr, noreply@agency.gr, logo@2x.png",
    }
    contacts = extract_contacts(response)
    assert [p.e164 for p in contacts.phones] == ["+306987654321", "+302109876543"]
    assert [p.kind for p in contacts.phones] == ["mobile", "landline"]
    assert [e.address for e in contacts.emails] == ["owner@yahoo.gr"]


def test_extract_contacts_handles_multiple_numbers_in_one_field_and_raw_text():
    contacts = extract_contacts({"agent_phone": "210 1234567 / 6911111111"})
    assert contacts.sms_phone == "+306911111111"
    assert {p.e164 for p in contacts.phones} == {"+302101234567", "+306911111111"}

    from_text = extract_contacts("Landlord: Kostas, 6922222222, kostas@mail.gr")
    assert from_text.sms_phone == "+306922222222"
    assert from_text.email == "kostas@mail.gr"


def test_landline_is_not_sms_capable():
    contacts = extract_contacts(LISTING_LANDLINE_ONLY)
    assert contacts.has_contact is True
    assert contacts.sms_phone is None


# ---------------------------------------------------------------------------
# Message composition
# ---------------------------------------------------------------------------
def test_compose_messages_include_listing_windows_questions_and_disclosure():
    sms = compose_sms(LISTING_MOBILE_AND_EMAIL, "Maria", CTX)
    assert "Hello Maria," in sms
    assert LISTING_MOBILE_AND_EMAIL["url"] in sms
    assert "65 m², €600/month" in sms
    assert "Mon 18:00-20:00 or Sat 10:00-13:00" in sms
    assert "Sun 12:00-14:00" not in sms  # SMS keeps only the first 2 windows.
    assert "nikos@example.org" in sms
    assert "relocation assistant" in sms

    email = compose_email(LISTING_MOBILE_AND_EMAIL, "Maria", CTX)
    assert email.subject == "Viewing request: 65 m², €600/month apartment"
    assert "- Are pets allowed?" in email.text
    assert "- Sun 12:00-14:00" in email.text
    assert "<li>Is there an elevator?</li>" in email.html


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Maria Papadopoulou", "Maria Papadopoulou"),
        ("Νίκος Παπαδόπουλος", "Νίκος Παπαδόπουλος"),
        # Real contact names seen on Spitogatos: agencies → plain "Hello,".
        ("MEGA HOUSE REAL ESTATE (Π. ΠΑΥΛΙΔΗΣ)", None),
        ("ΠΑΠΑΝΑΣΤΑΣΙΟΥ ΝΙΚΟΣ (RE/MAX CARE)", None),
        ("TZELI HOME (ΚΑΡΑΣΑΒΒΙΔΗΣ ΓΙΩΡΓΟΣ)", None),
        ("ΚΑΡΑΣΑΒΒΙΔΗΣ ΓΙΩΡΓΟΣ", None),
        ("Athens Properties", None),
        ("", None),
        (None, None),
    ],
)
def test_greeting_name_skips_agencies(name, expected):
    from backend.outreach.messages import greeting_name

    assert greeting_name(name) == expected


def test_agency_listing_gets_plain_greeting():
    sms = compose_sms(LISTING_MOBILE_AND_EMAIL, "MEGA HOUSE REAL ESTATE (Π. ΠΑΥΛΙΔΗΣ)", CTX)
    assert sms.startswith("Hello, my name is Nikos")


def test_compose_greek_and_default_questions():
    ctx = CTX.model_copy(update={"language": "el", "viewing_windows": []})
    sms = compose_sms(LISTING_LANDLINE_ONLY, None, ctx)
    assert sms.startswith("Καλησπέρα σας,")
    assert "σε ώρα που σας βολεύει" in sms
    email = compose_email(LISTING_LANDLINE_ONLY, None, ctx)
    assert "Είναι ακόμα διαθέσιμο το διαμέρισμα;" in email.text  # default question


# ---------------------------------------------------------------------------
# Outreach orchestration
# ---------------------------------------------------------------------------
TWILIO = TwilioSmsSender("ACtest", "secret", from_number="+15550001111")
RESEND = ResendEmailSender("re_test", "Agent <agent@relocate.test>")


def _run(listings, settings, handler, channels=("sms", "email"), **kwargs):
    settings = settings.model_copy(update={"channels": list(channels)})  # Enable both for these tests.

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await run_outreach(
                listings, CTX, channels, settings=settings, sms=TWILIO, email=RESEND, client=client, **kwargs
            )

    return asyncio.run(go())


def _no_http(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Dry run must not call {request.url}")


def test_dry_run_sends_nothing_and_reports_per_channel_status():
    batch = _run(
        [LISTING_MOBILE_AND_EMAIL, LISTING_LANDLINE_ONLY, LISTING_NO_CONTACT],
        OutreachSettings(dry_run=True),
        _no_http,
    )
    assert batch.dry_run is True
    first, landline, none = batch.results

    assert first.status == "dry_run"
    assert {a.channel: a.status for a in first.attempts} == {"sms": "dry_run", "email": "dry_run"}
    assert first.attempts[0].to == "+306912345678"
    assert first.attempts[1].subject.startswith("Viewing request")

    assert landline.status == "no_contact"
    assert "landline" in landline.attempts[0].detail

    assert none.status == "no_contact"
    assert batch.no_contact == 2


def test_disabled_channel_is_dropped_even_if_requested(monkeypatch):
    monkeypatch.delenv("OUTREACH_CHANNELS", raising=False)
    assert OutreachSettings.from_env().channels == ["sms", "email"]  # Both on by default.

    monkeypatch.setenv("OUTREACH_CHANNELS", "sms")
    settings = OutreachSettings.from_env()
    assert settings.channels == ["sms"]

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(_no_http)) as client:
            return await run_outreach(
                [LISTING_MOBILE_AND_EMAIL], CTX, ["sms", "email"],
                settings=settings.model_copy(update={"dry_run": True}),
                sms=TWILIO, email=RESEND, client=client,
            )

    batch = asyncio.run(go())
    assert batch.channels == ["sms"]
    assert [a.channel for a in batch.results[0].attempts] == ["sms"]


def test_channels_env_parsing(monkeypatch):
    monkeypatch.setenv("OUTREACH_CHANNELS", " SMS, email ,fax")
    assert OutreachSettings.from_env().channels == ["sms", "email"]


def test_request_cannot_disable_server_dry_run_but_can_force_it():
    batch = _run([LISTING_MOBILE_AND_EMAIL], OutreachSettings(dry_run=False), _no_http, force_dry_run=True)
    assert batch.dry_run is True


def test_live_send_calls_twilio_and_resend():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "api.twilio.com":
            assert request.url.path == "/2010-04-01/Accounts/ACtest/Messages.json"
            assert request.headers["Authorization"] == "Basic " + base64.b64encode(b"ACtest:secret").decode()
            form = parse_qs(request.content.decode())
            assert form["To"] == ["+306912345678"]
            assert form["From"] == ["+15550001111"]
            assert "Hello Maria Papadopoulou," in form["Body"][0]
            return httpx.Response(201, json={"sid": "SM123", "status": "queued"})
        if request.url.host == "api.resend.com":
            assert request.headers["Authorization"] == "Bearer re_test"
            body = json.loads(request.content)
            assert body["to"] == ["maria.p@gmail.com"]
            assert body["from"] == "Agent <agent@relocate.test>"
            assert body["reply_to"] == "nikos@example.org"
            assert "<ul>" in body["html"]
            return httpx.Response(200, json={"id": "email_123"})
        raise AssertionError(f"Unexpected call {request.url}")

    batch = _run([LISTING_MOBILE_AND_EMAIL], OutreachSettings(dry_run=False), handler)
    result = batch.results[0]
    assert len(calls) == 2
    assert result.status == "contacted"
    assert batch.contacted == 1
    assert {a.channel: a.provider_id for a in result.attempts} == {"sms": "SM123", "email": "email_123"}


def test_override_redirects_messages_to_demo_recipient():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.twilio.com":
            seen["sms"] = parse_qs(request.content.decode())["To"][0]
            return httpx.Response(201, json={"sid": "SM1", "status": "queued"})
        seen["email"] = json.loads(request.content)["to"][0]
        return httpx.Response(200, json={"id": "e1"})

    settings = OutreachSettings(dry_run=False, override_phone="+306900000001", override_email="demo@team.test")
    result = _run([LISTING_MOBILE_AND_EMAIL], settings, handler).results[0]
    assert seen == {"sms": "+306900000001", "email": "demo@team.test"}
    assert {a.intended_to for a in result.attempts} == {"+306912345678", "maria.p@gmail.com"}


def test_provider_error_is_reported_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.twilio.com":
            return httpx.Response(400, json={"code": 21211, "message": "Invalid 'To' Phone Number"})
        return httpx.Response(200, json={"id": "e1"})

    result = _run([LISTING_MOBILE_AND_EMAIL], OutreachSettings(dry_run=False), handler).results[0]
    sms, email = result.attempts
    assert sms.status == "failed" and "Invalid 'To' Phone Number" in sms.detail
    assert email.status == "sent"
    assert result.status == "contacted"  # At least one channel reached the landlord.


def test_missing_credentials_fail_with_actionable_message():
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(_no_http)) as client:
            return await run_outreach(
                [LISTING_MOBILE_AND_EMAIL], CTX, ["sms"],
                settings=OutreachSettings(dry_run=False),
                sms=TwilioSmsSender(None, None), email=ResendEmailSender(None, None), client=client,
            )

    result = asyncio.run(go()).results[0]
    assert result.status == "failed"
    assert "TWILIO_ACCOUNT_SID" in result.attempts[0].detail


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_api_health_and_preview(monkeypatch):
    monkeypatch.setenv("OUTREACH_DRY_RUN", "false")  # Preview must still never send.
    client = TestClient(app)

    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert "dry_run" in health["outreach"]

    extract = client.post("/api/outreach/extract", json={"properties": [LISTING_MOBILE_AND_EMAIL]})
    assert extract.status_code == 200
    assert extract.json()[0]["contacts"]["sms_phone"] == "+306912345678"

    preview = client.post(
        "/api/outreach/preview",
        json={
            "user": {"name": "Nikos", "email": "nikos@example.org"},
            "properties": [LISTING_MOBILE_AND_EMAIL],
            "viewing_windows": ["Mon 18:00-20:00"],
            "language": "el",
        },
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["dry_run"] is True
    assert body["results"][0]["status"] == "dry_run"
    assert body["results"][0]["attempts"][0]["body"].startswith("Καλησπέρα σας Maria Papadopoulou,")


def test_api_send_rejects_empty_selection():
    response = TestClient(app).post("/api/outreach/send", json={"user": {"name": "N"}, "properties": []})
    assert response.status_code == 422
