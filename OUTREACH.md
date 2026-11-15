# Landlord Outreach — Contact Extraction + SMS / E-mail

> **Scope:** The step after the human approval gate. It takes the agent's response for each listing the user approved, **extracts the landlord's phone number and e-mail**, composes a viewing-request message, and **sends it by SMS (Twilio) and e-mail (Resend)**, with one agent per listing running in parallel.
> **Code:** [`backend/outreach/`](./backend/outreach/) · **Tests:** [`tests/test_outreach.py`](./tests/test_outreach.py)

---

## 1. Where it sits in the pipeline

```text
[backend/agent.py]      search → rank → deep-scrape top 3  →  PropertyDetails (agent response)
[backend/decision.py]   Oumi Iris: SAFE / POSSIBLY_SCAM
[frontend]              HUMAN APPROVAL GATE: user picks SAFE homes + name/e-mail/phone + viewing windows
          │
          ▼   POST /api/outreach/preview   (exact messages and recipients, nothing sent)
          ▼   POST /api/outreach/send      (user confirms)
[backend/outreach/]     one ListingOutreachAgent per approved listing, concurrently
    1. contacts.py   extract + normalize phone / e-mail from the agent response
    2. messages.py   compose SMS + e-mail (EN or EL)
    3. channels.py   Twilio SMS ‖ Resend e-mail (in parallel)
    4. service.py    per-channel attempt log → live status dashboard
```

## 2. Module layout

| File | Responsibility |
| :--- | :--- |
| `contacts.py` | `extract_contacts(response)` turns a `PropertyDetails` model, dict or raw string into an `ExtractedContacts` (name, E.164 phones with mobile/landline type, e-mails, plus `sms_phone` / `email` shortcuts). |
| `messages.py` | `compose_sms()` / `compose_email()` use deterministic EN/EL templates that include the listing, the ranker's missing-info questions, viewing windows, the user's contact details and an AI-assistant disclosure. |
| `channels.py` | `TwilioSmsSender` and `ResendEmailSender`, thin async REST adapters over `httpx`. |
| `service.py` | `ListingOutreachAgent` (one per listing) and `run_outreach()` (runs all of them concurrently, with a concurrency limit). Also holds the safety settings. |

## 3. API

All three endpoints take agent responses (`PropertyDetails` JSON from `/api/search`) as `properties`.

| Endpoint | Purpose |
| :--- | :--- |
| `POST /api/outreach/extract` | `{properties}` → the contacts found for each listing. Use it to show "📞 / ✉️ found" badges on cards. |
| `POST /api/outreach/preview` | Same body as `/send`. Composes every message and resolves every recipient, and **never sends**. Use it on the approval screen. |
| `POST /api/outreach/send` | Sends for real (unless dry-run is on, see §5). |
| `GET /api/health` | Now also reports `outreach.dry_run`, `sms_configured`, `email_configured`. |

Request body for `/preview` and `/send`:

```json
{
  "user": { "name": "Nikos", "email": "nikos@example.org", "phone": "+30 690 000 0000" },
  "properties": [ { "url": "...", "price": 600, "sqm": 65, "agent_name": "Maria",
                    "agent_phone": "691 234 5678", "agent_email": "maria@gmail.com",
                    "missing_info": ["Are pets allowed?"] } ],
  "viewing_windows": ["Mon 18 Nov, 18:00-20:00", "Sat 23 Nov, 10:00-13:00"],
  "channels": ["sms", "email"],
  "language": "en",
  "note": null,
  "dry_run": false
}
```

Response (abridged):

```json
{
  "dry_run": true,
  "contacted": 0, "failed": 0, "no_contact": 0,
  "results": [{
    "url": "...",
    "status": "dry_run",                        // contacted | dry_run | no_contact | failed
    "contacts": { "name": "Maria", "sms_phone": "+306912345678", "email": "maria@gmail.com",
                  "phones": [{ "e164": "+306912345678", "kind": "mobile", "source": "agent_phone", ... }], ... },
    "attempts": [
      { "channel": "sms",   "status": "dry_run", "to": "+306912345678", "intended_to": "+306912345678",
        "provider_id": null, "body": "Hello Maria, my name is Nikos ..." },
      { "channel": "email", "status": "dry_run", "to": "maria@gmail.com", "subject": "Viewing request: 65 m², €600/month apartment", ... }
    ]
  }]
}
```

Attempt `status`: `sent` (provider accepted it; `provider_id` = Twilio SID / Resend id), `dry_run`, `skipped` (no usable contact for this channel; `detail` says why), `failed` (provider or config error; `detail` says why).

## 4. Configuration (`.env`), placeholders to fill in

