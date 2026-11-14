"""Compose the SMS / e-mail a per-listing outreach agent sends to a landlord.

Templates are deterministic (no LLM call) so the user sees *exactly* what will be sent at the
approval gate (`/api/outreach/preview`). Every message discloses that it was sent by the
user's assistant, and gives the landlord the user's own contact details to reply to.
"""

from __future__ import annotations

import html
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Language = Literal["en", "el"]


class UserContact(BaseModel):
    """The house-hunter on whose behalf the agent reaches out."""

    name: str
    email: Optional[str] = Field(default=None, description="Used as e-mail Reply-To.")
    phone: Optional[str] = None


class OutreachContext(BaseModel):
    user: UserContact
    viewing_windows: list[str] = Field(
        default_factory=list,
        description="Free-text viewing slots, e.g. 'Mon 18 Nov, 18:00-20:00'.",
    )
    language: Language = "en"
    note: Optional[str] = Field(default=None, description="Optional personal note from the user.")
    questions: Optional[list[str]] = Field(
        default=None,
        description="The exact questions the user approved (ranker's + their own). "
        "When set (even to []), it replaces the listing's missing_info.",
    )


class EmailContent(BaseModel):
    subject: str
    text: str
    html: str


DEFAULT_QUESTIONS: dict[Language, list[str]] = {
    "en": [
        "Is the apartment still available?",
        "What is the earliest move-in date and the minimum lease term?",
        "Are utilities / building fees (koinoxrista) included in the rent?",
    ],
    "el": [
        "Είναι ακόμα διαθέσιμο το διαμέρισμα;",
        "Ποια είναι η νωρίτερη ημερομηνία μετακόμισης και η ελάχιστη διάρκεια μίσθωσης;",
        "Περιλαμβάνονται τα κοινόχρηστα / λογαριασμοί στο ενοίκιο;",
    ],
}

_T: dict[Language, dict[str, str]] = {
    "en": {
        "hello": "Hello",
        "intro": "my name is {user} and I'm interested in your rental listing{spec}",
        "available": "Is it still available? Could I come for a viewing {windows}?",
        "any_time": "at a time that suits you",
        "or": " or ",
        "reply_sms": "You can reply here{alt}. Thank you!",
        "alt_email": " or at {email}",
        "disclosure": "Sent on behalf of {user} by their relocation assistant.",
        "subject": "Viewing request: {summary}",
        "questions_header": "A few questions about the property:",
        "windows_header": "I'm available for a viewing:",
        "contact_header": "You can reach me at:",
        "thanks": "Thank you in advance,",
        "apartment": "apartment",
        "month": "/month",
        "sqm": "m²",
    },
    "el": {
        "hello": "Καλησπέρα σας",
        "intro": "ονομάζομαι {user} και ενδιαφέρομαι για την αγγελία ενοικίασης{spec}",
        "available": "Είναι ακόμα διαθέσιμο; Θα μπορούσα να το δω {windows};",
        "any_time": "σε ώρα που σας βολεύει",
        "or": " ή ",
        "reply_sms": "Μπορείτε να απαντήσετε εδώ{alt}. Ευχαριστώ!",
        "alt_email": " ή στο {email}",
        "disclosure": "Το μήνυμα στάλθηκε εκ μέρους του/της {user} από τον ψηφιακό βοηθό μετεγκατάστασης.",
        "subject": "Αίτημα επίσκεψης: {summary}",
        "questions_header": "Θα ήθελα να ρωτήσω:",
        "windows_header": "Είμαι διαθέσιμος/η για επίσκεψη:",
        "contact_header": "Μπορείτε να επικοινωνήσετε μαζί μου:",
        "thanks": "Ευχαριστώ εκ των προτέρων,",
        "apartment": "διαμέρισμα",
        "month": "/μήνα",
        "sqm": "τ.μ.",
    },
}

MAX_SMS_WINDOWS = 2
MAX_QUESTIONS = 5
MAX_APPROVED_QUESTIONS = 10  # The user picked these explicitly, so allow more.


def _spec(listing: dict[str, Any], t: dict[str, str]) -> str:
    """'65 m², €600/month' or '' when the listing has neither."""
    parts = []
    if listing.get("sqm"):
        parts.append(f"{listing['sqm']} {t['sqm']}")
    if listing.get("price"):
        parts.append(f"€{listing['price']}{t['month']}")
    return ", ".join(parts)


AGENCY_WORDS = (
    "real estate", "estate", "realty", "properties", "property", "home", "house", "re/max",
    "remax", "century 21", "agency", "group", "ltd", "ακίνητα", "ακινητα", "μεσιτ", "κτηματομεσ",
)


