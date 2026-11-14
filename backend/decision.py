"""Post-ranker Oumi Iris Decision Model (`POST https://inference.oumi.ai/v1/systemone`).

Evaluates ranked properties in parallel and classifies each as `SAFE` or `POSSIBLY_SCAM`
with calibrated forensic rubric probabilities for the frontend UI.
"""

from __future__ import annotations

import asyncio
import os
import statistics
from typing import Any, Literal, Optional, Sequence

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

OUMI_SYSTEMONE_URL = "https://inference.oumi.ai/v1/systemone"

IRIS_QUESTIONS: dict[str, Any] = {
    "verdict": {
        "type": "choice",
        "instructions": "Classify this ranked residential rental listing as SAFE or POSSIBLY_SCAM.",
        "criteria": {
            "SAFE": "Plausible residential rental with realistic market pricing, consistent specs, verifiable contact info, and normal in-person viewing terms.",
            "POSSIBLY_SCAM": "Exhibits rental scam or bait indicators: unrealistic underpricing vs. cohort, upfront payment/escrow before viewing, remote landlord claims, stolen/cloned media, or contradictory/missing specs.",
        },
    },
    "is_possibly_scam": {
        "type": "noul",
        "instructions": "What is the probability that this ranked rental listing is fraudulent or a bait scam?",
        "criteria": {
            "true": "The listing shows pricing, financial, media, or contact red flags.",
            "false": "The listing appears to be a legitimate rental offering.",
        },
    },
    "price_anomaly": {
        "type": "noul",
        "instructions": "Is the rental price per square meter unrealistically low compared to the search cohort and property features?",
        "criteria": {
            "true": "Price per m² is abnormally low relative to the cohort median or advertised condition.",
            "false": "Price per m² is within a realistic range for the cohort.",
        },
    },
    "advance_fee_lure": {
        "type": "noul",
        "instructions": "Does the listing request upfront payment/escrow before viewing or claim an unavailable/remote landlord?",
        "criteria": {
            "true": "Mentions pre-viewing deposits, external platform escrow, courier key delivery, or absentee owner.",
            "false": "Allows standard in-person viewing prior to payment.",
        },
    },
    "stolen_or_cloned_media": {
        "type": "noul",
        "instructions": "Are there signs of stolen short-term rental photos or conflicting duplicate listings?",
        "criteria": {
            "true": "Signals indicate reused short-term rental/stock imagery or conflicting cross-portal data.",
            "false": "Media and listing provenance appear consistent.",
        },
    },
    "metadata_inconsistency": {
        "type": "noul",
        "instructions": "Are there contradictions in property attributes or missing/suspicious landlord contact details?",
        "criteria": {
            "true": "Contradictory property specs or unverified/missing landlord contact on a high-match listing.",
            "false": "Property metadata and contact details are consistent.",
        },
    },
}


class PropertyDecision(BaseModel):
    """Oumi Iris scam decision and forensic probabilities for a single ranked property."""

    url: str
    initial_rank: int = Field(description="1-based rank from the feature ranker.")
    verified_rank: Optional[int] = Field(
        default=None,
        description="Re-indexed 1-based rank among SAFE properties (None if POSSIBLY_SCAM).",
    )
    verdict: Literal["SAFE", "POSSIBLY_SCAM"]
    scam_probability: float = Field(description="Overall scam probability (0.0 to 1.0).")
    scam_risk_pct: int = Field(description="Scam risk percentage (0 to 100) for frontend display.")
    rubric_probabilities: dict[str, float] = Field(
        default_factory=dict,
        description="Per-criterion probabilities (0.0 to 1.0) from Oumi Iris.",
    )
    property_data: dict[str, Any] = Field(default_factory=dict)


class DecisionBatchResponse(BaseModel):
    """Aggregated post-ranker Oumi Iris decisions for the frontend."""

    results: list[PropertyDecision]
    safe_properties: list[PropertyDecision]
    possibly_scam_properties: list[PropertyDecision]
    intercepted_top_match: bool = Field(
        default=False,
        description="True if initial_rank #1 was flagged as POSSIBLY_SCAM.",
    )


def _to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, BaseModel):
        return item.model_dump()
    if isinstance(item, dict):
        return dict(item)
    return dict(item.__dict__)


def _compute_cohort_median_sqm(properties: Sequence[ dict[str, Any] ]) -> Optional[float]:
    ratios = [
        float(p["price"]) / float(p["sqm"])
        for p in properties
        if p.get("price") and p.get("sqm") and float(p["sqm"]) > 0
    ]
    return round(float(statistics.median(ratios)), 2) if ratios else None


