"""Extract landlord / agent contact details (phone numbers + emails) from an agent response.

The ranker (`backend/agent.py`) returns a `PropertyDetails` object per listing. Gemini fills
`agent_phone` / `agent_email`, but in practice those fields are messy ("Τηλ: 210 123 4567",
"6912 345 678 / 210...", null with the number buried in free text, the portal's own support
e-mail, ...). This module turns any agent response into clean, de-duplicated, E.164 phone
numbers and validated e-mail addresses using deterministic regex rules (no LLM call), so the
outreach step is predictable and cheap.

Accepted inputs: a Pydantic model, a dict, or a raw string.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, Field, computed_field

PhoneKind = Literal["mobile", "landline", "unknown"]

# Structured fields the agent may use, in priority order.
PHONE_KEYS = (
    "agent_phone",
    "contact_phone",
    "landlord_phone",
    "owner_phone",
    "phone",
    "phone_number",
    "telephone",
    "mobile",
)
EMAIL_KEYS = ("agent_email", "contact_email", "landlord_email", "owner_email", "email")
NAME_KEYS = ("agent_name", "contact_name", "landlord_name", "owner_name")
# Keys never scanned as free text (their digits are IDs, not phone numbers).
SKIP_TEXT_KEYS = {"url", "link", "href", "image", "images", "photos"}

# Portals / platforms whose own contact details appear on scraped pages. We must never
# message these instead of the landlord.
BLOCKED_EMAIL_DOMAINS = {
    "spitogatos.gr",
    "xe.gr",
    "plot.gr",
    "facebook.com",
    "facebookmail.com",
    "example.com",
    "sentry.io",
}
BLOCKED_EMAIL_LOCAL_PARTS = {"noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon"}
NON_EMAIL_TLDS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "avif"}

DEFAULT_COUNTRY_CODE = "30"  # Greece: bare 10-digit numbers are assumed to be Greek.

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# A run of digits with common separators, optionally starting with + or 00.
_PHONE_CANDIDATE_RE = re.compile(r"(?<![\w/])(?:\+|00)?\d[\d \-.()/]{6,20}\d(?![\w/])")


class ContactPhone(BaseModel):
    e164: str = Field(description="Normalized E.164 number, e.g. +306912345678.")
    raw: str = Field(description="The text the number was extracted from.")
    kind: PhoneKind = Field(description="mobile / landline (Greek numbers only) or unknown.")
    source: str = Field(description="Field the number came from, e.g. 'agent_phone'.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sms_capable(self) -> bool:
        # Greek landlines (+302...) cannot receive SMS; foreign numbers we can't classify.
        return self.kind != "landline"


class ContactEmail(BaseModel):
    address: str
    source: str


class ExtractedContacts(BaseModel):
    name: Optional[str] = None
    phones: list[ContactPhone] = Field(default_factory=list)
    emails: list[ContactEmail] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sms_phone(self) -> Optional[str]:
        """Best number to text: the first SMS-capable phone (structured fields come first)."""
        return next((p.e164 for p in self.phones if p.sms_capable), None)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def email(self) -> Optional[str]:
        return self.emails[0].address if self.emails else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_contact(self) -> bool:
        return bool(self.phones or self.emails)


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------
def _classify_greek(national: str) -> PhoneKind:
    if national.startswith("69"):
        return "mobile"
    if national.startswith("2"):
        return "landline"
    return "unknown"


def normalize_phone(
    raw: str, default_country_code: str = DEFAULT_COUNTRY_CODE
) -> Optional[tuple[str, PhoneKind]]:
    """Normalizes a phone string to `(e164, kind)` or returns None if it isn't a plausible number.

    Rules (pragmatic MVP, tuned for Greek listings):
      * `+CC...` / `00CC...` → international, 8-15 digits.
      * Bare 10-digit numbers starting with `2` (landline) or `69` (mobile) → +30.
      * `30XXXXXXXXXX` (12 digits) → +30.
      * Greek numbers must have exactly 10 national digits.
    """
    if not raw:
        return None
    cleaned = raw.strip()
    has_plus = cleaned.startswith("+")
    digits = re.sub(r"\D", "", cleaned)
    if not has_plus and digits.startswith("00"):
        has_plus, digits = True, digits[2:]

    if has_plus:
        if not 8 <= len(digits) <= 15:
            return None
        if digits.startswith("30"):
            national = digits[2:]
            if len(national) != 10:
                return None
            return f"+{digits}", _classify_greek(national)
        return f"+{digits}", "unknown"

    if default_country_code == "30":
        if len(digits) == 12 and digits.startswith("30"):
            digits = digits[2:]
        if len(digits) == 10 and (digits.startswith("2") or digits.startswith("69")):
            return f"+30{digits}", _classify_greek(digits)
        return None

    if 8 <= len(digits) <= 15:
        return f"+{default_country_code}{digits}", "unknown"
    return None


def find_phones(text: str, source: str = "text") -> list[ContactPhone]:
    """Finds all plausible phone numbers inside free text (URLs are stripped first)."""
    if not text:
        return []
    text = _URL_RE.sub(" ", text)
    found: list[ContactPhone] = []
    for match in _PHONE_CANDIDATE_RE.finditer(text):
        candidate = match.group(0)
        # "210 1234567 / 6912345678" is matched as one run: also try each "/"-separated part.
        parts = [candidate] + [p for p in candidate.split("/") if p.strip()]
        for part in parts:
            normalized = normalize_phone(part)
            if normalized:
                e164, kind = normalized
                found.append(ContactPhone(e164=e164, raw=part.strip(), kind=kind, source=source))
    return found


# ---------------------------------------------------------------------------
# E-mails
# ---------------------------------------------------------------------------
def _is_allowed_email(address: str) -> bool:
    local, _, domain = address.rpartition("@")
    if not local or not domain:
        return False
    if domain.rsplit(".", 1)[-1] in NON_EMAIL_TLDS:  # e.g. "logo@2x.png"
        return False
    if local in BLOCKED_EMAIL_LOCAL_PARTS:
        return False
    return not any(domain == d or domain.endswith("." + d) for d in BLOCKED_EMAIL_DOMAINS)


def find_emails(text: str, source: str = "text") -> list[ContactEmail]:
    if not text:
        return []
    found = []
    for match in _EMAIL_RE.finditer(text):
        address = match.group(0).strip(".").lower()
        if _is_allowed_email(address):
            found.append(ContactEmail(address=address, source=source))
    return found


# ---------------------------------------------------------------------------
# Agent response → contacts
# ---------------------------------------------------------------------------
def to_dict(item: Any) -> dict[str, Any]:
    if item is None:
        return {}
    if isinstance(item, BaseModel):
        return item.model_dump()
    if isinstance(item, dict):
        return dict(item)
    if isinstance(item, str):
        return {"text": item}
    return dict(getattr(item, "__dict__", {}))


def _as_texts(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def extract_contacts(response: Any) -> ExtractedContacts:
    """Extracts the landlord/agent's name, phone numbers and e-mails from an agent response.

    Structured fields (`agent_phone`, `agent_email`, ...) are trusted first; every other
    string field (e.g. `score_reason`, `basic_info`, raw text) is scanned as a fallback.
    Results are de-duplicated and keep that priority order.
    """
    data = to_dict(response)

    phones: list[ContactPhone] = []
    emails: list[ContactEmail] = []

    for key in PHONE_KEYS:
        for text in _as_texts(data.get(key)):
            matches = find_phones(text, source=key)
            if not matches:  # The whole field may be a single number our regex didn't split.
                normalized = normalize_phone(text)
                if normalized:
                    matches = [ContactPhone(e164=normalized[0], raw=text, kind=normalized[1], source=key)]
            phones.extend(matches)
            # Gemini sometimes puts the e-mail in the phone field (or vice versa).
            emails.extend(find_emails(text, source=key))

    for key in EMAIL_KEYS:
        for text in _as_texts(data.get(key)):
            emails.extend(find_emails(text, source=key))

    structured = set(PHONE_KEYS) | set(EMAIL_KEYS) | set(NAME_KEYS)
    for key, value in data.items():
        if key in structured or key.lower() in SKIP_TEXT_KEYS:
            continue
        for text in _as_texts(value) if isinstance(value, (str, list, tuple)) else []:
            phones.extend(find_phones(text, source=key))
            emails.extend(find_emails(text, source=key))

    name = next(
        (str(data[k]).strip() for k in NAME_KEYS if isinstance(data.get(k), str) and data[k].strip()),
        None,
    )
    return ExtractedContacts(
        name=name,
        phones=_dedupe(phones, key=lambda p: p.e164),
        emails=_dedupe(emails, key=lambda e: e.address),
    )


def _dedupe(items: list[Any], key: Any) -> list[Any]:
    """Keeps the first occurrence of each key, preserving priority order."""
    seen: set[str] = set()
    unique = []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            unique.append(item)
    return unique