| Variable | Notes |
| :--- | :--- |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | Twilio console. |
| `TWILIO_FROM_NUMBER` **or** `TWILIO_MESSAGING_SERVICE_SID` | A number **you bought or claimed in Twilio** (not your personal phone), in E.164. Alternatively, set the SID (`MG…`) of a Messaging Service, a Twilio container grouping several sender numbers. You need only one of the two. **Trial accounts can only text verified numbers.** |
| `RESEND_API_KEY` | resend.com → API keys. |
| `RESEND_FROM_EMAIL` | Must be on a domain verified in Resend. If left empty it uses `onboarding@resend.dev`, which only delivers to the Resend account owner's inbox. |
| `OUTREACH_DRY_RUN` | Default `true`. Set `false` to actually send. |
| `OUTREACH_CHANNELS` | Channels enabled on the server, comma-separated. Default `email` (e-mail only by default; the Twilio SMS adapter is kept and can be re-enabled with `OUTREACH_CHANNELS=sms,email`). A request's `channels` defaults to these, and channels not listed here are dropped even if a request asks for them. |
| `OUTREACH_OVERRIDE_PHONE` / `OUTREACH_OVERRIDE_EMAIL` | Optional. Redirects every real message to a teammate's phone or inbox. |
| `GEMINI_API_KEY`, `FIRECRAWL_API_KEY` | Used by the search agent (moved out of the source code, see §7). |

If credentials are missing, nothing crashes. The attempt comes back `failed` with a message such as `"Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env"`.

## 5. Safety design (decisions)

1. **Dry-run by default, as a server-side kill switch.** `OUTREACH_DRY_RUN=true` unless explicitly turned off. A request can force a dry run (`"dry_run": true`) but **cannot turn it off**. Only the server's `.env` can. This prevents someone accidentally texting real landlords while developing.
2. **Separate `/preview` endpoint.** The PROJECT_CONTEXT requires a human approval gate before any external communication. `/preview` returns the exact text and recipients so the UI can show them before the user presses "Send".
3. **Demo redirect (`OUTREACH_OVERRIDE_*`).** On stage we want real messages to arrive on a teammate's phone, not a stranger's. The response keeps both `to` (actual) and `intended_to` (the landlord), so the dashboard can still show who would have been contacted.
4. **Portal contacts are never used.** E-mails on `spitogatos.gr`, `xe.gr`, `plot.gr`, `facebook.com` and `noreply@`-style addresses are filtered out. The Gemini prompt was also changed to say "never the portal's own support contact".
5. **AI disclosure.** Every SMS and e-mail ends with "Sent on behalf of {user} by their relocation assistant."
6. **Replies go to the user.** The e-mail `Reply-To` is the user's address, and the user's phone/e-mail are in the body. Landlords can answer the human directly even though inbound webhooks aren't built yet.
7. **Oumi Iris `POSSIBLY_SCAM` dry-run lock.** If a listing carries `scam_verdict: "POSSIBLY_SCAM"`, both `ListingOutreachAgent` (`service.py`) and `stream_listing_outreach` (`live.py`) force `dry_run=True` even when `OUTREACH_DRY_RUN=false`. The agent still extracts contacts and composes the draft for review (with `detail: "Not sent: Oumi Iris flagged this listing as a possible scam"`), but never sends an SMS or e-mail.

## 6. Extraction & delivery decisions

- **Deterministic regex extraction, no second LLM call.** Gemini already fills `agent_phone` / `agent_email`. We only need to *clean* it, so regex is faster and free, gives the same result every time, and is unit-tested. Order of trust: structured fields (`agent_phone`, `contact_phone`, `phone`, … / `agent_email`, …) first, then every other string field (e.g. `score_reason`, raw text) as a fallback. Results are de-duplicated.
- **Greek-first phone normalization to E.164.** This is what Twilio needs. Bare 10-digit numbers starting with `69` are mobile and those starting with `2` are landline (`+30` is added). `0030…`, `30…` and `+30…` are handled. Other `+CC` numbers are accepted as `unknown` type. URLs are stripped before scanning, so listing IDs like `/aggelia/1234567890` are never mistaken for phone numbers.
- **Greek landlines are not texted.** SMS to `+302…` cannot be delivered, so the SMS attempt is `skipped` with `"Only a landline (...) was found; it cannot receive SMS"`, and e-mail still goes out. This is also the natural hook for the future voice-call channel.
- **SMS and e-mail are sent together, not as a fallback.** The spec's fallback chain is `Call → SMS + Email`. Voice isn't built yet, so both text channels fire in parallel. A listing counts as `contacted` if **any** channel succeeded.
- **REST over `httpx` instead of the Twilio/Resend SDKs.** This adds no dependencies, is natively async (so the per-listing agents really run concurrently), and can be tested with `httpx.MockTransport`, the same pattern as `backend/decision.py`.
- **Errors are reported, not raised.** One landlord's bad number must not abort the other agents. Each attempt carries its own `failed` + `detail`.
- **Templates instead of LLM-written messages.** The user approves exactly the text that will be sent, and nothing can be hallucinated (wrong price, false promises). Templates come in English and Greek (`"language": "el"`). SMS includes at most 2 viewing windows to stay short. The e-mail includes all of them plus the questions.
- **`missing_info` from the ranker becomes the e-mail's questions.** I added `missing_info` to `PropertyDetails` (the spec's "Missing-Info Detector"). If it's empty, default questions are used (availability, move-in date, whether building fees are included).

