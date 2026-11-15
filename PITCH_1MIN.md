# 1-Minute Hackathon Submission Video Script — Hestia

> **Format:** 60-second screen recording + voiceover for the initial screening round (leading into the 3-minute pitch + 2-minute Q&A).  
> **Covers:** Who it's for · Problem · Solution · Live demo cues.

---

## Pre-Recording Setup (10 Seconds Before Hitting Record)

1. Confirm both servers are running (`uvicorn` on `:8000` and `next dev` on `:3000`).
2. Open **Settings** in the top-right (`http://localhost:3000`) and save your **Name** and **Email** (plus your Google Calendar secret iCal link if you want real calendar slots, or leave it blank for the sample work week).
3. Either run one search ahead of time or speed up / trim the ~25s Firecrawl scraping wait in your video edit so the recording stays right at **1:00**.
4. Have your **public GitHub repository URL** ready for the submission form (`.env` is already gitignored in `.gitignore`).

---

## `0:00 – 0:12` | Who It's For & The Problem (~32 words)

- **[On Screen]:** Start on Hestia's home screen (*"Describe the home. The agent does the rest."*). Type or click a chip such as *"Bright two-bedroom in Pangrati with a home office"* and submit.
- **[Say]:**
  > *"Apartment hunting is broken for renters. You juggle dozens of listing tabs, try to dodge underpriced rental scams, and still spend hours emailing and calling landlords just to ask missing questions and book a viewing."*

---

## `0:12 – 0:30` | The Solution: Live Multi-Agent Pipeline + Oumi `Iris` (~45 words)

- **[On Screen]:** Show the live streaming steps (`Understand` → `Scan` → `Rank` → `Inspect` with the parallel sub-agent graph), then **Oumi Iris** evaluating the shortlist and revealing the `Live data` cards with photos, match scores, and `Oumi Iris · Safe` badges.
- **[Say]:**
  > *"We built **Hestia**—an autonomous housing agent running on real, live listing data. From one prompt, Gemini sets the search filters, Firecrawl scans live market pages, and parallel agents deep-scrape the top three real listings. Then **Oumi's Iris decision model** screens each finalist against real neighborhood pricing to catch scam signals before you ever reach out."*

---

## `0:30 – 0:55` | Human-in-the-Loop Outreach, Calendar & Voice Call Demo (~90 words)

- **[On Screen]:** Open **Details** briefly to show *"What the listing leaves open"*, click **Ask Agent to Contact**, confirm or add a question, and trigger the outreach agent (showing calendar slot matching, the email draft, and the live web LLM voice-call mockup).
- **[Say]:**
  > *"When you pick a verified home, Hestia flags what the listing left out—like pet rules or building fees—lets you add your own questions, checks your Google Calendar for free evening viewing slots, verifies the landlord's real email, and drafts or sends a tailored viewing request. For the purpose of this demo we also have a call option, with real-time inference of an LLM, that works as a mockup of how the agent will talk to the landlord. Following our initial demonstration, we would buy Twilio credits and have the phone call happen normally, not via web."*

---

## `0:55 – 1:00` | Closing (~13 words)

- **[On Screen]:** End on the completed outreach summary showing the proposed calendar viewing slots and `Live data` cards.
- **[Say]:**
  > *"From one prompt to scam-checked homes and booked viewings in under a minute. That's Hestia."*
