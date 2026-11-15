# Oumi `Iris` Decision Model — Post-Ranker Integration Guide

> **Purpose:** Concise reference for how **Oumi's `Iris` Decision Model** (`POST https://inference.oumi.ai/v1/systemone`) is integrated into our pipeline via [`backend/decision.py`](./backend/decision.py).  
> **Scope:** `Iris` runs **after the Feature Ranker and deep scrape** on the shortlisted properties and classifies each as **`SAFE`** or **`POSSIBLY_SCAM`**. Per-criterion `rubric_probabilities` are computed internally in `backend/decision.py`, while only the single strongest red flag at or above `0.50` (`SCAM_THRESHOLD`) is surfaced as plain-English `scam_reason` on `POSSIBLY_SCAM` listings. It is completely location-agnostic and does **not** decide outreach channel strategies.

---

## 1. Pipeline Position (Post-Ranker Decision Gate)

```text
[1. Provider Search & Scrape (`backend/agent.py`)]
    Fetches all candidate listings on the search page (`all_houses`)
          │
          ▼
[2. Feature Ranker & Deep Scrape (`backend/agent.py`)]
    Scores candidates against user requirements and deep-scrapes top listings (`final_properties`)
          │
          ▼
[3. Oumi Iris Decision Model (`backend/decision.py`)]
    • Computes dynamic cohort median €/m² from `all_houses` (location-agnostic)
    • Evaluates shortlisted properties in parallel via `POST https://inference.oumi.ai/v1/systemone`
    • Computes `SAFE` vs. `POSSIBLY_SCAM`, `scam_risk_pct`, and internal `rubric_probabilities`
    • Surfaces the single strongest red flag >= 0.50 as plain-English `scam_reason` (only when `POSSIBLY_SCAM`)
          │
          ├──► `safe_properties` (Kept at top of `results`; re-indexed `verified_rank` #1, #2... in `DecisionBatchResponse`)
          └──► `possibly_scam_properties` (Sunk to the bottom of `results` with a card/modal warning and outreach dry-run lock)
```

---

## 2. API & Environment Setup

| Parameter | Value |
| :--- | :--- |
| **Endpoint** | `POST https://inference.oumi.ai/v1/systemone` |
| **Headers** | `X-API-Key: $OUMI_API_KEY`, `Content-Type: application/json` |
| **Model Identifier** | `projects/{OUMI_PROJECT_ID}/models/iris-latest` |
| **Health Check** | `GET /api/health` reports `"oumi_configured": true \| false` via `oumi_configured()` |
| **Standalone Endpoint** | `POST /api/decision/evaluate` runs `evaluate_ranked_properties()` without a full search |

### `.env` Variables & Helpers
```dotenv
OUMI_API_KEY=your_oumi_api_key
OUMI_PROJECT_ID=your_oumi_project_id
```

- `normalize_project_id(raw)` accepts `abc`, `projects/abc`, or `projects/abc/models/iris-latest` and normalizes to `abc`.
- `oumi_configured()` checks that both `OUMI_API_KEY` and normalized `OUMI_PROJECT_ID` are non-empty.
- `probe_oumi()` runs a tiny single-question (`is_rental`) check against `/v1/systemone` to verify the key, project ID, and endpoint:
  ```powershell
  uv run python -m backend.decision
  # Also invoked automatically by:
  uv run python -m backend.check_env
  ```

---

## 3. Request & Response Contract (`/v1/systemone`)

### Request Payload (`state` + `questions`)
For each ranked property, [`backend/decision.py`](./backend/decision.py) sends the property object, its `initial_rank`, and dynamic cohort $€/\text{m}^2$ comparison:

```json
{
  "model": "projects/{project_id}/models/iris-latest",
  "state": {
    "initial_rank": 1,
    "property": {
      "url": "https://...",
      "price": 400,
      "sqm": 70,
      "floor": "3rd",
      "features": ["renovated", "furnished", "pet friendly"],
      "agent_phone": null,
      "agentic_score": 10,
      "score_reason": "Matches all user criteria at a very low price."
    },
    "price_signals": {
      "eur_per_sqm": 5.71,
      "cohort_median_eur_per_sqm": 12.1,
      "deviation_from_cohort_pct": -52.8
    }
  },
  "questions": {
    "verdict": {
      "type": "choice",
      "instructions": "Classify this ranked residential rental listing as SAFE or POSSIBLY_SCAM.",
      "criteria": {
        "SAFE": "Plausible residential rental with realistic market pricing, consistent specs, verifiable contact info, and normal in-person viewing terms.",
        "POSSIBLY_SCAM": "Exhibits rental scam or bait indicators: unrealistic underpricing vs. cohort, upfront payment/escrow before viewing, remote landlord claims, stolen/cloned media, or contradictory/missing specs."
      }
    },
    "is_possibly_scam": {
      "type": "noul",
      "instructions": "What is the probability that this ranked rental listing is fraudulent or a bait scam?",
      "criteria": {
        "true": "The listing shows pricing, financial, media, or contact red flags.",
        "false": "The listing appears to be a legitimate rental offering."
      }
    },
    "price_anomaly": {
      "type": "noul",
      "instructions": "Is the rental price per square meter unrealistically low compared to the search cohort and property features?",
      "criteria": {
        "true": "Price per m² is abnormally low relative to the cohort median or advertised condition.",
        "false": "Price per m² is within a realistic range for the cohort."
      }
    },
    "advance_fee_lure": {
      "type": "noul",
      "instructions": "Does the listing request upfront payment/escrow before viewing or claim an unavailable/remote landlord?",
      "criteria": {
        "true": "Mentions pre-viewing deposits, external platform escrow, courier key delivery, or absentee owner.",
        "false": "Allows standard in-person viewing prior to payment."
      }
    },
    "stolen_or_cloned_media": {
      "type": "noul",
      "instructions": "Are there signs of stolen short-term rental photos or conflicting duplicate listings?",
      "criteria": {
        "true": "Signals indicate reused short-term rental/stock imagery or conflicting cross-portal data.",
        "false": "Media and listing provenance appear consistent."
      }
    },
    "metadata_inconsistency": {
      "type": "noul",
      "instructions": "Are there contradictions in property attributes or missing/suspicious landlord contact details?",
      "criteria": {
        "true": "Contradictory property specs or unverified/missing landlord contact on a high-match listing.",
        "false": "Property metadata and contact details are consistent."
      }
    }
  }
}
```

---

## 4. How to Call `backend/decision.py` & API

```python
from backend.decision import evaluate_ranked_properties_sync, oumi_configured

if oumi_configured():
    # Pass `final_properties` (ranked list) and optionally `all_houses` (for cohort median €/m²)
    decision_batch = evaluate_ranked_properties_sync(
        ranked_properties=final_properties,
        all_properties=all_houses,
    )

    # 1. Verified SAFE listings (re-indexed verified_rank = 1, 2...)
    for item in decision_batch.safe_properties:
        print(item.verified_rank, item.url, item.scam_risk_pct)

    # 2. Flagged POSSIBLY_SCAM listings (plain-English scam_reason; rubric_probabilities stay internal)
    for scam in decision_batch.possibly_scam_properties:
        print(scam.initial_rank, scam.url, scam.scam_risk_pct, scam.scam_reason, scam.rubric_probabilities)
```

- **Standalone FastAPI endpoint (`POST /api/decision/evaluate`):** Accepts `{ "properties": [...], "cohort": [...] }` (where `cohort` is optional) and returns `[{ "url", "rank", "scam_verdict", "scam_risk_pct", "scam_reason" }]`. Returns `503` if `oumi_configured()` is `False` or `502` on upstream Iris errors.

---

## 5. Implemented Frontend & Outreach Behavior

`backend/agent.py` merges `scam_verdict`, `scam_risk_pct`, and `scam_reason` into each returned listing and sinks any `POSSIBLY_SCAM` listings to the bottom of `results`:

1. **Card & Details Badges:**
   Cards display `Oumi Iris · Safe · {scam_risk_pct}% risk` or `Oumi Iris · Possible scam · {scam_risk_pct}% risk` (when `scam_verdict` is present), and the collapsed `AgentFeed` summary reports either `Oumi Iris: all safe` or `Oumi Iris flagged N possible scam(s)`.
2. **Plain-English Warning (`scam_reason`), Not 4 UI Bars:**
   `rubric_probabilities` (`price_anomaly`, `advance_fee_lure`, `stolen_or_cloned_media`, `metadata_inconsistency`) remain internal to `backend/decision.py`. Only the single strongest red flag `>= 0.50` is returned as plain-English `scam_reason` (only on `POSSIBLY_SCAM` listings) and shown in a warning notice on the property card, details modal (alongside the `Scam check (Oumi Iris)` key fact), and outreach question briefing.
3. **Outreach Dry-Run Lock:**
   Both `backend/outreach/service.py` and `backend/outreach/live.py` automatically force `dry_run=True` for any listing with `scam_verdict == "POSSIBLY_SCAM"` (even if `OUTREACH_DRY_RUN=false`). The UI reflects this with **Draft e-mail only** in the question briefing and **Drafted · Not Sent** once completed.
