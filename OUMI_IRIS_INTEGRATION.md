# Oumi `Iris` Decision Model — Post-Ranker Integration Guide

> **Purpose:** Technical reference and implementation contract for integrating **Oumi's `Iris` Decision Model** into our autonomous housing relocation pipeline (`POST https://inference.oumi.ai/v1/systemone`).  
> **Scope Constraint:** `Iris` operates **strictly as our post-ranking rental scam decision gate**, classifying each ranked listing as **`SAFE`** or **`POSSIBLY_SCAM`** with calibrated forensic probabilities. It does **not** select or decide landlord outreach channels or messaging strategies.

---

## 1. Overview & Architectural Role (Post-Ranker Decision Gate)

Instead of evaluating 100+ raw scraped listings up front, **Oumi `Iris` runs directly *after* the Feature Ranker** on the Top-$K$ highest-matching candidates (`K = 8–10`):

```text
[1. Multi-Source Provider Ingestion & Deduplication]
    Spitogatos + XE.gr + Plot.gr + Facebook Marketplace -> Normalized Clusters (N listings)
    Computes neighborhood €/m² cohort baselines (median & standard deviation)
          │
          ▼
[2. Feature Ranker & Missing-Info Detector (MatchRanker)]
    • Scores all N listings against user hard constraints & preferences (0–100% Match)
    • Assigns initial_rank (#1 .. #N) and detects unstated property attributes
    • Applies Top-K Cutoff (Top 8–10 finalists)
          │
          ▼
[3. Oumi Iris Decision Model (ScamGuard — Post-Ranker Gate)]
    • Evaluates ONLY the Top-K ranked finalists concurrently via asyncio.gather (~0.5–1.2s)
    • Receives ranked context: initial_rank, match_score, cohort €/m² Z-score, NLP & photo flags
    • Outputs strict verdict: SAFE vs. POSSIBLY_SCAM + 4 parallel forensic rubric probabilities
          │
          ├──► Stream A: Verified SAFE Ranked Shortlist (re-indexed Verified Rank #1, #2, #3...)
          │      Ready for Human Approval Gate -> 1-Agent-Per-Landlord Outreach Swarm
          │
          └──► Stream B: Intercepted High-Rank Bait Scams (POSSIBLY_SCAM)
                 Shows "Would Have Ranked #1 (98% Match) — Intercepted by Oumi Iris" (Frontend Wow Factor)
```

### Why Running `Iris` *After* Ranking Is Better
1. **~90% Credit & Latency Efficiency:** Multi-portal search easily returns 60–150+ listings, most of which fail budget or size constraints. Scoring features deterministically takes `<50 ms`; calling Oumi `Iris` only on the Top-$K$ finalists via `asyncio.gather` finishes in **~0.5–1.2 seconds total** while preserving hackathon API credits.
2. **Richer Context (`state`) for `Iris` ("Too-Good-To-Be-True" Detection):** Rental scammers deliberately stuff bait ads with every sought-after keyword (*renovated, Acropolis view, pets welcome, bills included*) at 50%+ below market rent so they float to `#1`. Because the Ranker runs first, we feed `initial_rank`, `feature_match_score`, and the exact `price_z_score` vs. neighborhood cohort directly into `Iris`’s `state`.
3. **Maximum Frontend "Wow Factor":** Rather than hiding anonymous rejected junk in a footnote, the UI proves why simple feature matching is dangerous without a Decision Model—visibly intercepting a listing that would have been **Raw Rank `#1` (98% Match)** right before the user or outreach agents ever contact a scammer.

---

## 2. Oumi `Iris` API Specification (`/v1/systemone`)

Oumi's Decision Model endpoint does **not** generate open-ended chat tokens (`outputTokens: 0`). In one forward pass, it takes a structured `state` and a map of `questions` and scores every question in parallel with calibrated probabilities (`0.0–1.0`).

| Parameter | Value |
| :--- | :--- |
| **Endpoint** | `POST https://inference.oumi.ai/v1/systemone` |
| **Headers** | `X-API-Key: $OUMI_API_KEY`, `Content-Type: application/json` |
| **Pretrained Model Identifier** | `projects/{project_id}/models/iris-latest` |
| **Execution Pattern** | 1 request per Top-$K$ listing, fired concurrently with `httpx.AsyncClient` + `asyncio.gather` |

