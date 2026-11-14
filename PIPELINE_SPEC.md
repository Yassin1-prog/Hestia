# Autonomous Relocation & Housing Agent — Hackathon Product Specification

> **Purpose of this Document:** Master product & architecture context prompt for the team and our AI coding agents.

---

## 1. One-Line Pitch
An autonomous AI housing & relocation platform that owns the end-to-end process of discovering listings across multiple datasources, filtering out rental scams, ranking homes by user features, and deploying one dedicated outreach agent per landlord (via Phone Call, SMS, and Email) to verify details and book viewings.

## 2. The Problem
Finding a place to live is fragmented across many sites (Spitogatos, XE.gr, Plot.gr, Facebook Marketplace, etc.) and requires repetitive searching, cross-checking duplicate ads, dodging sophisticated rental scams, comparing incomplete listings, and playing endless phone/SMS tag with landlords. People repeat this exhausting workflow every time they move or relocate.

## 3. Vision
Shift the user from manually browsing dozens of tabs and chasing landlords to **delegating the entire discovery, verification, and outreach workflow to an AI team**—intervening only once to pick their favorite verified homes.

## 4. Success Metrics
- **Time saved:** Hours of searching, scam-checking, and calling compressed into a 2-minute workflow.
- **Scam protection:** % of fraudulent or bait listings intercepted before the user ever sees or contacts them.
- **Higher quality shortlist:** Fewer listings reviewed manually, ranked accurately against hard constraints and soft preferences.
- **Conversion to booked viewings:** Successful landlord contact and confirmed viewing slots with minimal user effort.

## 5. User Personas
- **Student relocating** for university on a strict budget (high vulnerability to rental scams).
- **Professional moving cities** with tight schedules who cannot spend all day calling landlords.
- **Family relocating** with strict feature requirements (m², bedrooms, quiet neighborhood, pet policy).
- **Digital nomad / mid-term relocator** (architecture remains extensible to short/mid-term stays).

## 6. End-to-End User Journey & Pipeline
```text
User Prompt (+ Optional Map Area)
  → Parallel Multi-Source Search & Deduplication (Spitogatos, XE.gr, etc.)
  → Scam Decision Model (Quarantines suspicious listings with reasons)
  → Feature Ranker & Missing-Info Detector (Ranks safe options + flags unstated details)
  → [HUMAN APPROVAL GATE: User selects desired non-scam homes + enters contact info & viewing windows]
  → Parallel Landlord Outreach Swarm (1 Dedicated Agent per Selected House: Voice Call → SMS + Email Fallback)
  → Live Status Dashboard (Transcripts, verified property answers, and booked viewing slots)
```

## 7. Agent & Pipeline Architecture (Lean 2-Agent Design + Modular Tools)
To avoid brittle, slow chains of too many LLM agents, we separate **deterministic pipeline tools** from **autonomous agents**:

### A. Deterministic Pipeline Modules & Evaluators (Tools)
1. **Generalized Multi-Provider Connectors (`BaseListingProvider`):**
   - Pluggable adapters for **Spitogatos**, **XE.gr**, **Plot.gr**, **Facebook Marketplace**, etc.
   - Normalizes raw listings into a single schema and deduplicates cross-posted properties (via coordinates/m² + image hashing).
2. **Scam Decision Model (`ScamGuard` — Powered by Oumi Iris Decision Model):**
   - Uses **Oumi's `Iris` Decision Model** (`https://docs.oumi.ai/guides/decision-models`) to evaluate every listing before ranking and output a structured decision (`SAFE` | `BLOCKED_SCAM`), risk score (`0–100%`), and explicit criteria reasoning.
   - Decision Rubrics fed to **Oumi Iris**: Price-per-m² anomaly vs. neighborhood median, reverse-image / stolen photo signal, advance-fee NLP red flags (*"landlord abroad"*, *"wire deposit before viewing"*), and metadata contradictions.
   - Quarantines flagged listings into a collapsible **"Blocked Scams (Verified by Oumi Iris)"** UI section.
3. **Feature-Aware Ranker & Gap Analyzer (`MatchRanker`):**
   - Scores all `SAFE` listings (`0–100% Match`) against the user's hard constraints and soft features.
   - **Missing-Info Detector:** Automatically identifies required features *not mentioned* in the listing (e.g., pet policy, monthly common charges / *κοινόχρηστα*, autonomous heating active) so the Outreach Agent knows exactly what to ask the landlord.

### B. Autonomous Agents (Where Autonomy & State Matter)
1. **Discovery Orchestrator Agent (1 Instance per User Session):**
   - Parses the user's natural language prompt (+ optional highlighted map polygon) into structured filters and weighted preferences.
   - Executes the provider search, Scam Decision Model, and Feature Ranker tools, then presents the verified shortlist and blocked scams to the user for approval.
2. **Per-House Landlord Outreach Agents ($N$ Parallel Instances — 1 Agent per Selected House):**
   - Once the user selects $N$ verified houses and provides their contact details + viewing availability, the platform spawns **1 dedicated agent per house/landlord**.
   - **Goal:** Confirm the property is still available, ask the missing-info questions identified by the Ranker, and book a viewing slot.
   - **Multi-Channel Fallback State Machine:**
     - **Step 1 (Phone Call First):** AI Voice Agent calls the landlord directly.
     - **Step 2 (Automatic SMS + Email Fallback):** If the call is busy, unanswered, or hits voicemail, the agent immediately dispatches a personalized SMS and Email with the user's viewing windows and monitors inbound webhook replies asynchronously.

