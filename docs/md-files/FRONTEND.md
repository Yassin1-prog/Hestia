# Frontend: Hestia, the autonomous housing agent UI

Next.js 15 (App Router, React 19) single-page app in [`frontend/`](./frontend). It calls the FastAPI
backend at `POST http://localhost:8000/api/search` (and `/api/search/stream`) to fetch and evaluate
**real, live rental listing data**, falling back to realistic demo data only if the backend is offline,
errors or times out. That keeps the live demo safe.

## Run it locally

```powershell
# 1. Backend (optional; without it the UI runs on demo data)
uv run python -m uvicorn backend.main:app --reload --port 8000

# 2. Frontend
cd frontend
npm install
npm run dev          # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to point at a different backend. The default is
`http://localhost:8000`. Next.js reads env files from `frontend/`, not the repo root.

Checks (same as CI): `npm run typecheck`, `npm run build`, `npm run format:check`.

## Screens

| Area | What it does |
| --- | --- |
| **Top bar** | Logo and name on the left. **My Viewings**, **My Favorites** and **Settings/Profile** on the right open slide-in drawers. Counts show on the buttons. |
| **Hero** | Large prompt textarea: Enter sends, Shift+Enter adds a new line. Below it are 4 quick-demo chips that run immediately, and a pill showing how many saved preferences will be attached. |
| **Results (50/50)** | **Left, Agent Feed:** a step-by-step thought process, then the agent's conclusion typed out. Next come an overview of the top 3 (click one to scroll to its card) and an input for extra instructions, which re-runs the search with them appended. **Right:** skeleton cards while the agent works, then the AI Property Cards. |
| **Property card** | Rank, location, title and facts. A large **score badge** shows `9.3/10` and `Match 93%`: gold for 9 and above, emerald for 7 and above. An Oumi Iris badge (`Oumi Iris · Safe · X% risk` or `Oumi Iris · Possible scam · X% risk`, when `scam_verdict` is present) and feature tags follow; `POSSIBLY_SCAM` cards also show a plain-English warning (`scam_reason`) and lock outreach to draft-only (**Draft e-mail only** → **Drafted · Not Sent**). A **"Why the agent picked it"** block with a star icon shows `score_reason`. The questions the agent will ask come from `missing_info`. At the bottom are the agent phone (`tel:` link) or email (`mailto:`), favorite and listing links, and **Ask Agent to Contact** (which launches the outreach flow and adds the property to My Viewings). |
| **Settings/Profile** | Permanent preferences ("I have 2 cats", "Max budget €700") as removable chips, with one-click suggestions and an "attach to every search" toggle. Also the user's name, email and phone, which the outreach API needs later. |

The app is locked to the viewport (`100dvh`, `overflow: hidden` on `html/body`) and only the panes and
drawers scroll. Below 900px wide, the two panes stack and each scrolls on its own.

## Backend contract

- **Request:** `POST /api/search` with `{ "request": "<query>\n\nAlways respect these saved preferences: I have 2 cats; Max budget €700." }`.
  The profile constraints are appended on the client, so the backend needs no changes.
- **Response:** the current backend returns `PropertyDetails[]` (see `backend/agent.py`). The client also
  accepts `{ reply, properties, stats: { scanned, rejected, rejectReason } }` if the backend later adds
  them:
  - **`reply`:** the agent's conclusion. Without it, the client builds one from the top results.
  - **`stats`:** fills in the "Scanned 35 listings / Rejected 32 due to ..." lines.

  Extra optional fields the cards display if present: `title`, `location`, `scam_verdict`
  (`SAFE` | `POSSIBLY_SCAM`, from `backend/decision.py`), `scam_risk_pct` (0–100), and
  `scam_reason` (plain-English red flag when flagged).
- **Fallback:** a network error, non-2xx status or 180 s timeout switches to demo data, with a notice in
  the feed and a **Demo data** badge (it reads **Live data** whenever real market listings are used).
  The 3 demo sets in `src/lib/demo.ts` are chosen by keyword: default 2-bedroom apartment,
  city-center penthouse, and budget compact studio. Their phone numbers and links are placeholders.

## Decisions

- **The agents' work is streamed, not simulated.** `POST /api/search/stream` and
  `POST /api/outreach/stream` send NDJSON progress events (`step` / `log` / `draft` / `result` /
  `error`, see `backend/streaming.py`). `lib/trace.ts` reduces them into a step list, and a `Pacer`
  releases them one at a time (about 0.25 s per action), so a burst from the backend still reads as
  an agent working step by step. While a step runs, its actions appear one by one under it. Once it
  is done, it collapses to "N actions". Reopening it replays the actions with a stagger.
- **When the search finishes, the steps collapse** into a single summary line ("Agent finished in
  0:47 · 6 steps · 24 listings scanned · 3 shortlisted · Oumi Iris: all safe", or how many Oumi
  Iris flagged when any listing is `POSSIBLY_SCAM`, with a **Show work** toggle), and only the
  listings remain.
