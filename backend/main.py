from typing import Any, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from backend.outreach import (
    Channel,
    ExtractedContacts,
    OutreachBatchResponse,
    OutreachContext,
    OutreachSettings,
    ResendEmailSender,
    TwilioSmsSender,
    UserContact,
    extract_contacts,
    run_outreach,
)

from backend.decision import evaluate_ranked_properties, oumi_configured
from backend.outreach.live import stream_listing_outreach
from backend.photos import ImageFetchError, fetch_image
from backend.streaming import NDJSON_MEDIA_TYPE, stream_async_events, stream_sync_pipeline

load_dotenv()

app = FastAPI(title="GENAI Summit Agent API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    settings = OutreachSettings.from_env()
    return {
        "status": "ok",
        "oumi_configured": oumi_configured(),
        "outreach": {
            "dry_run": settings.dry_run,
            "channels": settings.channels,
            "sms_configured": TwilioSmsSender.from_env().missing_config is None,
            "email_configured": ResendEmailSender.from_env().missing_config is None,
            "override_phone": bool(settings.override_phone),
            "override_email": bool(settings.override_email),
        },
    }


# ---------------------------------------------------------------------------
# Search & rank (backend/agent.py)
# ---------------------------------------------------------------------------
class SearchInput(BaseModel):
    request: str = Field(description="Natural-language housing request.")


@app.post("/api/search")
async def search(payload: SearchInput) -> List[dict[str, Any]]:
    """Blocking search: returns the final ranked listings (with Oumi verdicts when configured)."""
    # Imported lazily so the API (and outreach) work without Gemini/Firecrawl installed/configured.
    from backend.agent import run_search

    try:
        outcome = await run_in_threadpool(run_search, payload.request)
    except RuntimeError as exc:  # Missing API keys.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return outcome.properties


@app.post("/api/search/stream")
async def search_stream(payload: SearchInput):
    """Same pipeline as /api/search, streamed as NDJSON progress events (see backend/streaming.py).

    The last line is `{"type": "result", "properties": [...], "stats": {...}}`
    or `{"type": "error", "detail": "..."}`.
    """
    from backend.agent import run_search

    def to_result(outcome) -> dict[str, Any]:
        return {
            "properties": outcome.properties,
            "stats": {"scanned": outcome.scanned, "rejected": outcome.rejected},
        }

    return StreamingResponse(
        stream_sync_pipeline(lambda emit: run_search(payload.request, emit), to_result),
        media_type=NDJSON_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Oumi Iris scam check on its own (backend/decision.py), without a full search
# ---------------------------------------------------------------------------
class DecisionInput(BaseModel):
    properties: List[dict[str, Any]] = Field(
        min_length=1, description="Ranked listings (PropertyDetails JSON), best first."
    )
    cohort: Optional[List[dict[str, Any]]] = Field(
        default=None, description="Other listings in the area, for the price-per-m² comparison."
    )


@app.post("/api/decision/evaluate")
async def decision_evaluate(payload: DecisionInput) -> List[dict[str, Any]]:
    """Runs only the Oumi Iris scam check: verdict, risk % and the main reason per listing."""
    if not oumi_configured():
        raise HTTPException(status_code=503, detail="OUMI_API_KEY / OUMI_PROJECT_ID not set.")
    try:
        batch = await evaluate_ranked_properties(payload.properties, all_properties=payload.cohort)
    except Exception as exc:  # Upstream error, timeout or unexpected response.
        raise HTTPException(status_code=502, detail=f"Oumi Iris did not answer: {exc}") from exc
    return [
        {
            "url": d.url,
            "rank": d.initial_rank,
            "scam_verdict": d.verdict,
            "scam_risk_pct": d.scam_risk_pct,
            "scam_reason": d.scam_reason,
        }
        for d in batch.results
    ]


@app.get("/api/image")
async def image_proxy(url: str = Query(..., max_length=2048)):
    """Serves a listing photo through the backend (portals often block hot-linking).

    Public http(s) hosts only; raster images only; 8 MB cap. See backend/photos.py.
    """
    try:
        content, media_type = await fetch_image(url)
    except ImageFetchError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


# ---------------------------------------------------------------------------
# Landlord outreach (backend/outreach/)
# ---------------------------------------------------------------------------
class ExtractInput(BaseModel):
    properties: List[dict[str, Any]] = Field(description="Agent responses (PropertyDetails JSON).")


class ExtractedListingContacts(BaseModel):
    url: Optional[str]
    contacts: ExtractedContacts


class OutreachInput(BaseModel):
    """Payload sent after the human approval gate."""

    user: UserContact
    properties: List[dict[str, Any]] = Field(
        description="The approved listings: agent responses (PropertyDetails JSON)."
    )
    viewing_windows: List[str] = Field(default_factory=list)
    channels: Optional[List[Channel]] = Field(
        default=None,
        description="Defaults to the server's enabled channels (OUTREACH_CHANNELS).",
    )
    language: str = Field(default="en", pattern="^(en|el)$")
    note: Optional[str] = None
    questions: Optional[List[str]] = Field(
        default=None,
        description="Questions the user approved for the landlord (the ranker's plus their own). "
        "When empty, each listing's missing_info is used.",
    )
    dry_run: bool = Field(
        default=False,
        description="Force a dry run. Cannot disable OUTREACH_DRY_RUN=true set on the server.",
    )

    def context(self) -> OutreachContext:
        return OutreachContext(
            user=self.user,
            viewing_windows=self.viewing_windows,
            language=self.language,  # type: ignore[arg-type]
            note=self.note,
            questions=self.questions,
        )


@app.post("/api/outreach/extract", response_model=List[ExtractedListingContacts])
async def outreach_extract(payload: ExtractInput):
    """Shows which phone numbers / e-mails were found for each listing."""
    return [
        ExtractedListingContacts(url=p.get("url"), contacts=extract_contacts(p))
        for p in payload.properties
    ]


@app.post("/api/outreach/preview", response_model=OutreachBatchResponse)
async def outreach_preview(payload: OutreachInput):
    """Composes every message and resolves every recipient, without sending anything."""
    return await run_outreach(
        payload.properties, payload.context(), payload.channels, force_dry_run=True
    )


@app.post("/api/outreach/send", response_model=OutreachBatchResponse)
async def outreach_send(payload: OutreachInput):
    """Sends SMS / e-mail to each approved listing's landlord (one agent per listing)."""
    if not payload.properties:
        raise HTTPException(status_code=422, detail="No approved properties to contact.")
    return await run_outreach(
        payload.properties, payload.context(), payload.channels, force_dry_run=payload.dry_run
    )


class LiveOutreachInput(OutreachInput):
    calendar_url: Optional[str] = Field(
        default=None,
        description="Google Calendar 'secret address in iCal format' used to find free viewing "
        "slots. Falls back to GOOGLE_CALENDAR_ICS_URL, then to a sample work week.",
    )
    demo: bool = Field(default=False, description="Demo listing: always a dry run.")


@app.post("/api/outreach/stream")
async def outreach_stream(payload: LiveOutreachInput):
    """Runs the outreach agent for ONE approved listing, streaming each step as NDJSON.

    Steps: brief → calendar (free viewing slots) → contact → draft (a `draft` event with the
    exact e-mail) → send, then a `result` event shaped like `PropertyOutreachResult` plus
    `viewing_windows` and `dry_run`.
    """
    if len(payload.properties) != 1:
        raise HTTPException(status_code=422, detail="Stream exactly one approved property.")
    events = stream_listing_outreach(
        payload.properties[0],
        payload.context(),
        calendar_url=payload.calendar_url,
        channels=payload.channels,
        force_dry_run=payload.dry_run,
        demo=payload.demo,
    )
    return StreamingResponse(
        stream_async_events(events),
        media_type=NDJSON_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
