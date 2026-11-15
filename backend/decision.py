"""Post-ranker Oumi Iris Decision Model (`POST https://inference.oumi.ai/v1/systemone`).

Evaluates ranked properties in parallel and classifies each as `SAFE` or `POSSIBLY_SCAM`,
keeping per-criterion rubric probabilities internal and exposing a plain-English `scam_reason`
when a listing is flagged.
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
SCAM_THRESHOLD = 0.50

# Plain-English label for each red-flag question. Only the strongest flag is shown to the user.
RED_FLAG_LABELS: dict[str, str] = {
    "price_anomaly": "Price is far below similar listings in the area",
    "advance_fee_lure": "Asks for money before a viewing or claims the owner is away",
    "stolen_or_cloned_media": "Photos look reused from another listing",
    "metadata_inconsistency": "Listing details directly contradict each other",
}


def normalize_project_id(raw: Optional[str]) -> str:
    """Accepts `abc`, `projects/abc` or `projects/abc/models/iris-latest` and returns `abc`."""
    value = (raw or "").strip().lstrip("/")
    if value.startswith("projects/"):
        value = value[len("projects/"):]
    return value.split("/models/", 1)[0].strip(" /")


def oumi_configured() -> bool:
    return bool(os.getenv("OUMI_API_KEY", "").strip() and normalize_project_id(os.getenv("OUMI_PROJECT_ID")))


def model_path(project_id: str) -> str:
    return f"projects/{normalize_project_id(project_id)}/models/iris-latest"

IRIS_QUESTIONS: dict[str, Any] = {
    "verdict": {
        "type": "choice",
        "instructions": (
            "Classify this ranked residential rental listing as SAFE or POSSIBLY_SCAM. "
            "Be relaxed on normal market listings: larger apartments (80-120+ m²) naturally have a "
            "lower €/m² than small flats, and listings from real-estate agencies or with masked/null "
            "portal contacts and normal follow-up questions (missing_info) are SAFE. Only flag "
            "POSSIBLY_SCAM when there are unmistakable fraud signals."
        ),
        "criteria": {
            "SAFE": "Normal residential rental (including larger apartments with lower €/m² or agency listings) without advance-fee lures or absurd bait pricing.",
            "POSSIBLY_SCAM": "Unmistakable rental scam or bait: extreme bait underpricing (>50% below cohort median, e.g. €250-€350 for a large renovated flat), upfront deposit/wire/escrow requests before viewing, absentee-owner key-shipping stories, or blatantly contradictory specs.",
        },
    },
    "is_possibly_scam": {
        "type": "noul",
        "instructions": (
            "What is the probability that this ranked rental listing is a fraudulent bait scam? "
            "Do NOT penalize larger apartments having a lower €/m² (e.g. 20-40% below smaller flats), "
            "named real-estate agencies, masked/null portal contact fields, or normal missing_info questions."
        ),
        "criteria": {
            "true": "Clear scam bait: absurdly low total rent (>50% below cohort median), upfront payment/courier lures before viewing, or stolen luxury media.",
            "false": "Legitimate rental listing at a plausible monthly rent (even if €/m² is lower due to larger size or older condition).",
        },
    },
    "price_anomaly": {
        "type": "noul",
        "instructions": (
            "Is the rental price absurdly low scam-bait compared to the cohort (>50% below median)? "
            "Note: a 20-40% lower €/m² on a large (80-120+ m²) or unrenovated apartment at normal monthly rent (€600-€1200+) is normal and NOT a price anomaly."
        ),
        "criteria": {
            "true": "Price per m² is >50% below the cohort median with unrealistically low total monthly rent (e.g. €250-€350 for a large renovated flat).",
            "false": "Price is plausible for the apartment's size and condition (including larger flats with lower €/m²).",
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
            "true": "Signals indicate reused short-term rental/stock imagery paired with bait pricing or conflicting cross-portal data.",
            "false": "Media and listing provenance appear consistent.",
        },
    },
    "metadata_inconsistency": {
        "type": "noul",
        "instructions": (
            "Do the property attributes directly contradict each other (e.g. impossible size, room count, or floor)? "
            "Ignore null phone/email fields or normal missing_info questions."
        ),
        "criteria": {
            "true": "Direct contradictions in size, rooms, floor, or location within the listing.",
            "false": "Property specs are internally consistent (masked phone/email on a portal is normal).",
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
        description="Per-criterion probabilities (0.0 to 1.0) from Oumi Iris (internal; not shown in the UI).",
    )
    scam_reason: Optional[str] = Field(
        default=None,
        description="Plain-English label of the strongest red flag, only when the listing is flagged.",
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


def _compute_cohort_median_sqm(properties: Sequence[dict[str, Any]]) -> Optional[float]:
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
    answers = resp.json().get("answers") or {}
    scam_answer = answers.get("is_possibly_scam")
    if not isinstance(scam_answer, dict) or scam_answer.get("noul") is None:
        raise ValueError(f"Oumi Iris response has no 'is_possibly_scam' answer: {sorted(answers)}")

    scam_prob = float(scam_answer["noul"])
    verdict: Literal["SAFE", "POSSIBLY_SCAM"] = (
        "POSSIBLY_SCAM" if scam_prob >= SCAM_THRESHOLD else "SAFE"
    )
    rubric = {
        key: round(float(answers[key]["noul"]), 4)
        for key in RED_FLAG_LABELS
        if isinstance(answers.get(key), dict) and answers[key].get("noul") is not None
    }
    return PropertyDecision(
        url=str(prop.get("url") or f"property-{initial_rank}"),
        initial_rank=initial_rank,
        verdict=verdict,
        scam_probability=round(scam_prob, 4),
        scam_risk_pct=round(scam_prob * 100),
        rubric_probabilities=rubric,
        scam_reason=top_red_flag(rubric) if verdict == "POSSIBLY_SCAM" else None,
        property_data=prop,
    )


def top_red_flag(rubric: dict[str, float]) -> Optional[str]:
    """The single strongest red flag as a sentence, or None if no flag crosses the threshold."""
    candidates = [(key, rubric[key]) for key in RED_FLAG_LABELS if key in rubric]
    if not candidates:
        return None
    key, prob = max(candidates, key=lambda kv: kv[1])
    return RED_FLAG_LABELS[key] if prob >= SCAM_THRESHOLD else None


async def evaluate_ranked_properties(
    ranked_properties: Sequence[Any],
    all_properties: Optional[Sequence[Any]] = None,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> DecisionBatchResponse:
    """Evaluates ranked properties in parallel with Oumi Iris (`/v1/systemone`)."""
    resolved_key = (api_key or os.getenv("OUMI_API_KEY", "")).strip()
    resolved_project = normalize_project_id(project_id or os.getenv("OUMI_PROJECT_ID", ""))
    if not resolved_key or not resolved_project:
        raise ValueError("OUMI_API_KEY and OUMI_PROJECT_ID must be set to call Oumi Iris.")

    ranked_dicts = [_to_dict(p) for p in ranked_properties]
    if not ranked_dicts:
        return DecisionBatchResponse(
            results=[],
            safe_properties=[],
            possibly_scam_properties=[],
            intercepted_top_match=False,
        )

    model_id = model_path(resolved_project)
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


def probe_oumi(timeout: float = 15.0, client: Optional[httpx.Client] = None) -> tuple[bool, str]:
    """One tiny live Iris call (a single yes/no question) to check the key, project and endpoint."""
    key = os.getenv("OUMI_API_KEY", "").strip()
    project = normalize_project_id(os.getenv("OUMI_PROJECT_ID"))
    if not key or not project:
        return False, "OUMI_API_KEY / OUMI_PROJECT_ID not set"
    body = {
        "model": model_path(project),
        "state": "Bright 60 m² apartment in Pangrati for €650/month. Viewing by appointment.",
        "questions": {"is_rental": {"type": "noul", "instructions": "Is this a rental listing?"}},
    }
    http = client or httpx.Client(timeout=timeout)
    try:
        resp = http.post(
            OUMI_SYSTEMONE_URL,
            headers={"Content-Type": "application/json", "X-API-Key": key},
            json=body,
        )
    except httpx.HTTPError as exc:
        return False, f"request failed: {exc!r}"
    finally:
        if client is None:
            http.close()
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    try:
        prob = float(resp.json()["answers"]["is_rental"]["noul"])
    except (KeyError, TypeError, ValueError):
        return False, f"unexpected response: {resp.text[:200]}"
    return True, f"Iris answered ({model_path(project)}, sample p={prob:.2f})"


if __name__ == "__main__":  # uv run python -m backend.decision
    ok, detail = probe_oumi()
    print(("OK   " if ok else "FAIL ") + detail)
    raise SystemExit(0 if ok else 1)