def greeting_name(name: Optional[str]) -> Optional[str]:
    """The name to greet, or None for a plain 'Hello,'.

    Portal contact names are often agencies in capitals with a person in brackets, e.g.
    'MEGA HOUSE REAL ESTATE (Π. ΠΑΥΛΙΔΗΣ)'. Greeting those reads robotic, so only a clean,
    normally-cased personal name is used.
    """
    n = " ".join((name or "").split())
    if not n or "(" in n or ")" in n or len(n) > 40:
        return None
    if n.isupper() and len(n) > 3:  # SHOUTED names are almost always agency listings.
        return None
    if any(word in n.lower() for word in AGENCY_WORDS):
        return None
    return n


def _greeting(name: Optional[str], t: dict[str, str]) -> str:
    n = greeting_name(name)
    return f"{t['hello']} {n}," if n else f"{t['hello']},"


def _clean(questions: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in questions or []:
        if not isinstance(q, str) or not q.strip():
            continue
        text = " ".join(q.split())
        if text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out


def _questions(listing: dict[str, Any], ctx: OutreachContext | Language) -> list[str]:
    """The user's approved questions, else the ranker's missing-info ones, else defaults."""
    lang: Language = ctx if isinstance(ctx, str) else ctx.language  # type: ignore[assignment]
    if not isinstance(ctx, str) and ctx.questions is not None:
        # The user reviewed the list: respect it exactly, even if they cleared it.
        return _clean(ctx.questions)[:MAX_APPROVED_QUESTIONS]
    custom = _clean(listing.get("missing_info"))
    return (custom or DEFAULT_QUESTIONS[lang])[:MAX_QUESTIONS]


def compose_sms(listing: dict[str, Any], landlord_name: Optional[str], ctx: OutreachContext) -> str:
    t = _T[ctx.language]
    spec = _spec(listing, t)
    windows = ctx.viewing_windows[:MAX_SMS_WINDOWS]
    greeting = _greeting(landlord_name, t)
    url = listing.get("url")
    intro = t["intro"].format(user=ctx.user.name, spec=f" ({spec})" if spec else "")
    lines = [
        f"{greeting} {intro}" + (f": {url}" if url else "."),
        t["available"].format(windows=t["or"].join(windows) if windows else t["any_time"]),
        t["reply_sms"].format(alt=t["alt_email"].format(email=ctx.user.email) if ctx.user.email else ""),
        f"- {t['disclosure'].format(user=ctx.user.name)}",
    ]
    return "\n".join(lines)


def compose_email(
    listing: dict[str, Any], landlord_name: Optional[str], ctx: OutreachContext
) -> EmailContent:
    t = _T[ctx.language]
    spec = _spec(listing, t)
    url = listing.get("url", "")
    summary = f"{spec} {t['apartment']}" if spec else (url or t["apartment"])
    greeting = _greeting(landlord_name, t)
    intro = t["intro"].format(user=ctx.user.name, spec=f" ({spec})" if spec else "") + "."
    intro = intro[0].upper() + intro[1:]
    questions = _questions(listing, ctx)
    windows = ctx.viewing_windows or [t["any_time"]]
    contacts = [c for c in (ctx.user.phone, ctx.user.email) if c]

    # Plain-text version.
    text_lines = [greeting, "", intro]
    if url:
        text_lines.append(url)
    if ctx.note:
        text_lines += ["", ctx.note]
    if questions:
        text_lines += ["", t["questions_header"], *[f"- {q}" for q in questions]]
    text_lines += ["", t["windows_header"], *[f"- {w}" for w in windows]]
    if contacts:
        text_lines += ["", t["contact_header"], *[f"- {c}" for c in contacts]]
    text_lines += ["", t["thanks"], ctx.user.name, "", "--", t["disclosure"].format(user=ctx.user.name)]

    # HTML version (same content, escaped).
    e = html.escape

    def ul(items: list[str]) -> str:
        return "<ul>" + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>"

    html_parts = [f"<p>{e(greeting)}</p>", f"<p>{e(intro)}"]
    if url:
        html_parts.append(f'<br><a href="{e(url, quote=True)}">{e(url)}</a>')
    html_parts.append("</p>")
    if ctx.note:
        html_parts.append(f"<p>{e(ctx.note)}</p>")
    if questions:
        html_parts += [f"<p>{e(t['questions_header'])}</p>", ul(questions)]
    html_parts += [f"<p>{e(t['windows_header'])}</p>", ul(windows)]
    if contacts:
        html_parts += [f"<p>{e(t['contact_header'])}</p>", ul(contacts)]
    html_parts += [
        f"<p>{e(t['thanks'])}<br>{e(ctx.user.name)}</p>",
        f'<p style="color:#888;font-size:12px">{e(t["disclosure"].format(user=ctx.user.name))}</p>',
    ]

    return EmailContent(
        subject=t["subject"].format(summary=summary),
        text="\n".join(text_lines),
        html="\n".join(html_parts),
    )
