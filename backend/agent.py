"""Search & ranking agent: plan → scan every site in parallel → rank → deep scrape top 3.

Sites (Spitogatos, xe.gr, Booking.com) are adapters in backend/sources.py.

Usage:
    from backend.agent import run_search_pipeline
    final_properties = run_search_pipeline("Apartment in Pangrati up to 600€, pet friendly")

Or from the CLI:  uv run python -m backend.agent "your request"

API keys are read from `.env` (GEMINI_API_KEY, FIRECRAWL_API_KEY); importing this module has
no side effects, so FastAPI can import it safely.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from backend.photos import listing_photos
from backend.sources import STAY_NIGHTS, ListingSource, ScanResult, enabled_sources, source_for_url
from backend.streaming import Cancelled, Emit, StepReporter

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


# ==========================================
# PYDANTIC SCHEMAS (Data structure)
# NOTE: no default values — the Gemini response_schema does not support them.
# ==========================================
class SearchPlan(BaseModel):
    spitogatos_url: str = Field(description="The search URL for spitogatos.gr.")
    area: str = Field(description="The neighbourhood and city in English, e.g. 'Pangrati, Athens'.")
    area_greek: Optional[str] = Field(description="The neighbourhood's name in Greek, e.g. 'Παγκράτι'.")
    max_price: Optional[int] = Field(description="Maximum monthly rent in euros, if the user gave one.")
    min_sqm: Optional[int] = Field(description="Minimum size in square meters, if the user gave one.")
    min_bedrooms: Optional[int] = Field(description="Minimum number of bedrooms, if the user gave one.")


class PropertyPreview(BaseModel):
    url: str = Field(description="The exact listing link")
    price: Optional[int] = Field(description="The price (number only)")
    sqm: Optional[int] = Field(description="The square meters")
    basic_info: str = Field(description="A short sentence with everything else mentioned in the summary")


class AllProperties(BaseModel):
    properties: List[PropertyPreview] = Field(description="The complete list of ALL properties on the page.")


class PropertyLink(BaseModel):
    url: str = Field(description="The exact listing link")


class PropertyList(BaseModel):
    links: List[PropertyLink] = Field(description="List of the top 3 listing links.")


METRIC_NAMES = ["Price & value", "Space & layout", "Location", "Condition & light", "Your must-haves"]


class MetricScore(BaseModel):
    name: str = Field(description=f"Exactly one of: {', '.join(METRIC_NAMES)}.")
    score: int = Field(description="Score 1-10 for THIS user on this metric.")
    note: str = Field(description="Why, in at most 12 words, in English.")


class PropertyDetails(BaseModel):
    url: str
    price: Optional[int] = Field(description="The rental price in Euros (number only).")
    sqm: Optional[int] = Field(description="The square meters.")
    floor: Optional[str] = Field(description="The floor (e.g., 1st, Ground floor).")
    features: List[str] = Field(description="List of amenities/features (e.g., natural gas, pet friendly).")
    agent_name: Optional[str] = Field(
        description="Name of the landlord / real-estate agent or agency, if shown."
    )
    agent_phone: Optional[str] = Field(
        description="The phone number of the agent/owner exactly as shown, if available. "
        "Never the portal's own customer-support number."
    )
    agent_email: Optional[str] = Field(
        description="The e-mail address of the agent/owner, if available. "
        "Never the portal's own address (e.g. @spitogatos.gr, @xe.gr, @booking.com)."
    )
    missing_info: List[str] = Field(
        description="Up to 4 short questions IN ENGLISH to ask the landlord about important details "
        "the user cares about that the listing does NOT state (e.g. 'Are pets allowed?')."
    )
    agentic_score: int = Field(description="Score 1-10 for how well it matches the requirements.")
    score_reason: str = Field(description="A short sentence explaining why it received this score.")
    pros: List[str] = Field(
        description="2-4 concrete strengths of this listing for THIS user, max 10 words each, in English."
    )
    cons: List[str] = Field(
        description="1-3 concrete drawbacks or risks for THIS user, max 10 words each, in English."
    )
    metrics: List[MetricScore] = Field(
        description=f"Exactly {len(METRIC_NAMES)} entries, one per metric: {', '.join(METRIC_NAMES)}."
    )


# ==========================================
# API CLIENTS (lazy, keys from .env)
# ==========================================
@lru_cache(maxsize=1)
def _gemini():
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env")
    return genai.Client(api_key=api_key)


@lru_cache(maxsize=1)
def _firecrawl():
    from firecrawl import FirecrawlApp

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("Set FIRECRAWL_API_KEY in .env")
    return FirecrawlApp(api_key=api_key)


def _generate(prompt: str, schema: type[BaseModel]):
    from google.genai import types

    res = _gemini().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema),
    )
    return res.parsed


@dataclass
class ScrapedPage:
    markdown: str = ""
    raw_html: str = ""
    og_image: Optional[str] = None
    images: List[str] = field(default_factory=list)


def _field(obj, *names):
    """First non-empty attribute / key among `names` (Firecrawl v1 dicts and v2 models)."""
    for name in names:
        value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if value:
            return value
    return None


def scrape_page(url: str, images: bool = False, raw_html: bool = False) -> ScrapedPage:
    """Scrapes a page with Firecrawl (any firecrawl-py version): markdown, og:image, image URLs,
    and optionally the raw HTML (for data embedded in the page, see backend/sources.py)."""
    firecrawl = _firecrawl()
    formats = ["markdown"] + (["images"] if images else []) + (["rawHtml"] if raw_html else [])
    if hasattr(firecrawl, "scrape"):
        try:
            res = firecrawl.scrape(url, formats=formats)
        except Exception:
            if not images:
                raise
            res = firecrawl.scrape(url, formats=["markdown"])  # "images" format not supported.
    else:
        res = firecrawl.scrape_url(url, params={"formats": ["markdown"]})
    meta = _field(res, "metadata") or {}
    og = _field(meta, "og_image", "ogImage", "og:image")
    if isinstance(og, list):
        og = og[0] if og else None
    imgs = _field(res, "images") or []
    return ScrapedPage(
        markdown=_field(res, "markdown") or "",
        raw_html=_field(res, "raw_html", "rawHtml") or "",
        og_image=og if isinstance(og, str) else None,
        images=[i for i in imgs if isinstance(i, str)],
    )


def get_markdown(url: str) -> str:
    return scrape_page(url).markdown


# ==========================================
# PIPELINE
# ==========================================
TOP_N = 3

STEP_TITLES = {
    "understand": "Reading your request",
    "scan": "Scanning listings",
    "rank": "Ranking against your request",
    "inspect": "Inspecting the shortlist",
    "scam": "Scam check (Oumi Iris)",
    "final": "Selecting the top matches",
}


class SearchOutcome(BaseModel):
    """What the streaming search returns: final listings (+ scam verdicts) and funnel stats."""

    properties: List[dict]
    scanned: int
    rejected: int


def _short_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else ""
    host = parsed.netloc.replace("www.", "")
    return f"{host}/…/{tail}" if tail and path.count("/") > 1 else f"{host}{path}"


def _money(price: Optional[int]) -> str:
    return f"€{price}/mo" if price else "price n/a"


def _preview_line(h: PropertyPreview) -> str:
    bits = [_money(h.price)]
    if h.sqm:
        bits.append(f"{h.sqm} m²")
    info = (h.basic_info or "").strip()
    if len(info) > 70:
        info = info[:67].rstrip() + "…"
    return " · ".join(bits) + (f": {info}" if info else "")


def _describe_plan(plan: SearchPlan) -> List[str]:
    """Human-readable lines for the search filters the agent planned."""
    lines = [f"Area: {plan.area}" + (f" ({plan.area_greek})" if plan.area_greek else "")]
    if plan.max_price:
        lines.append(f"Max price: €{plan.max_price}/month")
    if plan.min_sqm:
        lines.append(f"Min size: {plan.min_sqm} m²")
    if plan.min_bedrooms:
        lines.append(f"Min bedrooms: {plan.min_bedrooms}")
    return lines


def _names(sources: List[ListingSource]) -> str:
    names = [s.name for s in sources]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _scan_source(
    source: ListingSource, plan: SearchPlan, progress: StepReporter
) -> ScanResult:
    """One scanner agent: reads one site's results page."""
    agent_id = f"source-{source.key}"
    progress.agent("scan", agent_id, source.name, "running", "Opening the results page",
                   hub="Orchestrator", source=source.key)

    def log(text: str, kind: str = "info") -> None:
        progress.log("scan", f"{source.name}: {text}", kind, source=source.key)  # type: ignore[arg-type]

    try:
        result = source.scan(plan, log)
    except Cancelled:
        raise
    except Exception:
        progress.agent("scan", agent_id, source.name, "failed", "Results page unavailable", source=source.key)
        raise
    n = len(result.listings)
    log(f"found {n} listing{'' if n == 1 else 's'}", "ok" if n else "warn")
    for h in result.listings[:2]:
        progress.log("scan", _preview_line(h), source=source.key)
    progress.agent("scan", agent_id, source.name, "done" if n else "failed",
                   f"{n} listing{'' if n == 1 else 's'}", source=source.key)
    return result