- **Ask Agent to Contact starts a live outreach agent inside the card.** It reads the listing,
  checks the user's calendar for free viewing slots, verifies the landlord's e-mail, types out the
  exact e-mail it wrote, and sends it. Then it collapses to the outcome and the proposed slots. Each
  card has its own agent, so several can run in parallel. The calendar is the Google Calendar secret
  iCal address from Settings. Without it, the agent uses a clearly labelled sample work week.
- **Details dialog.** **Details** (or the card title) opens a dialog with an animated score ring,
  per-metric score bars (Price & value, Space & layout, Location, Condition & light, Your
  must-haves), pros and cons, key facts (including €/m² and the scam check), features and open
  questions. The deep-scrape prompt asks Gemini for `pros`, `cons` and `metrics`. Results without
  them fall back to features, open questions and the overall score.
- **Listing photos.** Each listing agent asks Firecrawl for the page's images
  (`formats=["markdown","images"]`, same credit cost) and its `og:image`. `backend/photos.py`
  keeps up to 8 real photos (main one first) and drops logos, icons, maps, tracking pixels and
  size variants of the same photo. They arrive as `images` on each property. Cards show the main
  photo as a banner with a photo count, the details dialog has a gallery (arrows, ← → keys,
  thumbnails), and drawer items get a thumbnail. `<ListingPhoto>` loads each photo directly,
  then through `GET /api/image?url=…` if the portal blocks hot-linking, then shows a placeholder,
  so a broken image never appears. The proxy only fetches public http(s) hosts (checked again
  after every redirect) and only returns raster images up to 8 MB. Demo listings use
  Unsplash interior photos bundled in `public/demo/`, so the demo works offline.
- **Question briefing before outreach.** **Ask Agent to Contact** first shows the questions the
  agent will ask: the ranker's are pre-ticked, you can untick any, add your own, or pick
  suggestions (up to 10). **Send agent** starts it (for `POSSIBLY_SCAM` listings, the warning banner
  appears and the button reads **Draft e-mail only**, completing as **Drafted · Not Sent** without
  sending). That list is sent as `questions` and replaces `missing_info` in the e-mail; an empty
  list means "just ask for a viewing". Retries reuse it.
- **Collaborating agents are drawn as a live graph.** `agent` events (sub-agents in the inspect
  and scam steps) render as a hub wired to one node per agent. The wires stream packets while an
  agent works, then turn solid green or red.
- **Motion:**
  - Cards slide in and tilt slightly toward the pointer. They stop tilting while you type in the
    briefing or while their agent works.
  - Scores and stats count up.
  - Status text and buttons cross-fade.
  - Finished steps draw their checkmark with a ring burst.
  - Active agent avatars pulse.
  - All of it respects `prefers-reduced-motion`.
- **Offline fallback.** If the backend is unreachable, `lib/demoAgent.ts` plays the same event
  scripts on demo data. Demo listings are never e-mailed, even with the backend online (`demo: true`
  forces a dry run).
- **Viewings, favorites and profile live in `localStorage`** (`hestia.*` keys). No backend
  persistence exists yet, and the app works in memory if storage is blocked. Live agent steps are
  in memory only. The outcome, proposed slots and e-mail text are persisted on the viewing.
- **No UI framework, no emojis.** One hand-written stylesheet (`src/app/globals.css`) with design
  tokens on `:root`, glass panels, and emerald/gold accents on near-black. Icons come from
  `lucide-react`, fonts are Inter (body) and Manrope (display) via `next/font`, and motion respects
  `prefers-reduced-motion`.

## File map

```text
frontend/src/
├── app/
│   ├── layout.tsx         # fonts, metadata
│   ├── page.tsx           # state: search lifecycle, drawers, viewings/favorites/profile, toasts
│   ├── globals.css        # all styles (tokens, layout, cards, drawers, motion)
│   └── icon.svg           # favicon
├── components/
│   ├── TopNav.tsx         # logo + drawer buttons
│   ├── Hero.tsx           # prompt bar + quick chips
│   ├── AgentFeed.tsx      # search agent's live steps, collapses to a summary when done
│   ├── AgentSteps.tsx     # shared step list: live actions, collapse, staggered replay
│   ├── OutreachWorkspace.tsx # outreach agent inside a card: steps, typed e-mail, outcome
│   ├── PropertyCard.tsx   # AI property card + skeleton
│   ├── Drawer.tsx         # slide-in panel shell (Esc / backdrop to close)
│   └── Panels.tsx         # Contact Requests, My Favorites, Settings/Profile (+ calendar link)
└── lib/
    ├── api.ts             # streamSearch / streamOutreach (NDJSON), response normalizing
    ├── trace.ts           # agent event types, step reducer, Pacer, NDJSON reader
    ├── useSearchAgent.ts  # search lifecycle (live stream → demo fallback)
    ├── useOutreachAgents.ts # one outreach agent per listing, in parallel
    ├── demoAgent.ts       # offline event scripts for both agents
    ├── demo.ts            # fallback data
    ├── format.ts          # titles, prices, score helpers
    ├── storage.ts         # usePersistentState (localStorage)
    └── types.ts           # Property (mirrors PropertyDetails), Profile, Viewing, SearchResult
```
