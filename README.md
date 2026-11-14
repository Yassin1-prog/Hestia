# GENAI Summit — Hackathon Starter

A lightweight **FastAPI (Python)** + **Next.js (React)** starter template built around the core hackathon pattern:

> **Goal → Plan → Tool Execution → End-to-End Deliverable**

---

## Project Structure

```text
Gen-AI-Summit/
├── .github/workflows/ci.yml # GitHub Actions CI (Ruff, Pytest, Prettier, Typecheck, Next build)
├── backend/
│   ├── main.py              # FastAPI endpoints (/api/health, /api/search, /api/outreach/*)
│   ├── agent.py             # Search & ranking agent (Gemini + Firecrawl) → PropertyDetails
│   ├── decision.py          # Oumi Iris scam decision gate (see OUMI_IRIS_INTEGRATION.md)
│   └── outreach/            # Contact extraction + Twilio SMS / Resend e-mail (see OUTREACH.md)
├── frontend/
│   └── src/                 # Hestia UI: prompt, agent feed, AI property cards (see FRONTEND.md)
├── tests/
│   ├── test_decision.py     # Oumi Iris decision tests
│   └── test_outreach.py     # Outreach extraction / messaging / API tests
├── .env.example             # Environment variable template
├── .prettierrc              # Shared Prettier formatting rules
├── pyproject.toml           # Python dependencies & Ruff/Pytest config (managed via uv)
└── run.ps1                  # Quick backend launcher for Windows
```

---

## Quickstart

### 1. Run Backend (FastAPI + `uv`)

```powershell
.\run.ps1
# Or manually:
uv run python -m uvicorn backend.main:app --reload --port 8000
```

* API: `http://localhost:8000`
* Interactive Swagger Docs: `http://localhost:8000/docs`

### 2. Run Frontend (Next.js)

```powershell
cd frontend
npm install
npm run dev
```

* Web UI: `http://localhost:3000`
* Works without the backend too (falls back to demo data). Details in [`FRONTEND.md`](./FRONTEND.md).

---

## Checks & CI

* **Backend lint & tests:**
  ```powershell
  uv run ruff check .
  uv run pytest -v
  ```
* **Frontend format, typecheck & build:**
  ```powershell
  cd frontend
  npm run format        # auto-format with Prettier
  npm run format:check  # verify formatting
  npm run typecheck
  npm run build
  ```

---

## How to Customize Tomorrow

1. **Add your API keys** in `.env` (copied from `.env.example`).
2. **Outreach:** fill the `TWILIO_*` / `RESEND_*` placeholders and read [`OUTREACH.md`](./OUTREACH.md). Sending stays in dry-run until `OUTREACH_DRY_RUN=false`. Check your setup with `uv run python -m backend.check_env`.