def _inspect_listing(
    index: int, url: str, user_request: str, progress: StepReporter, thumbnail: Optional[str] = None
) -> tuple[PropertyDetails, List[str]]:
    """One shortlist agent: deep-scrapes a listing for details, contacts, questions and photos."""
    tag = f"Agent {index + 1}"
    agent_id = f"listing-{index + 1}"
    site = source_for_url(url)
    key = site.key if site else None
    progress.agent("inspect", agent_id, tag, "running", f"Opening {_short_url(url)}", hub="Orchestrator", source=key)
    progress.log("inspect", f"{tag} is opening {_short_url(url)}", source=key)
    try:
        page = scrape_page(url, images=True)
        detail_markdown = page.markdown
        photos = listing_photos(url, detail_markdown, page.og_image, page.images)
        if not photos and thumbnail:
            photos = [thumbnail]
        progress.log(
            "inspect",
            f"{tag} collected {len(photos)} photo{'' if len(photos) == 1 else 's'}" if photos
            else f"{tag} found no photos on the listing",
            "info" if photos else "warn",
            source=key,
        )
        kb = len(detail_markdown) // 1000 or 1
        progress.agent("inspect", agent_id, tag, "running", f"Reading the full listing ({kb} KB)", source=key)
        progress.log("inspect", f"{tag} is reading the full listing ({kb} KB)", source=key)
        stay_note = (
            f"This is a furnished short stay on {site.name}: the price shown is for a "
            f"{STAY_NIGHTS}-night stay, report it as the monthly price. The host is the landlord."
            if site and site.short_stay
            else ""
        )
        prompt_details = f"""
        The user requests: '{user_request}'.
        Confirm if this listing matches (score it 1-10).
        Find the name, phone number and e-mail of the landlord / agent who posted it
        (NOT the website's own support contacts).
        List the important details the user cares about that the listing does not mention,
        phrased as short questions to the landlord. Always write the questions in English,
        even if the listing is in Greek.
        Judge the listing for this user: give concrete pros and cons, and score each of these
        metrics 1-10 with a short note: {", ".join(METRIC_NAMES)}.
        {stay_note}
        Extract the data into JSON.
        Listing Markdown:
        {detail_markdown[:15000]}
        """
        property_data = _generate(prompt_details, PropertyDetails)
    except Cancelled:
        raise
    except Exception:
        progress.agent("inspect", agent_id, tag, "failed", "Could not read the listing", source=key)
        raise
    property_data.url = url
    contact = (
        f"e-mail for {property_data.agent_name or 'the landlord'}"
        if property_data.agent_email
        else "no e-mail listed"
    )
    questions = len(property_data.missing_info or [])
    progress.log(
        "inspect",
        f"{tag}: scored {property_data.agentic_score}/10, {contact}, "
        f"{questions} open question{'' if questions == 1 else 's'}",
        "ok" if property_data.agent_email else "warn",
        source=key,
    )
    progress.agent(
        "inspect", agent_id, tag, "done",
        f"{property_data.agentic_score}/10 · {'e-mail found' if property_data.agent_email else 'no e-mail'}",
        source=key,
    )
    return property_data, photos


