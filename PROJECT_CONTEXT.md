# Autonomous Housing Agent — Hackathon Product Specification

> **Purpose of this Document:** Master product & architecture context prompt for the team and our AI coding agents.

---

## 1. One-Line Pitch

An autonomous AI housing platform that owns the end-to-end process of discovering **real, live listings** across multiple datasources, filtering out rental scams, ranking homes by user features, and deploying one dedicated outreach agent per landlord (via Phone Call, SMS, and Email) to verify details and book viewings.

## 2. The Problem

Finding a place to live is fragmented across many sites (Spitogatos, XE.gr, Plot.gr, Facebook Marketplace, etc.) and requires repetitive searching, cross-checking duplicate ads, dodging sophisticated rental scams, comparing incomplete listings, and playing endless phone/SMS tag with landlords. People repeat this exhausting workflow every time they search for a new home.

## 3. Vision

Shift the user from manually browsing dozens of tabs and chasing landlords to **delegating the entire discovery, verification, and outreach workflow to an AI team**—intervening only once to pick their favorite verified homes.

## MVP Scope & Principles

This is an MVP. We are not targeting production-level code yet; the priority is a working end-to-end demonstration backed by **real, live rental data** scraped on demand (with offline fallback only if external APIs are unavailable). Hardcoded rules and other pragmatic shortcuts are acceptable when they help us deliver the core experience.

## 4. Success Metrics

- **Time saved:** Hours of searching, scam-checking, and calling compressed into a 2-minute workflow.
- **Scam protection:** % of fraudulent or bait listings intercepted before the user ever sees or contacts them.
- **Higher quality shortlist:** Fewer listings reviewed manually, ranked accurately against hard constraints and soft preferences.
- **Conversion to booked viewings:** Successful landlord contact and confirmed viewing slots with minimal user effort.

## 5. User Personas

- **Budget-conscious renter** searching on a strict monthly budget (high vulnerability to underpriced rental scams).
- **Busy professional** with tight schedules who cannot spend all day calling landlords.
- **Household / family** with strict feature requirements (m², bedrooms, quiet neighborhood, pet policy).
- **Mid-term / flexible renter** looking for furnished or adaptable stays (architecture remains extensible across stay lengths).

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

## 8. High-Level MVP Workflow

```text
+-------------------------------------------------+
| Text input: location + features                 |
+-------------------------------------------------+
                         |
                         v
+-------------------------------------------------+
| Agent searches available datasources             |
+-------------------------------------------------+
                         |
                         v  (Data Return)
+-------------------------------------------------+
| Ranker based on requested features plus         |
| hard-bound characteristics                      |
+-------------------------------------------------+
                         |
                         v
+-------------------------------------------------+
| Run Oumi Decision Model to flag potential scams |
| (Scam / No Scam recommendation)                 |
+-------------------------------------------------+
                         |
                         v  (List with scam flags)
+-------------------------------------------------+
| User picks one or more desired options          | <----+
+-------------------------------------------------+       | (adds contact details)
                         |                                |
                         v                                |
+-------------------------------------------------+       |
| Contact landlord (SMS + email)                  |       |
+-------------------------------------------------+       |
                         |                                |
                         v                                |
+-------------------------------------------------+       |
| User sees agent response                        |       |
+-------------------------------------------------+       |
                         |                                |
                         v                                |
+-------------------------------------------------+       |
| Books appointment                               |       |
+-------------------------------------------------+
```

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

## 13. Decision Model & Initial Integration Choices

- **Decision Model (Committed):** **Oumi (`Iris` Decision Model)** — powers the **ScamGuard Decision Gate** (`https://docs.oumi.ai/guides/decision-models`). Its job is to return if a real listing is a potential scam or not.
- **Initial third-party/API choices:**
  - **Web scraper:** Firecrawl.
  - **Agent orchestration:** Pydantic AI.
  - **LLM / agent brain:** Gemini (provider SDK).
  - **Communication:** Twilio for SMS and Resend for email.
- **Integration categories:**
  - **Listing datasources & ingestion:** Firecrawl-based connectors for real estate portals (e.g., Spitogatos, XE.gr, Plot.gr, and social feeds).
  - **Agent brain:** Gemini for intent parsing, ranking support, missing-info extraction, and outreach dialogue, orchestrated with Pydantic AI.
  - **Outreach channels:** Twilio SMS and Resend email, with webhook support for inbound landlord replies where needed.
  - **Geospatial / Maps (Optional):** Geocoding, polygon boundary filtering, and commute-time calculation.

## 14. Competitive Positioning

Real estate portals give you 500 unverified tabs; chatbots just summarize text. **Our platform owns the entire funnel from multi-site discovery and scam defense to picking up the phone, talking to every landlord in parallel, and handing you confirmed viewing appointments.**

## 15. Stretch Goals

- Interactive Google Maps polygon drawing to constrain search coordinates.
- Commute & neighborhood walkability scoring.
- Rent negotiation / price fairness estimator.
- Post-viewing comparison & move-in checklist.
- Multiagents instead of a single agent
- Showing agent while its working (end-to-end) to give the user the agentic experience
- Expose api calls so it is a thing that agents also want and can utilize

## 16. Mapping to Judging Criteria

- **Usefulness:** Solves a high-friction, real-world problem end-to-end using real, live market data (multi-source search + scam protection + landlord outreach).
- **Craft:** Clean separation between pluggable data connectors, a dedicated Scam Decision Model, a Feature Ranker, a Human Approval Gate, and parallel state-machine Outreach Agents with multi-channel fallback.
- **Aura:** Watching multiple autonomous agents simultaneously call and message landlords on a live command center dashboard feels like having a team of personal housing assistants.

---

## 17. 3-Minute Hackathon Pitch & Demo Script

See [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md) for the standalone 3-minute speaking script covering the problem hook, multi-provider ingestion, the **Oumi `Iris` Scam Decision Model**, feature ranking with missing-info detection, and the parallel **1-Agent-Per-Landlord** outreach dashboard.