### Required Environment Variables (`.env` / `.env.example`)
```dotenv
OUMI_API_KEY=your_oumi_api_key_here
OUMI_PROJECT_ID=your_oumi_project_id_here
OUMI_TIMEOUT_MS=2500
# "auto" = Live Oumi Iris -> Pre-warmed Oumi cache -> Deterministic heuristic fallback
OUMI_FALLBACK_MODE=auto
OUMI_AUDIT_LOG_PATH=logs/oumi_iris_audit.jsonl
```

### Question Types Supported by `/v1/systemone`
- **`choice`:** Multi-class verdict across explicit keys (used for `verdict`: `"SAFE"` vs. `"POSSIBLY_SCAM"`). Returns winning `choice`, `confidence`, and full `probabilities`.
- **`noul`:** Binary probability `0.0–1.0` that a condition is `true` (used for overall `is_possibly_scam` and the 4 forensic rubric bars displayed in the UI).

---

## 3. Exact Request & Response Contract (`SAFE` vs. `POSSIBLY_SCAM`)

Every call sends **one** ranked listing (`state`) alongside **six parallel questions** (`questions`) focused exclusively on rental scam classification and forensic transparency.

### 3.1 Request Payload Example (`POST https://inference.oumi.ai/v1/systemone`)

```json
{
  "model": "projects/{project_id}/models/iris-latest",
  "state": {
    "listing_id": "ath_cluster_koukaki_01",
    "initial_rank": 1,
    "feature_match_score": 98,
    "property": {
      "title": "Luxury Renovated 2BR Apartment by Acropolis Museum - All Bills Included",
      "neighborhood": "Koukaki",
      "source": "fb_marketplace",
      "price_eur": 450,
      "sqm": 65,
      "description": "Fully furnished designer flat in Koukaki, 3 mins from Syggrou-Fix metro. Working in London UK so I cannot travel for viewings. Reservation via Airbnb Long-Term Escrow (€900 upfront before courier sends keys). Message ONLY on WhatsApp +44 7911 123456."
    },
    "quantitative_signals": {
      "price_per_sqm": 6.92,
      "neighborhood_median_sqm": 16.00,
      "price_deviation_pct": -56.75,
      "price_z_score": -3.43,
      "deposit_months_requested": 1,
      "upfront_pre_viewing_payment_eur": 900
    },
    "forensic_signals": {
      "reverse_image_match": "SHORT_TERM_RENTAL_AIRBNB_BOOKING",
      "cross_portal_price_conflict": false,
      "publisher_type": "ANONYMOUS_SOCIAL_PROFILE",
      "phone_country_code": "+44",
      "missing_mandatory_greek_fields": [
        "pea_energy_class",
        "heating_type_and_medium",
        "monthly_common_charges_koinochrista"
      ]
    }
  },
  "questions": {
    "verdict": {
      "type": "choice",
      "instructions": "Classify this ranked residential rental listing as SAFE or POSSIBLY_SCAM.",
      "criteria": {
        "SAFE": "Realistic neighborhood market price (€/m² aligns with cohort), consistent photos and property metadata, verifiable local contact or agency, and standard in-person viewing with zero pre-viewing payment.",
        "POSSIBLY_SCAM": "Shows credible fraud or bait-listing signals: extreme price-per-m² undervaluation vs. neighborhood median, advance-fee/escrow or landlord-abroad wire demands, WhatsApp/foreign-number isolation, stolen Airbnb/stock imagery, hijacked cross-portal duplicates, or severe metadata contradictions."
      }
    },
    "is_possibly_scam": {
      "type": "noul",
      "instructions": "What is the probability that this ranked rental listing is fraudulent, a bait ad, or an advance-fee scam?",
      "criteria": {
        "true": "Listing exhibits financial, pricing, media, or metadata fraud indicators that put the tenant at risk.",
        "false": "Listing behaves like an authentic residential lease offering."
      }
    },
    "price_anomaly": {
      "type": "noul",
      "instructions": "Is the monthly rent per m² suspiciously below the neighborhood median without a legitimate physical explanation?",
      "criteria": {
        "true": "price_deviation_pct <= -25% or price_z_score <= -1.5 (especially -40%+ bait pricing on a supposedly luxury/renovated home).",
        "false": "Price per m² falls within normal neighborhood variance."
      }
    },
    "advance_fee_or_remote_lure": {
      "type": "noul",
      "instructions": "Does the listing pressure for upfront payment/escrow before viewing or claim an absentee overseas landlord?",
      "criteria": {
        "true": "Requests upfront deposit/wire/Revolut/Airbnb escrow before in-person viewing, claims owner is abroad shipping keys, or enforces WhatsApp/text-only isolation.",
        "false": "Allows normal in-person property viewing and standard AADE Taxisnet lease signing."
      }
    },
    "stolen_media_or_clone": {
      "type": "noul",
      "instructions": "Do reverse-image or cross-portal signals indicate stolen short-term rental photos or a cloned listing?",
      "criteria": {
        "true": "Photos match an active Airbnb/Booking/hotel/stock listing or reappear across portals with conflicting contact details and large price drops.",
        "false": "Original property imagery with consistent cross-portal provenance."
      }
    },
    "metadata_contradiction": {
      "type": "noul",
      "instructions": "Are there physical/metadata contradictions or suspicious stripping of mandatory Greek rental disclosures?",
      "criteria": {
        "true": "Impossible floor geometry, photo vs. attribute conflict, or epically unverified burner profile missing ΠΕΑ energy class, heating type, and common charges together with pricing anomalies.",
        "false": "Specs are internally consistent (ordinary missing fields like pet policy alone do not indicate fraud)."
      }
    }
  }
}
```

