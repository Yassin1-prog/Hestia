# 3-Minute Hackathon Pitch & Live Demo Script

> **Goal:** Deliver a clear, high-energy 3-minute pitch that explains the real-world housing problem, highlights **Oumi's `Iris` Decision Model** for scam defense, and showcases the **1-Agent-Per-Landlord** multi-channel outreach swarm without relying on rigid UI script details.

---

## `0:00 – 0:35` | The Hook & Problem (35 sec)
> *"Anyone who has searched for an apartment in a major city knows the workflow is broken. You start with dozens of browser tabs open across portals like Spitogatos, classifieds, and social groups. Half the listings are duplicates, the most attractive low-priced ads are often rental scams, critical details like pet policies or building fees are missing, and once you finally shortlist a few places, you spend hours playing phone, SMS, and email tag with landlords just to ask basic questions and book a viewing.*  
>
> *A standard chatbot can't solve this—it just summarizes text. We built an end-to-end autonomous housing platform that searches across multiple providers, ranks your top matches, runs a dedicated decision model post-ranking to intercept high-scoring scams, and deploys one autonomous outreach agent per landlord to verify details and schedule viewings for you."*

---

## `0:35 – 1:15` | Stage 1: Natural Language Input & Pluggable Datasources (40 sec)
- **[On Screen]:** Show the user entering a natural language housing request (location, budget, size, and lifestyle features—plus an optional highlighted map zone) and launching the multi-provider search.
> *"The user starts by describing what they need in plain language—location, budget, size, and must-have features—with the option to highlight a target zone directly on a map.*  
>
> *From there, our Discovery Orchestrator queries live real-estate datasources in parallel to pull real, up-to-date market listings. Because all connectors implement one common schema, we can pull from portals simultaneously, then automatically deduplicate properties that appear on multiple sites."*

---

## `1:15 – 1:55` | Stage 2: Feature Ranker & Post-Ranker Oumi `Iris` Scam Decision Model (40 sec)
- **[On Screen]:** Show the Feature Ranker scores alongside the **Oumi `Iris`** scam-check badges (`Safe` vs. `Possible scam` with risk % and a plain-English warning), sinking a flagged listing below the verified `SAFE` shortlist and locking outreach to draft-only.
> *"Next, our Feature Ranker scores all real, deduplicated listings against the user's constraints, detects what details are missing—like pet policies or building charges—and narrows the pool to the Top-K finalists.*  
>
> *But here is the trap with real estate portals: **scammers design bait listings to rank #1** by stuffing luxury keywords at half the market price. So before the user ever sees or contacts a landlord, our Top-K ranked results pass in parallel through **Oumi's `Iris` Decision Model**.*  
>
> *`Iris` scores every candidate across price-per-square-meter anomalies, stolen photos, metadata contradictions, and advance-fee red flags, outputting a crisp **`SAFE`** or **`POSSIBLY_SCAM`** verdict with a risk score and plain-English reason. Look at the screen: the apartment that ranked #1 on raw features was flagged at high scam risk, pushed below the verified `SAFE` homes, and locked to draft-only outreach—promoting only verified `SAFE` homes for contact."*

---

## `1:55 – 2:40` | Stage 3 & 4: Approval Gate & 1-Agent-Per-Landlord Outreach Swarm (45 sec)
- **[On Screen]:** Select the desired verified properties, add user contact details and preferred viewing windows, and open the live Multi-Agent Status Dashboard.
> *"Next comes the human approval gate. Out of the scam-free shortlist, the user simply checks the homes they want, adds their contact details and viewing availability, and launches the outreach swarm.*  
>
> *Instead of one bot working sequentially, we spawn **one dedicated agent per house and landlord**, all running in parallel. Each agent follows a multi-channel fallback strategy: it places an **AI voice call first** to confirm availability, ask the missing property questions, and book a viewing slot. If the landlord doesn't pick up or is busy, the agent automatically falls back to **SMS and Email**, monitors incoming replies, and updates the live dashboard as each conversation progresses from contacting to viewing confirmed."*

---

## `2:40 – 3:00` | Closing Impact (20 sec)
> *"In a single flow, we take the user from fragmented, untrusted listings across multiple platforms to verified homes, answered questions, and confirmed viewing appointments—with one dedicated AI agent handling every landlord on your behalf. Thank you!"*