## 7. Changes to existing code

- **`backend/agent.py`**: refactored from a top-level script into `run_search_pipeline(user_request)`, with the same steps and prompts.
  - **The hardcoded Gemini and Firecrawl API keys were removed.** They are now read from `GEMINI_API_KEY` / `FIRECRAWL_API_KEY`. ⚠️ The old keys are still in git history, so **rotate them**.
  - Importing the module no longer runs the whole scrape. Previously it did, which also broke the FastAPI app.
  - `PropertyDetails` gained `agent_name`, `agent_email` and `missing_info`. The deep-scrape prompt now asks for them. No default values were added, because the Gemini `response_schema` doesn't support defaults.
  - CLI: `uv run python -m backend.agent "your request"`.
- **`backend/main.py`**: it imported `AgentResponse, TOOLS, agent`, which no longer exist, so the server could not start. It now exposes `POST /api/search` (runs the pipeline in a thread pool) plus the outreach endpoints. ⚠️ The frontend template still calls the old `/api/agent/run`.
- **`pyproject.toml` / `uv.lock`**: added `google-genai` and `firecrawl-py`, which `agent.py` already imported but which weren't declared.
- **`.env.example`**: added all new variables.

## 7b. Live outreach agent + calendar availability

`questions` (on `/preview`, `/send` and `/stream`): the exact questions the user approved in the
UI's briefing (the ranker's plus their own, up to 10). When present, even as `[]`, it replaces the
listing's `missing_info`. An empty list leaves the question block out of the e-mail.

`POST /api/outreach/stream` takes the same body as `/send` with exactly one property, plus
`calendar_url` (optional) and `demo` (forces a dry run). It streams NDJSON events
(`backend/outreach/live.py`) that the UI renders inside the property card:

| Step | What the agent does |
| :--- | :--- |
| `brief` | Reads the listing, the user's profile and the ranker's open questions. |
| `calendar` | Reads the user's calendar and picks up to 3 free viewing slots in the next 7 days, one per day: weekday evenings 18:00–20:30, Saturday 10–14 / 16–19, Sunday 11–14. Each slot is at least 1 h and leaves a 30-min travel buffer around events. Busy evenings are reported. |
| `contact` | Verifies the landlord's e-mail (portal and no-reply addresses filtered) and picks the greeting. |
| `draft` | Composes the e-mail with those slots as viewing windows. A `draft` event carries the exact subject and body. |
| `send` | Sends via Resend (or reports the dry run), then a `result` event shaped like `PropertyOutreachResult` plus `viewing_windows` and `dry_run`. |

**Calendar (`backend/outreach/availability.py`):** no OAuth. The user pastes their Google Calendar
*secret address in iCal format* in Settings (or the server sets `GOOGLE_CALENDAR_ICS_URL`).
`webcal://` links are accepted. Recurring events are expanded, and events marked *Free*
(`TRANSP:TRANSPARENT`, which includes most all-day events) don't block a slot. Without a calendar,
or if it can't be read, the agent uses a sample work week and says so in its log. The time zone is
`OUTREACH_TIMEZONE` (default `Europe/Athens`).

## 8. Not done yet / next steps

- **Inbound replies:** Twilio inbound-SMS webhook and Resend inbound e-mail, which would let the agent read landlord replies and update the dashboard. Today replies go directly to the user's phone/inbox.
- **Voice call channel** (first step of the spec's `Call → SMS + Email` chain).
- **Persisting outreach state.** Results are currently returned in the HTTP response only, with no DB.
- **A markdown fallback in `agent.py`:** running `extract_contacts()` over the raw listing markdown when Gemini returns no contact. This was left out on purpose because pages also contain the portal's own numbers.
- **Greek SMS cost:** Greek characters use UCS-2 encoding (70 chars per segment), so a Greek SMS costs about 4–5 segments.

## 9. Testing

**Environment readiness** (read-only, never sends anything):

```powershell
uv run python -m backend.check_env
```

It checks `.env` exists, that `.env.example` contains no secrets, dependencies, the outreach safety settings, and the Twilio credentials, sender number and trial restrictions (via read-only Twilio API calls). It also checks the search-agent keys.

**Unit tests:**

```powershell
uv run python -m pytest -v     # (on machines where Application Control blocks pytest.exe)
uv run ruff check .
```

`tests/test_outreach.py` covers phone normalization edge cases, extraction from structured fields and free text, portal filtering, EN/EL templates, dry-run (asserts no HTTP calls), live sends against mocked Twilio/Resend (auth headers, form/JSON payloads, `reply_to`), demo redirect, provider errors and missing credentials, and the API endpoints. No real messages are sent by the tests.