def build_iris_state(
    prop: dict[str, Any],
    initial_rank: int,
    cohort_median_eur_per_sqm: Optional[float] = None,
) -> dict[str, Any]:
    """Builds the location-agnostic `state` payload for a single ranked property."""
    price = prop.get("price")
    sqm = prop.get("sqm")
    eur_per_sqm = round(float(price) / float(sqm), 2) if (price and sqm and float(sqm) > 0) else None
    deviation_pct = (
        round(((eur_per_sqm - cohort_median_eur_per_sqm) / cohort_median_eur_per_sqm) * 100, 1)
        if (eur_per_sqm is not None and cohort_median_eur_per_sqm)
        else None
    )
    return {
        "initial_rank": initial_rank,
        "property": prop,
        "price_signals": {
            "eur_per_sqm": eur_per_sqm,
            "cohort_median_eur_per_sqm": cohort_median_eur_per_sqm,
            "deviation_from_cohort_pct": deviation_pct,
        },
    }


async def _evaluate_one(
    client: httpx.AsyncClient,
    model_id: str,
    api_key: str,
    prop: dict[str, Any],
    initial_rank: int,
    cohort_median_sqm: Optional[float],
) -> PropertyDecision:
    state = build_iris_state(prop, initial_rank=initial_rank, cohort_median_eur_per_sqm=cohort_median_sqm)
    resp = await client.post(
        OUMI_SYSTEMONE_URL,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        json={"model": model_id, "state": state, "questions": IRIS_QUESTIONS},
    )
    resp.raise_for_status()
    answers = resp.json()["answers"]

    scam_prob = float(answers["is_possibly_scam"]["noul"])
    choice = answers["verdict"]["choice"]
    verdict: Literal["SAFE", "POSSIBLY_SCAM"] = (
        "POSSIBLY_SCAM" if (choice == "POSSIBLY_SCAM" or scam_prob >= 0.50) else "SAFE"
    )
    rubric = {
        key: round(float(answers[key]["noul"]), 4)
        for key in ("price_anomaly", "advance_fee_lure", "stolen_or_cloned_media", "metadata_inconsistency")
        if key in answers
    }
    return PropertyDecision(
        url=str(prop.get("url") or f"property-{initial_rank}"),
        initial_rank=initial_rank,
        verdict=verdict,
        scam_probability=round(scam_prob, 4),
        scam_risk_pct=round(scam_prob * 100),
        rubric_probabilities=rubric,
        property_data=prop,
    )


async def evaluate_ranked_properties(
    ranked_properties: Sequence[Any],
    all_properties: Optional[Sequence[Any]] = None,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> DecisionBatchResponse:
    """Evaluates ranked properties in parallel with Oumi Iris (`/v1/systemone`)."""
    resolved_key = (api_key or os.getenv("OUMI_API_KEY", "")).strip()
    resolved_project = (project_id or os.getenv("OUMI_PROJECT_ID", "")).strip()
    if not resolved_key or not resolved_project:
        raise ValueError("OUMI_API_KEY and OUMI_PROJECT_ID must be set to call Oumi Iris.")

    model_id = f"projects/{resolved_project}/models/iris-latest"
    ranked_dicts = [_to_dict(p) for p in ranked_properties]
    cohort_source = [_to_dict(p) for p in all_properties] if all_properties else ranked_dicts
    cohort_median = _compute_cohort_median_sqm(cohort_source)

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=15.0)
    try:
        decisions = list(
            await asyncio.gather(
                *(
                    _evaluate_one(http_client, model_id, resolved_key, prop, idx + 1, cohort_median)
                    for idx, prop in enumerate(ranked_dicts)
                )
            )
        )
    finally:
        if owns_client:
            await http_client.aclose()

    decisions.sort(key=lambda d: d.initial_rank)
    safe_list: list[PropertyDecision] = []
    scam_list: list[PropertyDecision] = []

    next_rank = 1
    for dec in decisions:
        if dec.verdict == "SAFE":
            dec.verified_rank = next_rank
            next_rank += 1
            safe_list.append(dec)
        else:
            scam_list.append(dec)

    return DecisionBatchResponse(
        results=decisions,
        safe_properties=safe_list,
        possibly_scam_properties=scam_list,
        intercepted_top_match=any(d.initial_rank == 1 and d.verdict == "POSSIBLY_SCAM" for d in decisions),
    )


def evaluate_ranked_properties_sync(
    ranked_properties: Sequence[Any],
    all_properties: Optional[Sequence[Any]] = None,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
) -> DecisionBatchResponse:
    """Synchronous wrapper for calling Oumi Iris from synchronous pipelines."""
    return asyncio.run(
        evaluate_ranked_properties(
            ranked_properties,
            all_properties=all_properties,
            api_key=api_key,
            project_id=project_id,
        )
    )