### 3.2 Response Payload Example (`200 OK`)

```json
{
  "model": "projects/hackathon-team-01/models/iris-latest",
  "answers": {
    "verdict": {
      "type": "choice",
      "choice": "POSSIBLY_SCAM",
      "confidence": 0.96,
      "probabilities": {
        "SAFE": 0.04,
        "POSSIBLY_SCAM": 0.96
      }
    },
    "is_possibly_scam": {
      "type": "noul",
      "noul": 0.9624
    },
    "price_anomaly": {
      "type": "noul",
      "noul": 0.9815
    },
    "advance_fee_or_remote_lure": {
      "type": "noul",
      "noul": 0.9540
    },
    "stolen_media_or_clone": {
      "type": "noul",
      "noul": 0.9231
    },
    "metadata_contradiction": {
      "type": "noul",
      "noul": 0.8410
    }
  },
  "usage": {
    "inputTokens": 412,
    "outputTokens": 0
  }
}
```

> **Note on Borderline / Moderate Anomalies:** Because `Iris` outputs `SAFE` vs. `POSSIBLY_SCAM`, any listing with moderate-to-high fraud signals (or `is_possibly_scam >= 0.50`) is safely quarantined under `POSSIBLY_SCAM` so the user inspects its forensic bars explicitly rather than blindly launching outreach calls. Meanwhile, ordinary safe listings with missing Greek fields (like unstated `pet_policy` or `κοινόχρηστα`) remain `SAFE` (`is_possibly_scam < 0.50`), and the Ranker's Missing-Info Detector passes those questions to the Outreach Agent.

---

## 4. Reference Python Implementation (`backend/decision_model.py`)

This async client integrates cleanly with FastAPI + `httpx` (already installed in `pyproject.toml`), runs all Top-$K$ evaluations in parallel, supports 3-tier demo resilience (Live Oumi API -> Pre-warmed real Oumi cache -> Deterministic rubric fallback), and writes an append-only audit log for Oumi sponsor judges.

