# GENAI Summit Hackathon — One-Command Launcher
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[+] Created .env from .env.example" -ForegroundColor Green
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " GENAI Summit — Proactive Agent Mission Control" -ForegroundColor Cyan
Write-Host " Dashboard UI:  http://localhost:8000" -ForegroundColor Green
Write-Host " OpenAPI Docs:  http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