## 8. Product Demo Flow
1. **Input:** User enters a natural-language housing prompt (plus optional highlighted neighborhood area on a map) and selects active datasources.
2. **Ingestion & Scam Defense:** Pipeline fetches listings in parallel, merges duplicates, and quarantines 3 high-risk scam listings into a collapsible **"Blocked Scams"** drawer with forensic explanations.
3. **Ranked Shortlist:** User reviews the ranked, scam-free homes with match scores and auto-detected *"Questions for Agent to Ask Landlord"*.
4. **Approval Gate:** User checks their top 3 houses and enters their contact info + preferred viewing time windows.
5. **Parallel Multi-Agent Outreach:** 3 dedicated agents launch side-by-side (1 per landlord), visibly executing the **Voice Call → SMS + Email Fallback** sequence and updating the dashboard in real time as viewings are booked.

## 9. Aura Moments
- **"Blocked 3 Rental Scams Automatically":** Expandable forensic drawer showing why a too-good-to-be-true Koukaki listing was intercepted (57% below area €/m² average + stolen Airbnb photos).
- **Missing-Feature Intelligence:** Seeing the ranker notice *"Pet policy & common charges not stated in ad"* and automatically adding those questions to the voice agent's script.
- **Parallel 1-Agent-Per-Landlord Command Center:** Watching 3 agents work simultaneously—one conversing on a live phone call, another automatically falling back to SMS + Email after a busy signal and locking in a viewing when the landlord texts back.

## 10. Craft
Shows purposeful engineering rather than a single giant prompt:
- Generalized multi-provider adapter pattern (`ListingProvider`).
- Explicit Scam Decision Model before ranking.
- Clear Human-in-the-Loop approval gate before any external communication occurs.
- Per-house state-machine agents with multi-channel retry/fallback logic (`Call → SMS + Email`).

## 11. Usefulness
Automates the three things house-hunters hate most:
- Filtering out duplicate noise and dangerous rental scams across multiple sites.
- Figuring out which listings actually match their criteria and what details are missing.
- Calling, texting, and emailing dozens of landlords to ask basic questions and schedule viewings.

## 12. Research Checklist
- Apartment-hunting pain points & cross-platform duplication (Spitogatos, XE.gr, Plot.gr, FB).
- Real-world rental scam patterns (advance-fee wire fraud, stolen Airbnb photos, price anomalies).
- Feature ranking + missing-attribute extraction.
- Multi-channel outreach APIs (Voice AI, SMS, Email) and multi-agent status UX patterns.

## 13. Decision Model & Open Integration Layers
- **Decision Model (Committed):** **Oumi (`Iris` Decision Model)** — powers the **ScamGuard Decision Gate** (`https://docs.oumi.ai/guides/decision-models`, team registration: `https://labs.oumi.ai/hackathon-village/genai-summit-athens-2026`). Evaluates price-per-m² anomalies, reverse-image signals, advance-fee NLP red flags, and metadata consistency to output a deterministic `SAFE` vs. `BLOCKED_SCAM` verdict with explicit rubric reasoning.
- **Open Integration Categories (Tooling TBD by Team):**
  - **Listing Datasources & Ingestion:** Connectors/scrapers for real estate portals (e.g., Spitogatos, XE.gr, Plot.gr, social feeds).
  - **Agent Brain (LLM):** Model provider for intent parsing, ranking support, missing-info extraction, and outreach dialogue.
  - **Outreach Channels:** Programmable Voice AI (Phone Calls), SMS, and Email APIs with webhook support for inbound landlord replies.
  - **Geospatial / Maps (Optional):** Geocoding, polygon boundary filtering, and commute-time calculation.

## 14. Competitive Positioning
Real estate portals give you 500 unverified tabs; chatbots just summarize text. **Our platform owns the entire funnel from multi-site discovery and scam defense to picking up the phone, talking to every landlord in parallel, and handing you confirmed viewing appointments.**

## 15. Stretch Goals
- Interactive Google Maps polygon drawing to constrain search coordinates.
- Commute & neighborhood walkability scoring.
- Rent negotiation / price fairness estimator.
- Post-viewing comparison & relocation checklist.

## 16. Mapping to Judging Criteria
- **Usefulness:** Solves a high-friction, real-world problem end-to-end (multi-source search + scam protection + landlord outreach).
- **Craft:** Clean separation between pluggable data connectors, a dedicated Scam Decision Model, a Feature Ranker, a Human Approval Gate, and parallel state-machine Outreach Agents with multi-channel fallback.
- **Aura:** Watching multiple autonomous agents simultaneously call and message landlords on a live command center dashboard feels like having a team of personal relocation assistants.

## 17. Elevator Pitch
"Instead of spending days bouncing between Spitogatos and classifieds, dodging rental scams, and playing phone tag with twenty landlords, you tell our platform what home you want—it searches every source, blocks the scams, ranks your best matches, and deploys a dedicated AI agent for each house you pick to call, text, and email the landlords until your viewings are booked."

---

## 18. 3-Minute Hackathon Pitch & Demo Script
See [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md) for the standalone 3-minute speaking script covering the problem hook, multi-provider ingestion, the **Oumi `Iris` Scam Decision Model**, feature ranking with missing-info detection, and the parallel **1-Agent-Per-Landlord** outreach dashboard.