def _scam_gate(
    final: List[PropertyDetails], all_houses: List[PropertyPreview], progress: StepReporter
) -> dict[str, dict]:
    """Runs the Oumi Iris decision model if configured. Returns {url: verdict fields}."""
    progress.start("scam", STEP_TITLES["scam"], "Checking the shortlist for rental-scam patterns")
    if not (os.getenv("OUMI_API_KEY", "").strip() and os.getenv("OUMI_PROJECT_ID", "").strip()):
        progress.log("scam", "Oumi Iris is not configured (OUMI_API_KEY / OUMI_PROJECT_ID)", "warn")
        progress.done("scam", "Skipped: decision model not configured", status="skipped")
        return {}
    from backend.decision import evaluate_ranked_properties_sync

    progress.log("scam", f"Comparing price per m² against {len(all_houses)} listings in the area")
    progress.log("scam", f"Sending {len(final)} listings to Oumi Iris")
    for i in range(len(final)):
        progress.agent("scam", f"iris-{i + 1}", f"Listing {i + 1}", "running", "Under review", hub="Oumi Iris")
    try:
        decisions = evaluate_ranked_properties_sync(final, all_properties=all_houses)
    except Exception as exc:
        for i in range(len(final)):
            progress.agent("scam", f"iris-{i + 1}", f"Listing {i + 1}", "failed", "No verdict")
        progress.log("scam", f"Oumi Iris did not answer: {exc}", "warn")
        progress.done("scam", "Skipped: decision model unavailable", status="skipped")
        return {}
    verdicts: dict[str, dict] = {}
    for d in decisions.results:
        safe = d.verdict == "SAFE"
        progress.log(
            "scam",
            f"Listing {d.initial_rank}: {'safe' if safe else 'possible scam'} (risk {d.scam_risk_pct}%)",
            "ok" if safe else "warn",
        )
        progress.agent(
            "scam", f"iris-{d.initial_rank}", f"Listing {d.initial_rank}",
            "done" if safe else "failed", f"{'Safe' if safe else 'Possible scam'} · risk {d.scam_risk_pct}%",
        )
        verdicts[d.url] = {"scam_verdict": d.verdict, "scam_risk_pct": d.scam_risk_pct}
    flagged = len(decisions.possibly_scam_properties)
    progress.done(
        "scam",
        f"Flagged {flagged} possible scam{'' if flagged == 1 else 's'}" if flagged else "All listings passed",
    )
    return verdicts


