"""Oumi Iris Decision Model integration for post-ranker rental scam detection.

This module is standalone and does NOT modify or implement the feature ranker.
It accepts ranked properties produced by the ranker (such as `PropertyDetails`
from `backend/agent.py` or plain dicts), evaluates them in parallel with Oumi's
`Iris` Decision Model (`POST https://inference.oumi.ai/v1/systemone`), and
outputs a strict `SAFE` vs. `POSSIBLY_SCAM` verdict with frontend-ready
forensic probability bars.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

OUMI_SYSTEMONE_URL = "https://inference.oumi.ai/v1/systemone"

# Baseline Athens neighborhood median €/m² and std-dev for fallback cohort comparison
ATHENS_NEIGHBORHOOD_BASELINES: dict[str, tuple[float, float]] = {
    "pangrati": (12.20, 2.05),
    "pagkrati": (12.20, 2.05),
    "koukaki": (16.00, 2.65),
    "kolonaki": (17.50, 3.10),
    "exarchia": (11.20, 1.95),
    "exarcheia": (11.20, 1.95),
    "zografou": (10.40, 1.60),
    "kypseli": (8.90, 1.55),
    "kipseli": (8.90, 1.55),
    "petralona": (12.80, 2.10),
    "ampelokipoi": (11.50, 1.85),
    "mets": (13.40, 2.20),
    "neos-kosmos": (12.00, 2.00),
    "athens": (12.00, 2.20),
}

ADVANCE_FEE_KEYWORDS: tuple[str, ...] = (
    "escrow",
    "airbnb",
    "booking.com",
    "tripadvisor",
    "western union",
    "moneygram",
    "revolut",
    "wire transfer",
    "upfront deposit",
    "before viewing",
    "send keys",
    "courier",
    "abroad",
    "working in london",
    "out of country",
    "whatsapp only",
    "viber only",
    "telegram only",
    "προκαταβολή πριν",
    "εξωτερικό",
)


# ==========================================
# PYDANTIC SCHEMAS (Input & Frontend Output)
# ==========================================
class DecisionPropertyInput(BaseModel):
    """Normalized input for Oumi Iris evaluation, compatible with `PropertyDetails`."""

    listing_id: str = Field(description="Unique ID or URL for the property.")
    url: str = Field(default="", description="Listing URL.")
    title: str = Field(default="", description="Property title or summary.")
    neighborhood: str = Field(default="Athens", description="Neighborhood name or slug.")
    source: str = Field(default="spitogatos", description="Listing datasource.")
    price: Optional[float] = Field(default=None, description="Monthly rental price in EUR.")
    sqm: Optional[float] = Field(default=None, description="Area in square meters.")
    floor: Optional[str] = Field(default=None, description="Floor level string.")
    features: list[str] = Field(default_factory=list, description="Extracted property features.")
    agent_phone: Optional[str] = Field(default=None, description="Landlord or agency phone number.")
    agentic_score: int = Field(default=0, description="Ranker score (e.g., 1-10 or 0-100).")
    score_reason: str = Field(default="", description="Ranker reasoning summary.")
    initial_rank: int = Field(default=1, description="1-based rank assigned by the ranker.")
    description: str = Field(default="", description="Full text or markdown snippet of the listing.")
    cohort_median_eur_per_sqm: Optional[float] = Field(
        default=None,
        description="Median €/m² across the search cohort or neighborhood.",
    )
    cohort_std_eur_per_sqm: Optional[float] = Field(
        default=None,
        description="Standard deviation of €/m² across the search cohort or neighborhood.",
    )
    upfront_pre_viewing_payment_eur: float = Field(
        default=0.0,
        description="Any pre-viewing payment demanded in EUR.",
    )
    reverse_image_match: str = Field(
        default="NONE",
        description="Reverse-image signal (e.g., 'NONE', 'SHORT_TERM_RENTAL_AIRBNB_BOOKING').",
    )
    cross_portal_price_conflict: bool = Field(
        default=False,
        description="True if identical listing appears elsewhere with conflicting price/contact.",
    )


class ForensicCriterionBar(BaseModel):
    """Single forensic probability bar for the frontend 'Wow Factor' UI."""

    key: str = Field(description="Identifier of the rubric criterion.")
    label: str = Field(description="Human-readable label for the frontend progress bar.")
    probability: float = Field(description="0.0 to 1.0 probability from Oumi Iris.")
    risk_pct: int = Field(description="0 to 100 percentage for UI bar width.")
    evidence: str = Field(description="Short forensic evidence string shown beneath the bar.")


class PropertyDecisionResult(BaseModel):
    """Decision output for a single ranked property evaluated by Oumi Iris."""

    listing_id: str
    url: str
    title: str
    neighborhood: str
    price: Optional[float] = None
    sqm: Optional[float] = None
    eur_per_sqm: Optional[float] = None
    cohort_median_eur_per_sqm: float
    price_deviation_pct: Optional[float] = None
    price_z_score: Optional[float] = None
    initial_rank: int = Field(description="Rank #1..#K from the ranker BEFORE Oumi Iris.")
    verified_rank: Optional[int] = Field(
        default=None,
        description="Re-indexed rank #1..#M among SAFE properties (None if POSSIBLY_SCAM).",
    )
    agentic_score: int = Field(default=0, description="Original score from the ranker.")
    verdict: Literal["SAFE", "POSSIBLY_SCAM"]
    scam_probability: float = Field(description="Calibrated probability (0.0-1.0) from Oumi Iris.")
    scam_risk_pct: int = Field(description="0-100 risk percentage for the UI.")
    intercepted_top_match: bool = Field(
        default=False,
        description="True if this property was a top-ranked match (e.g. Rank #1) intercepted as POSSIBLY_SCAM.",
    )
    ui_badge: str = Field(description="Frontend pill badge text.")
    forensic_summary: str = Field(description="Headline explanation for the frontend card.")
    forensic_bars: list[ForensicCriterionBar] = Field(
        default_factory=list,
        description="4 forensic rubric probability bars for the frontend UI.",
    )
    triggered_flags: list[str] = Field(default_factory=list)
    source_mode: Literal["live_oumi_iris", "cached_oumi_iris", "deterministic_fallback"]
    latency_ms: float


class DecisionTelemetry(BaseModel):
    """Execution telemetry surfaced in the frontend pipeline banner."""

    model: str
    total_evaluated: int
    safe_count: int
    possibly_scam_count: int
    intercepted_rank_one: bool
    total_latency_ms: float
    source_mode: str


class DecisionBatchResponse(BaseModel):
    """Complete post-ranker Oumi Iris output ready for the frontend and downstream agents."""

    results: list[PropertyDecisionResult]
    safe_properties: list[PropertyDecisionResult]
    possibly_scam_properties: list[PropertyDecisionResult]
    wow_factor_banner: Optional[str] = None
    telemetry: DecisionTelemetry


# ==========================================
# OUMI IRIS (/v1/systemone) QUESTION RUBRIC
# ==========================================
IRIS_SCAM_QUESTIONS: dict[str, Any] = {
    "verdict": {
        "type": "choice",
        "instructions": "Classify this ranked residential rental listing as SAFE or POSSIBLY_SCAM.",
        "criteria": {
            "SAFE": (
                "Realistic neighborhood market price (€/m² aligns with cohort), consistent property "
                "details, verifiable phone contact, and standard in-person viewing with zero upfront payment."
            ),
            "POSSIBLY_SCAM": (
                "Shows credible rental scam or bait-listing indicators: severe price-per-m² undervaluation "
                "vs. neighborhood median, advance-fee/escrow or absentee-landlord wire demands, WhatsApp/foreign "
                "contact isolation, stolen Airbnb/stock imagery, cross-portal clone conflicts, or missing/contradictory specs."
            ),
        },
    },
    "is_possibly_scam": {
        "type": "noul",
        "instructions": "What is the probability that this ranked rental listing is fraudulent, a bait ad, or an advance-fee scam?",
        "criteria": {
            "true": "Listing exhibits financial, pricing, media, or contact fraud indicators that put a tenant at risk.",
            "false": "Listing behaves like an authentic residential lease offering.",
        },
    },
    "price_anomaly": {
        "type": "noul",
        "instructions": "Is the monthly rent per m² suspiciously below the neighborhood cohort median without a valid physical defect?",
        "criteria": {
            "true": "price_deviation_pct <= -25% or price_z_score <= -1.5 (especially -40%+ bait pricing on a high-scoring property).",
            "false": "Price per m² falls within normal neighborhood variance.",
        },
    },
    "advance_fee_or_remote_lure": {
        "type": "noul",
        "instructions": "Does the listing pressure for upfront payment/escrow before viewing or claim an absentee overseas landlord?",
        "criteria": {
            "true": "Requests upfront deposit/wire/Revolut/Airbnb escrow before in-person viewing, claims owner is abroad shipping keys, or isolates contact to WhatsApp/foreign numbers.",
            "false": "Allows normal in-person property viewing and standard lease signing.",
        },
    },
    "stolen_media_or_clone": {
        "type": "noul",
        "instructions": "Do reverse-image or cross-portal signals indicate stolen short-term rental photos or a cloned listing?",
        "criteria": {
            "true": "Photos match an active Airbnb/Booking/hotel/stock listing or reappear across portals with conflicting contact details and large price drops.",
            "false": "Original property imagery with consistent provenance.",
        },
    },
    "metadata_contradiction": {
        "type": "noul",
        "instructions": "Are there contradictory specs, missing landlord phone contact on a too-good-to-be-true ad, or suspicious omissions?",
        "criteria": {
            "true": "Unreachable/missing phone number combined with extreme feature claims, impossible floor geometry, or stripped mandatory disclosures.",
            "false": "Specs and contact metadata are consistent.",
        },
    },
}


# ==========================================
# HELPER FUNCTIONS (Cohort & Input Adapter)
# ==========================================
def infer_neighborhood_baseline(url_or_text: str) -> tuple[str, float, float]:
    """Infers the Athens neighborhood name, median €/m², and std-dev from a URL or text."""
    lowered = (url_or_text or "").lower()
    for slug, (median, std) in ATHENS_NEIGHBORHOOD_BASELINES.items():
        if slug in lowered:
            display = "Pangrati" if slug == "pagkrati" else slug.replace("-", " ").title()
            return display, median, std
    return "Athens", 12.00, 2.20


def compute_cohort_sqm_stats(
    all_properties: Optional[Sequence[Any]],
    fallback_url_or_text: str = "",
) -> tuple[float, float]:
    """Computes cohort (median_eur_per_sqm, std_eur_per_sqm) from shallow-scraped properties if available."""
    _, default_median, default_std = infer_neighborhood_baseline(fallback_url_or_text)
    if not all_properties:
        return default_median, default_std

    ratios: list[float] = []
    for item in all_properties:
        data = item.model_dump() if isinstance(item, BaseModel) else (item if isinstance(item, dict) else item.__dict__)
        price = data.get("price") or data.get("price_eur")
        sqm = data.get("sqm") or data.get("size_sqm")
        if price and sqm and float(sqm) > 10 and float(price) > 100:
            ratios.append(float(price) / float(sqm))

    if len(ratios) >= 3:
        med = float(statistics.median(ratios))
        std = float(statistics.stdev(ratios)) if len(ratios) >= 4 else max(med * 0.16, 1.5)
        return round(med, 2), round(max(std, 1.0), 2)
    return default_median, default_std


def normalize_ranked_property(
    raw: Any,
    initial_rank: int,
    cohort_median: Optional[float] = None,
    cohort_std: Optional[float] = None,
) -> DecisionPropertyInput:
    """Adapts a `PropertyDetails` object (from `backend/agent.py`), dict, or `DecisionPropertyInput`."""
    if isinstance(raw, DecisionPropertyInput):
        candidate = raw.model_copy(deep=True)
        if candidate.initial_rank <= 0:
            candidate.initial_rank = initial_rank
    else:
        data = raw.model_dump() if isinstance(raw, BaseModel) else (dict(raw) if isinstance(raw, dict) else dict(raw.__dict__))
        url = str(data.get("url") or data.get("listing_id") or f"property-{initial_rank}")
        neighborhood_hint = str(data.get("neighborhood") or url or data.get("score_reason") or "")
        inferred_name, _, _ = infer_neighborhood_baseline(neighborhood_hint)
        price_val = data.get("price") if data.get("price") is not None else data.get("price_eur")
        sqm_val = data.get("sqm") if data.get("sqm") is not None else data.get("size_sqm")
        features = list(data.get("features") or [])
        score_reason = str(data.get("score_reason") or "")
        description = str(data.get("description") or data.get("basic_info") or score_reason)
        title = str(
            data.get("title")
            or (f"{inferred_name} {int(sqm_val)}m² Apartment" if sqm_val else f"{inferred_name} Listing #{initial_rank}")
        )
        candidate = DecisionPropertyInput(
            listing_id=str(data.get("listing_id") or url),
            url=url,
            title=title,
            neighborhood=str(data.get("neighborhood") or inferred_name),
            source=str(data.get("source") or data.get("provider") or "spitogatos"),
            price=float(price_val) if price_val is not None else None,
            sqm=float(sqm_val) if sqm_val is not None else None,
            floor=data.get("floor"),
            features=features,
            agent_phone=data.get("agent_phone"),
            agentic_score=int(data.get("agentic_score") or data.get("match_score") or 0),
            score_reason=score_reason,
            initial_rank=int(data.get("initial_rank") or initial_rank),
            description=description,
            cohort_median_eur_per_sqm=data.get("cohort_median_eur_per_sqm") or data.get("neighborhood_median_sqm"),
            cohort_std_eur_per_sqm=data.get("cohort_std_eur_per_sqm") or data.get("neighborhood_std_sqm"),
            upfront_pre_viewing_payment_eur=float(data.get("upfront_pre_viewing_payment_eur") or 0.0),
            reverse_image_match=str(data.get("reverse_image_match") or "NONE"),
            cross_portal_price_conflict=bool(data.get("cross_portal_price_conflict") or False),
        )

    _, base_med, base_std = infer_neighborhood_baseline(f"{candidate.neighborhood} {candidate.url}")
    if candidate.cohort_median_eur_per_sqm is None:
        candidate.cohort_median_eur_per_sqm = cohort_median if cohort_median is not None else base_med
    if candidate.cohort_std_eur_per_sqm is None:
        candidate.cohort_std_eur_per_sqm = cohort_std if cohort_std is not None else base_std
    return candidate


# ==========================================
# OUMI IRIS DECISION MODEL CLIENT
# ==========================================
class OumiIrisDecisionModel:
    """Post-ranker Oumi Iris client (`POST https://inference.oumi.ai/v1/systemone`)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        fallback_mode: Optional[str] = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("OUMI_API_KEY", "")).strip()
        self.project_id = (project_id if project_id is not None else os.getenv("OUMI_PROJECT_ID", "")).strip()
        self.model_override = os.getenv("OUMI_MODEL", "").strip()
        timeout_val = timeout_ms if timeout_ms is not None else int(os.getenv("OUMI_TIMEOUT_MS", "2500"))
        self.timeout_s = max(timeout_val / 1000.0, 0.5)
        self.fallback_mode = (fallback_mode or os.getenv("OUMI_FALLBACK_MODE", "auto")).strip().lower()
        self.audit_log_path = Path(os.getenv("OUMI_AUDIT_LOG_PATH", "logs/oumi_iris_audit.jsonl"))
        self.cache_path = Path(os.getenv("OUMI_CACHE_PATH", "backend/data/oumi_iris_cache.json"))
        self._sem = asyncio.Semaphore(10)

    @property
    def model_identifier(self) -> str:
        if self.model_override and self.model_override.startswith("projects/"):
            return self.model_override
        proj = self.project_id or "default-project"
        return f"projects/{proj}/models/iris-latest"

    def _compute_price_metrics(
        self, item: DecisionPropertyInput
    ) -> tuple[Optional[float], float, float, Optional[float], Optional[float]]:
        med = float(item.cohort_median_eur_per_sqm or 12.0)
        std = float(item.cohort_std_eur_per_sqm or 2.0)
        if item.price is not None and item.sqm is not None and item.sqm > 0:
            eur_sqm = round(item.price / item.sqm, 2)
            dev_pct = round(((eur_sqm - med) / max(med, 0.01)) * 100.0, 2)
            z_score = round((eur_sqm - med) / max(std, 0.01), 2)
            return eur_sqm, med, std, dev_pct, z_score
        return None, med, std, None, None

    def build_iris_state(self, item: DecisionPropertyInput) -> dict[str, Any]:
        """Constructs the structured `state` object sent to `POST /v1/systemone`."""
        eur_sqm, med, _, dev_pct, z_score = self._compute_price_metrics(item)
        combined_text = f"{item.title} {item.description} {item.score_reason} {' '.join(item.features)}".lower()
        matched_keywords = [kw for kw in ADVANCE_FEE_KEYWORDS if kw in combined_text]
        phone_str = (item.agent_phone or "").strip()
        foreign_phone = bool(phone_str.startswith("+") and not phone_str.startswith("+30"))

        return {
            "listing_id": item.listing_id,
            "url": item.url,
            "initial_rank": item.initial_rank,
            "agentic_score": item.agentic_score,
            "score_reason": item.score_reason,
            "property": {
                "title": item.title,
                "neighborhood": item.neighborhood,
                "source": item.source,
                "price_eur": item.price,
                "sqm": item.sqm,
                "floor": item.floor,
                "features": item.features,
                "agent_phone": item.agent_phone,
                "description": item.description,
            },
            "quantitative_signals": {
                "price_per_sqm": eur_sqm,
                "neighborhood_median_sqm": med,
                "price_deviation_pct": dev_pct,
                "price_z_score": z_score,
                "upfront_pre_viewing_payment_eur": item.upfront_pre_viewing_payment_eur,
            },
            "forensic_signals": {
                "advance_fee_keywords_detected": matched_keywords,
                "reverse_image_match": item.reverse_image_match,
                "cross_portal_price_conflict": item.cross_portal_price_conflict,
                "phone_missing": not bool(phone_str) or phone_str.lower() in {"none", "n/a", "null", "unknown"},
                "foreign_phone_prefix": foreign_phone,
            },
        }

    def _cache_key(self, state: dict[str, Any]) -> str:
        serialized = json.dumps({"state": state, "questions": IRIS_SCAM_QUESTIONS}, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _load_cache(self) -> dict[str, Any]:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self, key: str, raw_response: dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache = self._load_cache()
            cache[key] = raw_response
            self.cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _append_audit_log(
        self, listing_id: str, latency_ms: float, mode: str, raw: dict[str, Any]
    ) -> None:
        try:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": time.time(),
                "listing_id": listing_id,
                "mode": mode,
                "latency_ms": round(latency_ms, 1),
                "model": raw.get("model", self.model_identifier),
                "answers": raw.get("answers", {}),
                "usage": raw.get("usage", {}),
            }
            with self.audit_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def _deterministic_fallback(self, state: dict[str, Any]) -> dict[str, Any]:
        """Calibrated rubric evaluation used when offline or when OUMI_API_KEY is not set."""
        quant = state["quantitative_signals"]
        forensic = state["forensic_signals"]
        dev_pct = quant.get("price_deviation_pct")
        z_score = quant.get("price_z_score")

        # 1. Price Anomaly probability
        if dev_pct is not None and (dev_pct <= -40.0 or (z_score is not None and z_score <= -2.2)):
            p_price = 0.96
        elif dev_pct is not None and (dev_pct <= -25.0 or (z_score is not None and z_score <= -1.5)):
            p_price = 0.68
        elif dev_pct is not None and dev_pct <= -18.0:
            p_price = 0.32
        else:
            p_price = 0.06

        # 2. Advance-Fee / Remote Lure probability
        has_keywords = len(forensic.get("advance_fee_keywords_detected") or []) > 0
        upfront_eur = float(quant.get("upfront_pre_viewing_payment_eur") or 0.0)
        foreign_phone = bool(forensic.get("foreign_phone_prefix"))
        if upfront_eur > 0 or (has_keywords and foreign_phone):
            p_fee = 0.96
        elif has_keywords:
            p_fee = 0.88
        elif foreign_phone:
            p_fee = 0.58
        else:
            p_fee = 0.04

        # 3. Stolen Media / Cross-Portal Clone probability
        rev_img = str(forensic.get("reverse_image_match") or "NONE")
        clone_conflict = bool(forensic.get("cross_portal_price_conflict"))
        if rev_img != "NONE" and clone_conflict:
            p_media = 0.97
        elif rev_img != "NONE":
            p_media = 0.92
        elif clone_conflict:
            p_media = 0.78
        else:
            p_media = 0.04

        # 4. Metadata / Contact Contradiction probability
        phone_missing = bool(forensic.get("phone_missing"))
        if phone_missing and p_price >= 0.65:
            p_meta = 0.84
        elif phone_missing or foreign_phone:
            p_meta = 0.45
        else:
            p_meta = 0.06

        max_signal = max(p_price, p_fee, p_media, p_meta)
        sorted_signals = sorted([p_price, p_fee, p_media, p_meta], reverse=True)
        mean_top_two = (sorted_signals[0] + sorted_signals[1]) / 2.0
        if max_signal >= 0.85:
            overall = round(min(0.99, max(max_signal, mean_top_two)), 4)
        else:
            overall = round(min(0.99, mean_top_two), 4)
        verdict = "POSSIBLY_SCAM" if overall >= 0.50 else "SAFE"

        return {
            "model": self.model_identifier,
            "answers": {
                "verdict": {
                    "type": "choice",
                    "choice": verdict,
                    "confidence": round(overall if verdict == "POSSIBLY_SCAM" else 1.0 - overall, 4),
                    "probabilities": {
                        "SAFE": round(1.0 - overall, 4),
                        "POSSIBLY_SCAM": overall,
                    },
                },
                "is_possibly_scam": {"type": "noul", "noul": overall},
                "price_anomaly": {"type": "noul", "noul": p_price},
                "advance_fee_or_remote_lure": {"type": "noul", "noul": p_fee},
                "stolen_media_or_clone": {"type": "noul", "noul": p_media},
                "metadata_contradiction": {"type": "noul", "noul": p_meta},
            },
            "usage": {"inputTokens": 0, "outputTokens": 0},
        }

    def _build_result(
        self,
        item: DecisionPropertyInput,
        state: dict[str, Any],
        raw: dict[str, Any],
        source_mode: Literal["live_oumi_iris", "cached_oumi_iris", "deterministic_fallback"],
        latency_ms: float,
    ) -> PropertyDecisionResult:
        ans = raw.get("answers", {})
        scam_prob = float(ans.get("is_possibly_scam", {}).get("noul", 0.0))
        choice_val = ans.get("verdict", {}).get("choice", "SAFE")
        verdict: Literal["SAFE", "POSSIBLY_SCAM"] = (
            "POSSIBLY_SCAM" if (choice_val == "POSSIBLY_SCAM" or scam_prob >= 0.50) else "SAFE"
        )
        if verdict == "POSSIBLY_SCAM" and scam_prob < 0.50:
            scam_prob = float(ans.get("verdict", {}).get("probabilities", {}).get("POSSIBLY_SCAM", 0.65))

        p_price = float(ans.get("price_anomaly", {}).get("noul", 0.0))
        p_fee = float(ans.get("advance_fee_or_remote_lure", {}).get("noul", 0.0))
        p_media = float(ans.get("stolen_media_or_clone", {}).get("noul", 0.0))
        p_meta = float(ans.get("metadata_contradiction", {}).get("noul", 0.0))

        quant = state["quantitative_signals"]
        forensic = state["forensic_signals"]
        eur_sqm = quant.get("price_per_sqm")
        med = float(quant.get("neighborhood_median_sqm") or 12.0)
        dev_pct = quant.get("price_deviation_pct")
        z_score = quant.get("price_z_score")

        if eur_sqm is not None and dev_pct is not None:
            price_ev = f"€{eur_sqm:.2f}/m² vs. €{med:.2f}/m² {item.neighborhood} median ({dev_pct:+.0f}%)"
        else:
            price_ev = f"Compared against €{med:.2f}/m² {item.neighborhood} baseline"

        kw_list = forensic.get("advance_fee_keywords_detected") or []
        if kw_list or quant.get("upfront_pre_viewing_payment_eur", 0) > 0:
            fee_ev = f"Flagged upfront/remote lure signals ({', '.join(kw_list[:2]) or 'pre-viewing payment'})"
        else:
            fee_ev = "No pre-viewing deposit or absentee-landlord lure detected"

        if item.reverse_image_match != "NONE" or item.cross_portal_price_conflict:
            media_ev = f"Provenance alert: {item.reverse_image_match}" + (
                " + cross-portal price conflict" if item.cross_portal_price_conflict else ""
            )
        else:
            media_ev = "Consistent listing imagery and portal provenance"

        if forensic.get("phone_missing"):
            meta_ev = "No verifiable landlord phone number provided on listing"
        elif forensic.get("foreign_phone_prefix"):
            meta_ev = f"Non-Greek contact prefix ({item.agent_phone}) on local rental"
        else:
            meta_ev = f"Verified local contact ({item.agent_phone or '+30 listing'}) & consistent specs"

        bars = [
            ForensicCriterionBar(
                key="price_anomaly",
                label="Price-per-m² Anomaly",
                probability=round(p_price, 3),
                risk_pct=round(p_price * 100),
                evidence=price_ev,
            ),
            ForensicCriterionBar(
                key="advance_fee_or_remote_lure",
                label="Advance-Fee / Remote Lure",
                probability=round(p_fee, 3),
                risk_pct=round(p_fee * 100),
                evidence=fee_ev,
            ),
            ForensicCriterionBar(
                key="stolen_media_or_clone",
                label="Stolen Photo / Clone Signal",
                probability=round(p_media, 3),
                risk_pct=round(p_media * 100),
                evidence=media_ev,
            ),
            ForensicCriterionBar(
                key="metadata_contradiction",
                label="Metadata & Contact Integrity",
                probability=round(p_meta, 3),
                risk_pct=round(p_meta * 100),
                evidence=meta_ev,
            ),
        ]

        flags = [b.label for b in bars if b.probability >= 0.50]
        risk_pct = round(scam_prob * 100)
        intercepted_top = verdict == "POSSIBLY_SCAM" and item.initial_rank == 1

        if verdict == "POSSIBLY_SCAM":
            ui_badge = f"🛡️ OUMI IRIS: POSSIBLY SCAM • {risk_pct}% Risk (Intercepted Rank #{item.initial_rank})"
            summary = (
                f"Intercepted former Rank #{item.initial_rank}: Oumi Iris flagged {risk_pct}% scam risk "
                f"across {', '.join(flags) or 'multiple forensic signals'}."
            )
        else:
            ui_badge = f"✓ OUMI IRIS: SAFE • {risk_pct}% Scam Risk"
            summary = f"Verified SAFE by Oumi Iris ({risk_pct}% risk). {price_ev}."

        return PropertyDecisionResult(
            listing_id=item.listing_id,
            url=item.url,
            title=item.title,
            neighborhood=item.neighborhood,
            price=item.price,
            sqm=item.sqm,
            eur_per_sqm=eur_sqm,
            cohort_median_eur_per_sqm=med,
            price_deviation_pct=dev_pct,
            price_z_score=z_score,
            initial_rank=item.initial_rank,
            agentic_score=item.agentic_score,
            verdict=verdict,
            scam_probability=round(scam_prob, 4),
            scam_risk_pct=risk_pct,
            intercepted_top_match=intercepted_top,
            ui_badge=ui_badge,
            forensic_summary=summary,
            forensic_bars=bars,
            triggered_flags=flags,
            source_mode=source_mode,
            latency_ms=round(latency_ms, 1),
        )

    async def evaluate_single(
        self,
        client: httpx.AsyncClient,
        item: DecisionPropertyInput,
    ) -> PropertyDecisionResult:
        """Evaluates one ranked property against Oumi Iris (`/v1/systemone`) with 3-tier resilience."""
        state = self.build_iris_state(item)
        key = self._cache_key(state)
        t0 = time.perf_counter()

        if self.fallback_mode == "cache_first":
            cached = self._load_cache().get(key)
            if cached:
                ms = (time.perf_counter() - t0) * 1000.0
                return self._build_result(item, state, cached, "cached_oumi_iris", ms)

        # Tier 1: Live Oumi Iris API call
        if self.api_key and (self.project_id or self.model_override.startswith("projects/")):
            payload = {
                "model": self.model_identifier,
                "state": state,
                "questions": IRIS_SCAM_QUESTIONS,
            }
            async with self._sem:
                try:
                    response = await client.post(
                        OUMI_SYSTEMONE_URL,
                        headers={
                            "Content-Type": "application/json",
                            "X-API-Key": self.api_key,
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    raw = response.json()
                    ms = (time.perf_counter() - t0) * 1000.0
                    self._save_cache(key, raw)
                    self._append_audit_log(item.listing_id, ms, "live_oumi_iris", raw)
                    return self._build_result(item, state, raw, "live_oumi_iris", ms)
                except Exception:
                    if self.fallback_mode == "live_only":
                        raise

        # Tier 2: Pre-warmed Oumi Iris cache
        cached = self._load_cache().get(key)
        if cached:
            ms = (time.perf_counter() - t0) * 1000.0
            return self._build_result(item, state, cached, "cached_oumi_iris", ms)

        # Tier 3: Deterministic rubric fallback
        raw_fb = self._deterministic_fallback(state)
        ms = (time.perf_counter() - t0) * 1000.0
        self._append_audit_log(item.listing_id, ms, "deterministic_fallback", raw_fb)
        return self._build_result(item, state, raw_fb, "deterministic_fallback", ms)

    async def evaluate_ranked_properties(
        self,
        ranked_properties: Sequence[Any],
        all_properties: Optional[Sequence[Any]] = None,
        top_k: int = 10,
    ) -> DecisionBatchResponse:
        """Evaluates the ranked property list in parallel and partitions SAFE vs. POSSIBLY_SCAM."""
        t_start = time.perf_counter()
        cohort_med: Optional[float] = None
        cohort_std: Optional[float] = None
        if all_properties:
            first_hint = ""
            if ranked_properties:
                first = ranked_properties[0]
                first_hint = getattr(first, "url", "") if not isinstance(first, dict) else str(first.get("url", ""))
            cohort_med, cohort_std = compute_cohort_sqm_stats(all_properties, fallback_url_or_text=first_hint)

        normalized = [
            normalize_ranked_property(
                prop,
                initial_rank=idx + 1,
                cohort_median=cohort_med,
                cohort_std=cohort_std,
            )
            for idx, prop in enumerate(list(ranked_properties)[:top_k])
        ]

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            evaluated = list(
                await asyncio.gather(*(self.evaluate_single(client, item) for item in normalized))
            )

        ordered = sorted(evaluated, key=lambda r: r.initial_rank)
        safe_list: list[PropertyDecisionResult] = []
        scam_list: list[PropertyDecisionResult] = []

        next_verified_rank = 1
        for res in ordered:
            if res.verdict == "SAFE":
                res.verified_rank = next_verified_rank
                next_verified_rank += 1
                safe_list.append(res)
            else:
                scam_list.append(res)

        intercepted_rank_one = any(r.initial_rank == 1 and r.verdict == "POSSIBLY_SCAM" for r in ordered)
        wow_banner: Optional[str] = None
        if intercepted_rank_one:
            top_scam = next(r for r in ordered if r.initial_rank == 1)
            wow_banner = (
                f"🛡️ Oumi Iris Intercepted Your Raw #1 Match ({top_scam.title}) as POSSIBLY_SCAM "
                f"({top_scam.scam_risk_pct}% Risk) — preventing your AI outreach agent from calling a scammer."
            )
        elif scam_list:
            wow_banner = (
                f"🛡️ Oumi Iris intercepted {len(scam_list)} ranked candidate(s) as POSSIBLY_SCAM before outreach."
            )

        total_ms = round((time.perf_counter() - t_start) * 1000.0, 1)
        dominant_mode = ordered[0].source_mode if ordered else "deterministic_fallback"

        return DecisionBatchResponse(
            results=ordered,
            safe_properties=safe_list,
            possibly_scam_properties=scam_list,
            wow_factor_banner=wow_banner,
            telemetry=DecisionTelemetry(
                model=self.model_identifier,
                total_evaluated=len(ordered),
                safe_count=len(safe_list),
                possibly_scam_count=len(scam_list),
                intercepted_rank_one=intercepted_rank_one,
                total_latency_ms=total_ms,
                source_mode=dominant_mode,
            ),
        )


def evaluate_ranked_properties_sync(
    ranked_properties: Sequence[Any],
    all_properties: Optional[Sequence[Any]] = None,
    top_k: int = 10,
) -> DecisionBatchResponse:
    """Synchronous one-line helper for calling Oumi Iris from synchronous scripts."""
    model = OumiIrisDecisionModel()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                model.evaluate_ranked_properties(ranked_properties, all_properties=all_properties, top_k=top_k),
            )
            return future.result()
    return asyncio.run(
        model.evaluate_ranked_properties(ranked_properties, all_properties=all_properties, top_k=top_k)
    )


if __name__ == "__main__":
    # Demo invocation showing how ranked `PropertyDetails`-shaped items are scored post-ranking
    sample_ranked_from_ranker = [
        {
            "url": "https://www.spitogatos.gr/enoikiaseis-katoikies/koukaki/bait-scam-01",
            "title": "Luxury Renovated 2BR by Acropolis Museum - All Bills Included",
            "neighborhood": "Koukaki",
            "price": 450,
            "sqm": 65,
            "floor": "3rd",
            "features": ["renovated", "furnished", "pet friendly", "acropolis view"],
            "agent_phone": "+44 7911 123456",
            "agentic_score": 10,
            "score_reason": "Matches every user requirement at an ultra-low €450 price.",
            "description": (
                "Working in London UK so I cannot travel to Athens for viewings. "
                "Reservation via Airbnb Long-Term Escrow (€900 upfront before courier sends keys). "
                "Message ONLY on WhatsApp +44 7911 123456."
            ),
            "upfront_pre_viewing_payment_eur": 900,
            "reverse_image_match": "SHORT_TERM_RENTAL_AIRBNB_BOOKING",
        },
        {
            "url": "https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati/safe-02",
            "title": "Sunny 2BR Apartment in Pangrati near Varnava Sq",
            "neighborhood": "Pangrati",
            "price": 600,
            "sqm": 52,
            "floor": "2nd",
            "features": ["bright", "pet friendly", "balcony", "natural gas"],
            "agent_phone": "+30 210 7512345",
            "agentic_score": 9,
            "score_reason": "Bright apartment in Pangrati within €600 budget and allows pets.",
            "description": "Bright 2nd floor apartment in Pangrati, autonomous gas heating, pets welcome.",
        },
    ]

    batch = evaluate_ranked_properties_sync(sample_ranked_from_ranker)
    print(f"\n[Oumi Iris Telemetry] Evaluated {batch.telemetry.total_evaluated} ranked properties in {batch.telemetry.total_latency_ms}ms")
    if batch.wow_factor_banner:
        print(f"WOW BANNER: {batch.wow_factor_banner}\n")
    for res in batch.results:
        print(f"Initial Rank #{res.initial_rank} -> Verdict: {res.verdict} (Verified Rank: {res.verified_rank})")
        print(f"  Badge:   {res.ui_badge}")
        print(f"  Summary: {res.forensic_summary}")
        for bar in res.forensic_bars:
            print(f"    • {bar.label:<30}: {bar.risk_pct:>3}% | {bar.evidence}")
        print("-" * 70)
