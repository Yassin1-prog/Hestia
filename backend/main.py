from typing import Any, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
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
    # Imported lazily so the API (and outreach) work without Gemini/Firecrawl installed/configured.
    from backend.agent import run_search_pipeline

    try:
        properties = await run_in_threadpool(run_search_pipeline, payload.request, False)
    except RuntimeError as exc:  # Missing API keys.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [p.model_dump() for p in properties]


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