```python
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Literal, Optional
import httpx
from pydantic import BaseModel, Field

OUMI_SYSTEMONE_URL = "https://inference.oumi.ai/v1/systemone"


class RankedPropertyCandidate(BaseModel):
    listing_id: str
    provider: str  # "spitogatos" | "xe_gr" | "plot_gr" | "fb_marketplace"
    title: str
    neighborhood: str
    price_eur: float
    sqm: float
    price_per_sqm: float
    neighborhood_median_sqm: float
    neighborhood_std_sqm: float = 2.0
    initial_rank: int                 # Rank #1..#K assigned by MatchRanker BEFORE Iris
    match_score: int                  # 0-100 feature match score
    matched_features: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    description: str
    deposit_months_requested: Optional[float] = 1.0
    upfront_pre_viewing_payment_eur: float = 0.0
    reverse_image_match: str = "NONE"  # e.g., "NONE", "SHORT_TERM_RENTAL_AIRBNB_BOOKING"
    cross_portal_price_conflict: bool = False
    publisher_type: str = "VERIFIED_PRIVATE_OWNER"
    phone_country_code: str = "+30"


class IrisRubricProbabilities(BaseModel):
    price_anomaly: float              # 0.0 - 1.0
    advance_fee_or_remote_lure: float # 0.0 - 1.0
    stolen_media_or_clone: float      # 0.0 - 1.0
    metadata_contradiction: float     # 0.0 - 1.0


class IrisDecisionResult(BaseModel):
    listing_id: str
    initial_rank: int                 # Preserved so UI can display "Would Have Ranked #1"
    final_rank: Optional[int] = None  # Re-indexed #1, #2... for SAFE shortlist (None if POSSIBLY_SCAM)
    verdict: Literal["SAFE", "POSSIBLY_SCAM"]
    scam_risk_pct: int                # 0 - 100
    rubric_probabilities: IrisRubricProbabilities
    triggered_flags: list[str]
    forensic_summary: str
    source_mode: Literal["live_oumi_iris", "cached_oumi_iris", "deterministic_fallback"]
    latency_ms: float


SCAM_QUESTIONS: dict[str, Any] = {
    "verdict": {
        "type": "choice",
        "instructions": "Classify this ranked residential rental listing as SAFE or POSSIBLY_SCAM.",
        "criteria": {
            "SAFE": "Realistic neighborhood market price (€/m² aligns with cohort), consistent photos and metadata, verifiable contact, and standard in-person viewing with zero upfront payment.",
            "POSSIBLY_SCAM": "Shows fraud or bait-listing signals: extreme price undervaluation vs. neighborhood median, advance-fee/escrow or landlord-abroad wire demands, WhatsApp-only foreign isolation, stolen Airbnb/stock imagery, cross-portal clone conflicts, or severe metadata contradictions.",
        },
    },
    "is_possibly_scam": {
        "type": "noul",
        "instructions": "Probability that this ranked rental listing is fraudulent, a bait ad, or an advance-fee scam.",
        "criteria": {
            "true": "Exhibits financial, pricing, media, or metadata fraud indicators.",
            "false": "Behaves like an authentic residential lease offering.",
        },
    },
    "price_anomaly": {
        "type": "noul",
        "instructions": "Is the monthly rent per m² suspiciously below the neighborhood median?",
        "criteria": {
            "true": "price_deviation_pct <= -25% or price_z_score <= -1.5 without physical justification.",
            "false": "Price per m² is aligned with neighborhood market variance.",
        },
    },
    "advance_fee_or_remote_lure": {
        "type": "noul",
        "instructions": "Does the text demand upfront payment/escrow before viewing or claim an absentee overseas landlord?",
        "criteria": {
            "true": "Requests wire/Revolut/Airbnb escrow before viewing, claims landlord is abroad shipping keys, or forces WhatsApp-only isolation.",
            "false": "Allows standard in-person viewing and Taxisnet lease signing.",
        },
    },
    "stolen_media_or_clone": {
        "type": "noul",
        "instructions": "Do reverse-image or cross-portal signals indicate stolen short-term rental photos or a cloned listing?",
        "criteria": {
            "true": "Matches Airbnb/Booking/stock imagery or appears on another portal at a conflicting higher price.",
            "false": "Original photos and consistent cross-portal provenance.",
        },
    },
    "metadata_contradiction": {
        "type": "noul",
        "instructions": "Are there physical contradictions or unverified burner profile disclosures?",
        "criteria": {
            "true": "Contradictory floor/specs or unverified ephemeral account stripped of mandatory disclosures.",
            "false": "Internally consistent specs.",
        },
    },
}


class OumiIrisScamClient:
    """Parallel async client for Oumi Iris (/v1/systemone) running post-ranking."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OUMI_API_KEY", "").strip()
        self.project_id = os.getenv("OUMI_PROJECT_ID", "").strip()
        self.timeout_s = float(os.getenv("OUMI_TIMEOUT_MS", "2500")) / 1000.0
        self.fallback_mode = os.getenv("OUMI_FALLBACK_MODE", "auto")
        self.audit_log_path = Path(os.getenv("OUMI_AUDIT_LOG_PATH", "logs/oumi_iris_audit.jsonl"))
        self.cache_path = Path("backend/data/oumi_iris_cache.json")
        self._sem = asyncio.Semaphore(10)

    def _build_state(self, item: RankedPropertyCandidate) -> dict[str, Any]:
        deviation_pct = round(
            ((item.price_per_sqm - item.neighborhood_median_sqm) / max(item.neighborhood_median_sqm, 0.01)) * 100,
            2,
        )
        z_score = round(
            (item.price_per_sqm - item.neighborhood_median_sqm) / max(item.neighborhood_std_sqm, 0.01),
            2,
        )
        return {
            "listing_id": item.listing_id,
            "initial_rank": item.initial_rank,
            "feature_match_score": item.match_score,
            "property": {
                "title": item.title,
                "neighborhood": item.neighborhood,
                "source": item.provider,
                "price_eur": item.price_eur,
                "sqm": item.sqm,
                "description": item.description,
            },
            "quantitative_signals": {
                "price_per_sqm": round(item.price_per_sqm, 2),
                "neighborhood_median_sqm": round(item.neighborhood_median_sqm, 2),
                "price_deviation_pct": deviation_pct,
                "price_z_score": z_score,
                "deposit_months_requested": item.deposit_months_requested,
                "upfront_pre_viewing_payment_eur": item.upfront_pre_viewing_payment_eur,
            },
            "forensic_signals": {
                "reverse_image_match": item.reverse_image_match,
                "cross_portal_price_conflict": item.cross_portal_price_conflict,
                "publisher_type": item.publisher_type,
                "phone_country_code": item.phone_country_code,
                "missing_mandatory_greek_fields": item.missing_features,
            },
        }

    def _cache_key(self, state: dict[str, Any]) -> str:
        raw = json.dumps({"state": state, "questions": SCAM_QUESTIONS}, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_cache(self) -> dict[str, Any]:
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        return {}

    def _save_cache(self, key: str, raw_response: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = self._load_cache()
        cache[key] = raw_response
        self.cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    def _append_audit_log(self, listing_id: str, latency_ms: float, mode: str, raw: dict[str, Any]) -> None:
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": time.time(),
            "listing_id": listing_id,
            "mode": mode,
            "latency_ms": round(latency_ms, 1),
            "answers": raw.get("answers", {}),
            "usage": raw.get("usage", {}),
        }
        with self.audit_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _to_decision_result(
        self,
        item: RankedPropertyCandidate,
        raw: dict[str, Any],
        source_mode: Literal["live_oumi_iris", "cached_oumi_iris", "deterministic_fallback"],
        latency_ms: float,
    ) -> IrisDecisionResult:
        ans = raw["answers"]
        scam_prob = float(ans["is_possibly_scam"]["noul"])
        verdict: Literal["SAFE", "POSSIBLY_SCAM"] = (
            "POSSIBLY_SCAM"
            if ans["verdict"]["choice"] == "POSSIBLY_SCAM" or scam_prob >= 0.50
            else "SAFE"
        )
        probs = IrisRubricProbabilities(
            price_anomaly=round(float(ans["price_anomaly"]["noul"]), 3),
            advance_fee_or_remote_lure=round(float(ans["advance_fee_or_remote_lure"]["noul"]), 3),
            stolen_media_or_clone=round(float(ans["stolen_media_or_clone"]["noul"]), 3),
            metadata_contradiction=round(float(ans["metadata_contradiction"]["noul"]), 3),
        )
        flags: list[str] = []
        if probs.price_anomaly >= 0.50:
            pct = round(((item.price_per_sqm - item.neighborhood_median_sqm) / item.neighborhood_median_sqm) * 100)
            flags.append(f"PRICE_ANOMALY ({pct:+d}% vs. {item.neighborhood} median)")
        if probs.advance_fee_or_remote_lure >= 0.50:
            flags.append("ADVANCE_FEE_OR_REMOTE_LURE")
        if probs.stolen_media_or_clone >= 0.50:
            flags.append("STOLEN_MEDIA_OR_CLONE")
        if probs.metadata_contradiction >= 0.50:
            flags.append("METADATA_CONTRADICTION")

        risk_pct = round(scam_prob * 100)
        if verdict == "POSSIBLY_SCAM":
            summary = (
                f"Intercepted former Rank #{item.initial_rank} ({item.match_score}% feature match): "
                f"{risk_pct}% scam probability ({', '.join(flags) or 'Multiple rubric triggers'})."
            )
        else:
            summary = f"Verified SAFE by Oumi Iris ({risk_pct}% risk). Cleared for human selection."

        return IrisDecisionResult(
            listing_id=item.listing_id,
            initial_rank=item.initial_rank,
            verdict=verdict,
            scam_risk_pct=risk_pct,
            rubric_probabilities=probs,
            triggered_flags=flags,
            forensic_summary=summary,
            source_mode=source_mode,
            latency_ms=round(latency_ms, 1),
        )

    def _deterministic_fallback(self, item: RankedPropertyCandidate) -> dict[str, Any]:
        """Offline heuristic mirror for CI tests or unreachable network."""
        pct_diff = (item.price_per_sqm - item.neighborhood_median_sqm) / max(item.neighborhood_median_sqm, 0.01)
        desc = item.description.lower()
        p_price = 0.96 if pct_diff <= -0.35 else (0.62 if pct_diff <= -0.22 else 0.08)
        p_fee = 0.95 if (
            item.upfront_pre_viewing_payment_eur > 0
            or any(k in desc for k in ("escrow", "abroad", "whatsapp only", "courier", "western union", "revolut"))
        ) else 0.05
        p_media = 0.92 if (item.reverse_image_match != "NONE" or item.cross_portal_price_conflict) else 0.04
        p_meta = 0.84 if (item.publisher_type in {"ANONYMOUS_SOCIAL_PROFILE", "UNVERIFIED_NEW_ACCOUNT"} and len(item.missing_features) >= 3) else 0.06
        overall = min(0.99, max(p_price, p_fee, p_media, (p_price + p_fee + p_media + p_meta) / 2.2))
        choice = "POSSIBLY_SCAM" if overall >= 0.50 else "SAFE"
        return {
            "answers": {
                "verdict": {"type": "choice", "choice": choice, "confidence": max(overall, 1 - overall)},
                "is_possibly_scam": {"type": "noul", "noul": overall},
                "price_anomaly": {"type": "noul", "noul": p_price},
                "advance_fee_or_remote_lure": {"type": "noul", "noul": p_fee},
                "stolen_media_or_clone": {"type": "noul", "noul": p_media},
                "metadata_contradiction": {"type": "noul", "noul": p_meta},
            },
            "usage": {"inputTokens": 0, "outputTokens": 0},
        }

    async def _evaluate_single(
        self, client: httpx.AsyncClient, item: RankedPropertyCandidate
    ) -> IrisDecisionResult:
        state = self._build_state(item)
        key = self._cache_key(state)
        t0 = time.perf_counter()

        # Optional cache-first mode for guaranteed sub-10ms stage reproducibility
        if self.fallback_mode == "cache_first":
            cached = self._load_cache().get(key)
            if cached:
                ms = (time.perf_counter() - t0) * 1000
                return self._to_decision_result(item, cached, "cached_oumi_iris", ms)

        # Tier 1: Live Oumi Iris /v1/systemone call
        if self.api_key and self.project_id:
            payload = {
                "model": f"projects/{self.project_id}/models/iris-latest",
                "state": state,
                "questions": SCAM_QUESTIONS,
            }
            async with self._sem:
                try:
                    resp = await client.post(
                        OUMI_SYSTEMONE_URL,
                        headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
                        json=payload,
                    )
                    resp.raise_for_status()
                    raw = resp.json()
                    ms = (time.perf_counter() - t0) * 1000
                    self._save_cache(key, raw)
                    self._append_audit_log(item.listing_id, ms, "live_oumi_iris", raw)
                    return self._to_decision_result(item, raw, "live_oumi_iris", ms)
                except Exception:
                    if self.fallback_mode == "live_only":
                        raise

        # Tier 2: Pre-warmed genuine Oumi response cache
        cached = self._load_cache().get(key)
        if cached:
            ms = (time.perf_counter() - t0) * 1000
            return self._to_decision_result(item, cached, "cached_oumi_iris", ms)

        # Tier 3: Deterministic rubric fallback
        raw_fb = self._deterministic_fallback(item)
        ms = (time.perf_counter() - t0) * 1000
        self._append_audit_log(item.listing_id, ms, "deterministic_fallback", raw_fb)
        return self._to_decision_result(item, raw_fb, "deterministic_fallback", ms)

    async def evaluate_top_k(
        self, ranked_candidates: list[RankedPropertyCandidate], top_k: int = 10
    ) -> list[IrisDecisionResult]:
        """Concurrently scores Top-K ranked listings with Oumi Iris and re-indexes SAFE ranks."""
        shortlist = sorted(ranked_candidates, key=lambda c: c.initial_rank)[:top_k]
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            results = list(await asyncio.gather(*(self._evaluate_single(client, c) for c in shortlist)))

        safe_rank = 1
        for res in sorted(results, key=lambda r: r.initial_rank):
            if res.verdict == "SAFE":
                res.final_rank = safe_rank
                safe_rank += 1
        return results
```

