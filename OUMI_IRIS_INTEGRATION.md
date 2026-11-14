# Oumi `Iris` Decision Model — Post-Ranker Integration Guide

> **Purpose:** Concise reference for how **Oumi's `Iris` Decision Model** (`POST https://inference.oumi.ai/v1/systemone`) is integrated into our pipeline via [`backend/decision.py`](./backend/decision.py).  
> **Scope:** `Iris` runs **after the Feature Ranker** on the ranked properties and classifies each as **`SAFE`** or **`POSSIBLY_SCAM`** with 4 parallel forensic probabilities for the frontend UI. It is completely location-agnostic and does **not** decide outreach channel strategies.

---

## 1. Pipeline Position (Post-Ranker Decision Gate)

```text
[1. Provider Search & Scrape]
    Fetches all candidate listings on the search page (`all_houses`)
          │
          ▼
[2. Feature Ranker (`backend/agent.py`)]
    Scores candidates against user requirements and returns top ranked properties (`final_properties`)
          │
          ▼
[3. Oumi Iris Decision Model (`backend/decision.py`)]
    • Computes dynamic cohort median €/m² from the scraped results (location-agnostic)
    • Evaluates ranked properties in parallel via `POST https://inference.oumi.ai/v1/systemone`
    • Outputs `SAFE` vs. `POSSIBLY_SCAM` + 4 rubric probabilities (`outputTokens: 0`)
          │
          ├──► `safe_properties` (Re-indexed `verified_rank` #1, #2... ready for user approval & outreach)
          └──► `possibly_scam_properties` (Shown in Frontend "Wow Factor" banner with forensic bars)
```

---

## 2. API & Environment Setup

| Parameter | Value |
| :--- | :--- |
| **Endpoint** | `POST https://inference.oumi.ai/v1/systemone` |
| **Headers** | `X-API-Key: $OUMI_API_KEY`, `Content-Type: application/json` |
| **Model Identifier** | `projects/{OUMI_PROJECT_ID}/models/iris-latest` |

### `.env` Variables
```dotenv
OUMI_API_KEY=your_oumi_api_key
OUMI_PROJECT_ID=your_oumi_project_id
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

## 4. How to Call `backend/decision.py`

```python
from backend.decision import evaluate_ranked_properties_sync

# Pass `final_properties` (ranked list) and optionally `all_houses` (for cohort median €/m²)
decision_batch = evaluate_ranked_properties_sync(
    ranked_properties=final_properties,
    all_properties=all_houses,
)

# 1. Verified SAFE listings (re-indexed verified_rank = 1, 2...)
for item in decision_batch.safe_properties:
    print(item.verified_rank, item.url, item.scam_risk_pct)

# 2. Flagged POSSIBLY_SCAM listings (with initial_rank and 4 rubric probabilities)
for scam in decision_batch.possibly_scam_properties:
    print(scam.initial_rank, scam.url, scam.scam_risk_pct, scam.rubric_probabilities)
```

---

## 5. Frontend "Wow Factor" Display

In the frontend, use `DecisionBatchResponse` to highlight Oumi `Iris` in action:
1. **Intercepted Top Match Callout (`intercepted_top_match == True`):**
   Show when `initial_rank == 1` was intercepted as `POSSIBLY_SCAM` (e.g., `~~Raw Rank #1~~ → 🛡️ OUMI IRIS: POSSIBLY SCAM (95% Risk)`).
2. **4 Forensic Probability Bars (`rubric_probabilities`):**
   Render horizontal bars for `price_anomaly`, `advance_fee_lure`, `stolen_or_cloned_media`, and `metadata_inconsistency`.
3. **Verified `SAFE` Badge:**
   Display `✓ OUMI IRIS: SAFE` and `scam_risk_pct` on each card in `safe_properties`.