def _site_fields(url: str) -> dict:
    site = source_for_url(url)
    return {"source": site.key, "source_name": site.name, "short_stay": site.short_stay} if site else {}


def run_search(user_request: str, emit: Optional[Emit] = None, verbose: bool = False) -> SearchOutcome:
    """The full search pipeline. `emit` receives live progress events (see backend/streaming.py)."""
    progress = StepReporter(emit)
    log = print if verbose else (lambda *a, **k: None)

    sources = enabled_sources()

    # STEP 1: Plan the search once; every site builds its own URL from the plan.
    progress.start("understand", STEP_TITLES["understand"], "Turning your request into search filters")
    progress.log("understand", f"Gemini is translating your request into filters for {_names(sources)}")
    log("1. The Agent is planning the search...")
    prompt_plan = f"""
    The user requests: '{user_request}'.
    Plan a rental search in Greece.
    - spitogatos_url: a search URL for spitogatos.gr.
      Example structure: https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati?max_price=600
    - area: the neighbourhood and city in English (e.g. 'Pangrati, Athens'); the city alone if no
      neighbourhood is given; 'Athens' if no place is given.
    - area_greek: the neighbourhood (or city) name in Greek (e.g. 'Παγκράτι').
    - max_price, min_sqm, min_bedrooms: the user's limits, or null if not stated.
    """
    plan = _generate(prompt_plan, SearchPlan)
    log(f"-> Plan: {plan}\n")
    for line in _describe_plan(plan):
        progress.log("understand", line)
    for source in sources:
        progress.log("understand", f"{source.name} search planned", "ok", source=source.key)
    progress.done("understand", "Search filters ready")

    # STEP 2: Shallow scrape — one scanner agent per site, in parallel.
    progress.start(
        "scan", STEP_TITLES["scan"], f"Searching {_names(sources)} in parallel",
        sources=[s.key for s in sources],
    )
    progress.log("scan", f"Dispatching {len(sources)} scanner agents, one per site")
    log(f"2. Firecrawl is scanning {_names(sources)}...")
    all_houses: List[PropertyPreview] = []
    thumbnails: dict[str, str] = {}
    site_by_url: dict[str, ListingSource] = {}
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        futures = [(src, pool.submit(_scan_source, src, plan, progress)) for src in sources]
        for src, future in futures:
            try:
                scan = future.result()
            except Cancelled:
                raise
            except Exception as exc:  # One unreachable site must not sink the whole search.
                progress.log("scan", f"{src.name} could not be searched: {exc}", "warn", source=src.key)
                continue
            for h in scan.listings:
                if h.url and h.url not in site_by_url:
                    site_by_url[h.url] = src
                    all_houses.append(h)
            thumbnails.update(scan.thumbnails)
    log(f"Found {len(all_houses)} properties in total!\n")
    if not all_houses:
        progress.log("scan", "No site had listings for these filters", "warn")
        progress.done("scan", "No listings found", status="failed")
        return SearchOutcome(properties=[], scanned=0, rejected=0)
    per_site = Counter(site_by_url[h.url].name for h in all_houses)
    progress.done(
        "scan",
        f"Scanned {len(all_houses)} listings (" + ", ".join(f"{n} on {name}" for name, n in per_site.items()) + ")",
    )

    # STEP 3A: Agentic Ranking on ALL properties
    progress.start("rank", STEP_TITLES["rank"], "Scoring each listing against your constraints")
    progress.log("rank", f"Weighing price, size and description of all {len(all_houses)} listings")
    log(f"3. The Agent is evaluating all {len(all_houses)} properties simultaneously...")
    houses_text = "".join(
        f"[{i}] Site: {site_by_url[h.url].name} | Link: {h.url} | Price: {h.price} | Sq.m.: {h.sqm}"
        f" | Info: {h.basic_info}\n"
        for i, h in enumerate(all_houses)
    )
    stay_sites = sorted({s.name for s in site_by_url.values() if s.short_stay})
    stay_note = (
        f"Listings from {', '.join(stay_sites)} are furnished short stays: their price is the cost of "
        f"{STAY_NIGHTS} nights, usually above a long-term rent. Prefer long-term rentals unless the user "
        "wants a short, temporary or furnished stay."
        if stay_sites
        else ""
    )
    prompt_rank_all = f"""
    The user requests: '{user_request}'.
    Below is a list of {len(all_houses)} apartments from several property sites.
    Acting as an expert real estate agent, evaluate each one and pick the top {TOP_N}.
    Base your decision on the price, square meters, and description.
    {stay_note}

    List:
    {houses_text}
    """
    ranked = _generate(prompt_rank_all, PropertyList).links
    top_urls = [u for u in dict.fromkeys(link.url for link in ranked) if u in site_by_url][:TOP_N]
    log(f"-> The Agent selected the top {TOP_N}: {top_urls}\n")
    by_url = {h.url: h for h in all_houses}
    for i, url in enumerate(top_urls):
        preview = by_url.get(url)
        line = _preview_line(preview) if preview else _short_url(url)
        progress.log("rank", f"Shortlisted #{i + 1}: {line}", "ok", source=site_by_url[url].key)
    set_aside = max(0, len(all_houses) - len(top_urls))
    if set_aside:
        progress.log("rank", f"Set aside {set_aside} weaker matches")
    progress.done("rank", f"Shortlisted {len(top_urls)} of {len(all_houses)}")

    # STEP 3B: Deep Scrape ONLY on the "Winners" — one agent per listing, in parallel.
    progress.start("inspect", STEP_TITLES["inspect"], "Visiting the best listings for contacts and missing details")
    progress.log("inspect", f"Dispatching {len(top_urls)} agents in parallel, one per listing")
    log(f"4. The Agent is visiting the {len(top_urls)} best listings to find the contact details...")
    final_properties: List[PropertyDetails] = []
    photos_by_url: dict[str, List[str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(top_urls))) as pool:
        futures = [
            pool.submit(_inspect_listing, i, url, user_request, progress, thumbnails.get(url))
            for i, url in enumerate(top_urls)
        ]
        for i, future in enumerate(futures):
            try:
                details, photos = future.result()
                final_properties.append(details)
                photos_by_url[details.url] = photos
            except Cancelled:
                raise
            except Exception as exc:  # One unreadable listing must not sink the whole search.
                progress.log("inspect", f"Agent {i + 1} could not read its listing: {exc}", "warn")
    with_email = sum(1 for p in final_properties if p.agent_email)
    progress.done("inspect", f"Found e-mail contacts for {with_email} of {len(final_properties)} listings")

    # STEP 4: Oumi Iris scam gate (optional, needs OUMI_API_KEY + OUMI_PROJECT_ID).
    # Short-stay prices would skew the area's price per m², so they are not used as comparables.
    cohort = [h for h in all_houses if not site_by_url[h.url].short_stay] or all_houses
    verdicts = _scam_gate(final_properties, cohort, progress) if final_properties else {}

    # STEP 5: Final ordering. Scam-flagged listings sink to the bottom.
    progress.start("final", STEP_TITLES["final"], "Final scoring")
    final_properties.sort(key=lambda x: x.agentic_score, reverse=True)
    results = [
        {
            **p.model_dump(),
            **verdicts.get(p.url, {}),
            "images": photos_by_url.get(p.url, []),
            **_site_fields(p.url),
        }
        for p in final_properties
    ]
    results.sort(key=lambda r: r.get("scam_verdict") == "POSSIBLY_SCAM")
    if results:
        best = results[0]
        progress.log("final", "Sorted the shortlist by match score")
        progress.log("final", f"Best match {best['agentic_score']}/10: {best['score_reason']}", "ok")
        progress.done("final", f"Selected the top {len(results)}, best match {best['agentic_score']}/10")
    else:
        progress.done("final", "No listing passed the filters", status="failed")
    return SearchOutcome(
        properties=results, scanned=len(all_houses), rejected=max(0, len(all_houses) - len(results))
    )


def run_search_pipeline(user_request: str, verbose: bool = True) -> List[PropertyDetails]:
    """Blocking, non-streaming search (CLI). Same pipeline as `run_search`."""
    outcome = run_search(user_request, verbose=verbose)
    fields = set(PropertyDetails.model_fields)
    return [PropertyDetails(**{k: v for k, v in p.items() if k in fields}) for p in outcome.properties]


if __name__ == "__main__":
    request = " ".join(sys.argv[1:]) or (
        "I am looking for an apartment in Pangrati, up to 600 euros, pet friendly. I want it to be bright."
    )
    results = run_search_pipeline(request)
    print("\n=== FINAL AGENT SELECTION ===")
    for prop in results:
        print(f"Property: {prop.url}")
        print(f"Price: {prop.price}€ | {prop.sqm} sq.m. | Floor: {prop.floor}")
        print(f"Score: {prop.agentic_score}/10")
        print(f"Reasoning: {prop.score_reason}")
        print(f"Contact: {prop.agent_name} | {prop.agent_phone} | {prop.agent_email}")
        print(f"Questions: {prop.missing_info}")
        print("-" * 30)