---

## 5. Frontend "Wow Factor" UI Specification

Because **Oumi `Iris`** sits visibly between the **Feature Ranker** and the **Human Approval Gate**, the frontend (`frontend/src/app/page.tsx` and interactive demo views) must make the post-ranker interception unmistakable at first glance during the 3-minute pitch:

### 5.1 Live Pipeline Telemetry Banner
Display a compact horizontal funnel bar directly above the listings:
- `18 Raw Listings Merged` $\rightarrow$ `Top 8 Ranked by Features` $\rightarrow$ `Evaluated by Oumi Iris in 0.64s` $\rightarrow$ **`2 POSSIBLY SCAM Intercepted` • `6 Verified SAFE`**

### 5.2 "Intercepted High-Rank Bait" Hero Banner / Quarantine Section (`POSSIBLY_SCAM`)
Do **not** bury blocked scams inside a collapsed muted drawer without context. Keep a high-contrast **"Intercepted by Oumi Iris (`POSSIBLY_SCAM`)"** callout card right alongside or above the verified list (expandable for full details):
- **Strikethrough Rank Comparison Badge (The Judge Hook):**
  - Displays: `~~Raw Rank #1 (98% Feature Match)~~` $\rightarrow$ **`🛡️ BLOCKED BY OUMI IRIS: POSSIBLY SCAM (96% Risk)`**
  - Caption: *"Without Oumi Iris, this €450/mo Koukaki listing ranked #1 on your features—and your voice agent would have called a scammer."*
