"""Environment readiness check. Read-only: it never sends an SMS or e-mail.

    uv run python -m backend.check_env

Checks: dependencies, .env presence, secrets not leaking into .env.example, outreach safety
settings, Twilio credentials / sender number / trial restrictions (via read-only GET calls),
and the search-agent keys. Exits non-zero if an enabled outreach channel is not ready.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values, load_dotenv

from backend.outreach.channels import TWILIO_API_BASE, ResendEmailSender, TwilioSmsSender
from backend.outreach.contacts import normalize_phone
from backend.outreach.service import OutreachSettings

ROOT = Path(__file__).resolve().parent.parent
SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "SID", "PASSWORD")

results: list[tuple[str, str, str]] = []  # (status, check, detail)


def report(status: str, check: str, detail: str = "") -> None:
    results.append((status, check, detail))


def mask(value: str) -> str:
    return value[:4] + "…" if len(value) > 6 else "…"


def check_files() -> None:
    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if env_file.exists():
        report("OK", ".env file", "found")
    else:
        report("FAIL", ".env file", "missing: copy .env.example to .env and fill it in")

    if example.exists():
        leaked = [
            k for k, v in dotenv_values(example).items()
            if v and v.strip() and any(h in k for h in SECRET_HINTS)
        ]
        if leaked:
            report("FAIL", ".env.example has no secrets", f"tracked by git but contains: {', '.join(leaked)}")
        else:
            report("OK", ".env.example has no secrets")


def check_dependencies() -> None:
    for module in ("fastapi", "httpx", "pydantic", "dotenv", "google.genai", "firecrawl"):
        try:
            importlib.import_module(module)
            report("OK", f"import {module}")
        except Exception as exc:  # noqa: BLE001
            report("FAIL", f"import {module}", f"{exc!r}; run `uv sync`")


def check_outreach_settings() -> OutreachSettings:
    s = OutreachSettings.from_env()
    report("INFO", "OUTREACH_CHANNELS", ", ".join(s.channels) or "none enabled")
    report(
        "INFO", "OUTREACH_DRY_RUN",
        "true: messages are composed but NOT sent" if s.dry_run else "false: messages WILL be sent",
    )
    if s.override_phone:
        ok = normalize_phone(s.override_phone)
        report("OK" if ok else "FAIL", "OUTREACH_OVERRIDE_PHONE",
               f"all SMS redirected to {ok[0]}" if ok else "not a valid phone number")
    else:
        report("INFO", "OUTREACH_OVERRIDE_PHONE", "not set: real sends go to landlords")
    return s


def check_twilio(settings: OutreachSettings) -> None:
    if "sms" not in settings.channels:
        report("INFO", "Twilio", "SMS channel disabled, skipped")
        return
    sms = TwilioSmsSender.from_env()
    if sms.missing_config:
        report("FAIL", "Twilio config", sms.missing_config)
        return
    if not sms.account_sid.startswith("AC"):  # type: ignore[union-attr]
        report("WARN", "TWILIO_ACCOUNT_SID", "should start with 'AC'")

    auth = (sms.account_sid, sms.auth_token)
    base = f"{TWILIO_API_BASE}/Accounts/{sms.account_sid}"
    with httpx.Client(timeout=15.0, auth=auth) as client:  # type: ignore[arg-type]
        try:
            resp = client.get(f"{base}.json")
        except httpx.HTTPError as exc:
            report("FAIL", "Twilio credentials", f"request failed: {exc!r}")
            return
        if resp.status_code == 401:
            report("FAIL", "Twilio credentials", "401 Unauthorized: wrong Account SID / Auth Token")
            return
        if resp.status_code != 200:
            report("FAIL", "Twilio credentials", f"HTTP {resp.status_code}: {resp.text[:200]}")
            return
        account = resp.json()
        is_trial = account.get("type") == "Trial"
        report(
            "OK" if account.get("status") == "active" else "FAIL",
            "Twilio credentials",
            f"account '{account.get('friendly_name')}' status={account.get('status')} type={account.get('type')}",
        )

        if sms.messaging_service_sid:
            r = client.get(f"https://messaging.twilio.com/v1/Services/{sms.messaging_service_sid}")
            report("OK" if r.status_code == 200 else "FAIL", "Twilio Messaging Service",
                   r.json().get("friendly_name", "") if r.status_code == 200 else f"HTTP {r.status_code}")
        else:
            normalized = normalize_phone(sms.from_number or "")
            if not normalized:
                report("FAIL", "TWILIO_FROM_NUMBER", "not a valid E.164 number")
            else:
                r = client.get(f"{base}/IncomingPhoneNumbers.json", params={"PhoneNumber": normalized[0]})
                numbers = r.json().get("incoming_phone_numbers", []) if r.status_code == 200 else []
                if not numbers:
                    report("FAIL", "TWILIO_FROM_NUMBER", f"{normalized[0]} is not a number on this Twilio account")
                else:
                    caps = numbers[0].get("capabilities", {})
                    report("OK" if caps.get("sms") else "FAIL", "TWILIO_FROM_NUMBER",
                           f"{normalized[0]} owned; sms capability={caps.get('sms')}")

        if is_trial:
            r = client.get(f"{base}/OutgoingCallerIds.json")
            verified = [c.get("phone_number") for c in r.json().get("outgoing_caller_ids", [])] if r.status_code == 200 else []
            masked = ", ".join(n[:-4] + "****" for n in verified) or "none"
            report("WARN", "Twilio trial account",
                   f"SMS only reach verified numbers ({masked}); messages get a trial prefix. "
                   "Set OUTREACH_OVERRIDE_PHONE to a verified number for demos.")
            if settings.override_phone and verified:
                override = normalize_phone(settings.override_phone)
                if override and override[0] not in verified:
                    report("FAIL", "Override phone verified", f"{override[0]} is not verified on the trial account")


def check_resend(settings: OutreachSettings) -> None:
    email = ResendEmailSender.from_env()
    enabled = "email" in settings.channels
    level = "FAIL" if enabled else "WARN"  # Only blocking when the e-mail channel is on.
    if not enabled:
        report("INFO", "E-mail channel", "disabled (OUTREACH_CHANNELS); Resend validated anyway")
    if email.missing_config:
        report(level, "RESEND_API_KEY", email.missing_config)
        return
    try:
        resp = httpx.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {email.api_key}"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        report(level, "RESEND_API_KEY", f"request failed: {exc!r}")
        return
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    from_domain = email.from_email.rsplit("@", 1)[-1].strip(" >").lower()
    if resp.status_code == 401 and body.get("name") == "restricted_api_key":
        report("OK", "RESEND_API_KEY", "valid (sending-only key; domain check skipped)")
        if from_domain == "resend.dev":
            report("WARN", "RESEND_FROM_EMAIL",
                   "using onboarding@resend.dev: only delivers to the Resend account owner's inbox")
        return
    if resp.status_code != 200:
        report(level, "RESEND_API_KEY", f"HTTP {resp.status_code}: {body.get('message') or resp.text[:200]}")
        return
    domains = {d.get("name"): d.get("status") for d in body.get("data", [])}
    report("OK", "RESEND_API_KEY", f"valid; domains: {domains or 'none'}")

    if from_domain == "resend.dev":
        report("WARN", "RESEND_FROM_EMAIL",
               "using onboarding@resend.dev: only delivers to the Resend account owner's inbox")
    elif domains.get(from_domain) == "verified":
        report("OK", "RESEND_FROM_EMAIL", f"{from_domain} is verified")
    else:
        report(level, "RESEND_FROM_EMAIL",
               f"domain '{from_domain}' is {domains.get(from_domain, 'not added')} in Resend")


def check_gemini() -> None:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
    if not key:
        report("WARN", "GEMINI_API_KEY", "not set: /api/search will return 503")
        return
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    try:
        from google import genai

        client = genai.Client(api_key=key)  # Keep a reference: a GC'd client closes itself.
        info = client.models.get(model=model)  # Free metadata call.
        report("OK", "GEMINI_API_KEY", f"valid; model '{info.name}' available")
    except Exception as exc:  # noqa: BLE001
        report("FAIL", "GEMINI_API_KEY / GEMINI_MODEL", f"{model}: {str(exc)[:200]}")


def check_firecrawl() -> None:
    key = os.getenv("FIRECRAWL_API_KEY")
    if not key:
        report("WARN", "FIRECRAWL_API_KEY", "not set: /api/search will return 503")
        return
    headers = {"Authorization": f"Bearer {key}"}
    try:
        for version in ("v2", "v1"):  # Credit-usage endpoint: validates the key, costs nothing.
            resp = httpx.get(f"https://api.firecrawl.dev/{version}/team/credit-usage", headers=headers, timeout=15.0)
            if resp.status_code != 404:
                break
    except httpx.HTTPError as exc:
        report("FAIL", "FIRECRAWL_API_KEY", f"request failed: {exc!r}")
        return
    if resp.status_code == 200:
        data = resp.json().get("data", {})
        credits = data.get("remainingCredits", data.get("remaining_credits"))
        report("OK" if credits != 0 else "FAIL", "FIRECRAWL_API_KEY", f"valid; remaining credits: {credits}")
    else:
        report("FAIL", "FIRECRAWL_API_KEY", f"HTTP {resp.status_code}: {resp.text[:200]}")


def check_oumi() -> None:
    from backend.decision import oumi_configured, probe_oumi

    if not oumi_configured():
        report("WARN", "OUMI_API_KEY / OUMI_PROJECT_ID", "not set: scam decision gate unavailable")
        return
    ok, detail = probe_oumi()  # One tiny Iris call: validates key, project and endpoint.
    report("OK" if ok else "FAIL", "OUMI_API_KEY / OUMI_PROJECT_ID", detail)


def check_agent_keys() -> None:
    check_gemini()
    check_firecrawl()
    check_oumi()


def main() -> int:
    load_dotenv(ROOT / ".env")
    check_files()
    check_dependencies()
    settings = check_outreach_settings()
    check_twilio(settings)
    check_resend(settings)
    check_agent_keys()

    icons = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}
    for status, check, detail in results:
        print(f"{icons[status]} {check}" + (f": {detail}" if detail else ""))
    failed = [r for r in results if r[0] == "FAIL"]
    print(f"\n{'NOT READY' if failed else 'READY'} for outreach ({len(failed)} failing checks)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
