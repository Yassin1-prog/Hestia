# 3-Minute Hackathon Pitch & Live Demo Script

> **Goal:** Deliver a clear, high-energy 3-minute pitch that explains the real-world housing problem, highlights **Oumi's `Iris` Decision Model** for scam defense, and showcases the **1-Agent-Per-Landlord** multi-channel outreach swarm without relying on rigid UI script details.

---

## `0:00 – 0:35` | The Hook & Problem (35 sec)
> *"Anyone who has searched for an apartment in a major city knows the workflow is broken. You start with dozens of browser tabs open across portals like Spitogatos, classifieds, and social groups. Half the listings are duplicates, the most attractive low-priced ads are often rental scams, critical details like pet policies or building fees are missing, and once you finally shortlist a few places, you spend hours playing phone, SMS, and email tag with landlords just to ask basic questions and book a viewing.*  
>
> *A standard chatbot can't solve this—it just summarizes text. We built an end-to-end autonomous housing platform that searches across multiple providers, blocks scams using a dedicated decision model, ranks your true matches, and deploys one autonomous outreach agent per landlord to verify details and schedule viewings for you."*

---

## `0:35 – 1:15` | Stage 1: Natural Language Input & Pluggable Datasources (40 sec)
- **[On Screen]:** Show the user entering a natural language housing request (location, budget, size, and lifestyle features—plus an optional highlighted map zone) and launching the multi-provider search.
> *"The user starts by describing what they need in plain language—location, budget, size, and must-have features—with the option to highlight a target zone directly on a map.*  
>
> *From there, our Discovery Orchestrator queries a generalized provider layer in parallel. Because all connectors implement one common schema, we can pull from Spitogatos, local classifieds, and other portals simultaneously, then automatically deduplicate properties that appear on multiple sites."*

---

## `1:15 – 1:55` | Stage 2: Oumi `Iris` Scam Decision Model & Feature Ranker (40 sec)
- **[On Screen]:** Show the quarantined/blocked scam listings drawer alongside the ranked, verified-safe shortlist.
> *"Before we rank anything for the user, every listing passes through our **Scam Decision Gate powered by Oumi's `Iris` Decision Model**. `Iris` evaluates each property against structured fraud signals—like unrealistic price-per-square-meter anomalies, reused or stolen listing photos, metadata contradictions, and advance-fee red flags in the text.*  
>
> *Suspicious listings are automatically quarantined into a transparent 'Blocked Scams' section with exact reasons why they were rejected, so the user never wastes time—or risks money—contacting a scammer.*  
>
> *Only the verified-safe properties move to our Feature Ranker. In addition to scoring how well each home matches the prompt, the Ranker detects **what important details are missing from the listing** and turns them into an automatic question checklist for our outreach agents."*

---

## `1:55 – 2:40` | Stage 3 & 4: Approval Gate & 1-Agent-Per-Landlord Outreach Swarm (45 sec)
- **[On Screen]:** Select the desired verified properties, add user contact details and preferred viewing windows, and open the live Multi-Agent Status Dashboard.
> *"Next comes the human approval gate. Out of the scam-free shortlist, the user simply checks the homes they want, adds their contact details and viewing availability, and launches the outreach swarm.*  
>
> *Instead of one bot working sequentially, we spawn **one dedicated agent per house and landlord**, all running in parallel. Each agent follows a multi-channel fallback strategy: it places an **AI voice call first** to confirm availability, ask the missing property questions, and book a viewing slot. If the landlord doesn't pick up or is busy, the agent automatically falls back to **SMS and Email**, monitors incoming replies, and updates the live dashboard as each conversation progresses from contacting to viewing confirmed."*

---

## `2:40 – 3:00` | Closing Impact (20 sec)
> *"In a single flow, we take the user from fragmented, untrusted listings across multiple platforms to verified homes, answered questions, and confirmed viewing appointments—with one dedicated AI agent handling every landlord on your behalf. Thank you!"*