- **4-Bar Forensic Probability Breakdown (Driven Directly by `Iris`'s `noul` Outputs):**
  Each quarantined card renders 4 horizontal probability meters with exact percentages from `/v1/systemone`:
  1. **Price-per-m² Anomaly:** `98%` *(€6.92/m² vs. €16.00/m² Koukaki median, -57%)*
  2. **Advance-Fee / Remote Lure:** `95%` *(Demands €900 Airbnb escrow before viewing; +44 WhatsApp only)*
  3. **Stolen Photo / Clone Signal:** `92%` *(Reverse-image match to active €145/night Airbnb listing)*
  4. **Metadata Contradiction:** `84%` *(Unverified 2-day profile missing ΠΕΑ, heating & κοινόχρηστα)*

### 5.3 Verified `SAFE` Shortlist Cards
For properties that clear `Iris` with `verdict == "SAFE"`:
- **Dual Rank & Trust Badges:**
  - `Verified Rank #1` *(Promoted after Rank #1 bait scam was blocked)*
  - **`✓ OUMI IRIS: SAFE (4% Scam Risk)`** (clickable pill or hover popover showing all 4 low-risk forensic bars in green: `Price Anomaly 8%`, `Advance-Fee 5%`, `Media Match 4%`, `Metadata 6%`).
- **Missing-Info Handoff Pill:**
  - Lists the exact questions extracted by the Feature Ranker (e.g., *"Ask landlord: Monthly κοινόχρηστα? Pets allowed?"*) ready for the **1-Agent-Per-Landlord** outreach swarm once the user checks the box and clicks Launch.
