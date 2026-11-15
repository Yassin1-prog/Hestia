"""Finds free viewing slots in the user's calendar before the agent writes to a landlord.

Calendar source, in order of preference:
  1. the user's Google Calendar "secret address in iCal format" (Settings → your calendar →
     Integrate calendar), sent from the profile or set server-wide as `GOOGLE_CALENDAR_ICS_URL`;
  2. a clearly labelled *sample* work week, so the demo still works without a calendar.

No OAuth is needed: the secret iCal address is a read-only feed of the user's own events.
Recurring events are expanded (`recurring-ical-events`), and events marked "Free"
(TRANSP:TRANSPARENT, e.g. most all-day events) do not block a viewing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Literal, Optional
from urllib.parse import parse_qs, quote, urlparse
from zoneinfo import ZoneInfo

import httpx

TIMEZONE = ZoneInfo(os.getenv("OUTREACH_TIMEZONE", "Europe/Athens"))
HORIZON_DAYS = 7
MAX_SLOTS = 3
MIN_SLOT = timedelta(minutes=60)
MAX_SLOT = timedelta(minutes=120)
TRAVEL_BUFFER = timedelta(minutes=30)

# When a viewing is reasonable: weekday evenings and weekend late mornings / afternoons.
VIEWING_HOURS: dict[int, list[tuple[time, time]]] = {
    **{d: [(time(18, 0), time(20, 30))] for d in range(5)},
    5: [(time(10, 0), time(14, 0)), (time(16, 0), time(19, 0))],
    6: [(time(11, 0), time(14, 0))],
}

CalendarSource = Literal["google", "ical", "sample"]


@dataclass
class BusyBlock:
    start: datetime
    end: datetime
    title: str


@dataclass
class FreeSlot:
    start: datetime
    end: datetime

    @property
    def label(self) -> str:
        """'Tue 18 Nov, 18:00-20:00' (ASCII dash: stays GSM-7 if it is ever texted)."""
        return f"{self.start:%a} {self.start.day} {self.start:%b}, {self.start:%H:%M}-{self.end:%H:%M}"


@dataclass
class Availability:
    source: CalendarSource
    window_start: date
    window_end: date
    events: int
    slots: list[FreeSlot]
    conflicts: list[str] = field(default_factory=list)
    """Human-readable 'Mon 17 Nov evening: Gym 18:00-19:30' lines for busy viewing windows."""
    error: Optional[str] = None
    """Set when a real calendar was requested but could not be read (sample used instead)."""


def resolve_calendar_url(url: Optional[str]) -> Optional[str]:
    raw = (url or os.getenv("GOOGLE_CALENDAR_ICS_URL") or "").strip()
    if not raw:
        return None
    if raw.startswith("webcal://"):
        raw = "https://" + raw[len("webcal://") :]
    if not raw.startswith(("https://", "http://")):
        raise ValueError("The calendar address must be an https:// or webcal:// iCal link")
    return _embed_to_ical(raw)


def _embed_to_ical(url: str) -> str:
    """A Google Calendar *embed* link (…/calendar/embed?src=<id>) → that calendar's public iCal feed.

    The public feed only works when the calendar is shared publicly ("Make available to public");
    a private calendar needs its "secret address in iCal format" instead.
    """
    parsed = urlparse(url)
    if parsed.hostname != "calendar.google.com" or not parsed.path.rstrip("/").endswith("/embed"):
        return url
    calendar_id = (parse_qs(parsed.query).get("src") or [""])[0].strip()
    if not calendar_id:
        return url
    return f"https://calendar.google.com/calendar/ical/{quote(calendar_id, safe='')}/public/basic.ics"


def _aware(value: datetime | date) -> tuple[datetime, bool]:
    """Returns (aware datetime, is_all_day)."""
    if isinstance(value, datetime):
        return (value.replace(tzinfo=TIMEZONE) if value.tzinfo is None else value.astimezone(TIMEZONE)), False
    return datetime.combine(value, time.min, TIMEZONE), True


def parse_ics(ics: bytes | str, start: datetime, end: datetime) -> list[BusyBlock]:
    """Busy blocks between `start` and `end`, with recurring events expanded."""
    import icalendar
    import recurring_ical_events

    calendar = icalendar.Calendar.from_ical(ics)
    blocks: list[BusyBlock] = []
    for event in recurring_ical_events.of(calendar).between(start, end):
        if str(event.get("TRANSP", "OPAQUE")).upper() == "TRANSPARENT":
            continue
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        dtstart = event.get("DTSTART")
        if dtstart is None:
            continue
        begin, all_day = _aware(dtstart.dt)
        dtend = event.get("DTEND")
        if dtend is not None:
            finish, _ = _aware(dtend.dt)
        else:
            finish = begin + (timedelta(days=1) if all_day else timedelta(hours=1))
        title = str(event.get("SUMMARY") or "Busy").strip() or "Busy"
        blocks.append(BusyBlock(begin, finish, title))
    return sorted(blocks, key=lambda b: b.start)


def sample_week(today: date) -> list[BusyBlock]:
    """A plausible work week, used only when no calendar is connected. Labelled as sample."""

    def at(day: date, h: int, m: int = 0) -> datetime:
        return datetime.combine(day, time(h, m), TIMEZONE)

    blocks: list[BusyBlock] = []
    for offset in range(HORIZON_DAYS + 1):
        day = today + timedelta(days=offset)
        weekday = day.weekday()
        if weekday < 5:
            blocks.append(BusyBlock(at(day, 9), at(day, 17, 30), "Work"))
        if weekday == 0:
            blocks.append(BusyBlock(at(day, 18, 0), at(day, 19, 30), "Gym"))
        if weekday == 2:
            blocks.append(BusyBlock(at(day, 18, 30), at(day, 21, 0), "Dinner with friends"))
        if weekday == 5:
            blocks.append(BusyBlock(at(day, 10, 0), at(day, 12, 30), "Football"))
    return blocks


def _fmt_range(a: datetime, b: datetime) -> str:
    return f"{a:%H:%M}-{b:%H:%M}"


def find_free_slots(
    busy: list[BusyBlock], now: datetime, max_slots: int = MAX_SLOTS
) -> tuple[list[FreeSlot], list[str]]:
    """First free viewing slot on each of the next days, plus the busy windows it skipped."""
    now = now.astimezone(TIMEZONE)
    slots: list[FreeSlot] = []
    conflicts: list[str] = []
    for offset in range(1, HORIZON_DAYS + 1):
        if len(slots) >= max_slots:
            break
        day = (now + timedelta(days=offset)).date()
        for open_t, close_t in VIEWING_HOURS.get(day.weekday(), []):
            w_start = datetime.combine(day, open_t, TIMEZONE)
            w_end = datetime.combine(day, close_t, TIMEZONE)
            blockers = [b for b in busy if b.start < w_end + TRAVEL_BUFFER and b.end + TRAVEL_BUFFER > w_start]
            # Walk the window, jumping past each blocker (plus travel time).
            cursor = w_start
            found: Optional[FreeSlot] = None
            for b in sorted(blockers, key=lambda b: b.start):
                if b.start - TRAVEL_BUFFER - cursor >= MIN_SLOT:
                    found = FreeSlot(cursor, min(b.start - TRAVEL_BUFFER, cursor + MAX_SLOT))
                    break
                cursor = max(cursor, b.end + TRAVEL_BUFFER)
            if not found and w_end - cursor >= MIN_SLOT:
                found = FreeSlot(cursor, min(w_end, cursor + MAX_SLOT))
            evening_blockers = [b for b in blockers if b.end > w_start and b.start < w_end]
            if evening_blockers:
                b = evening_blockers[0]
                part = "evening" if open_t.hour >= 16 else "morning"
                conflicts.append(f"{day:%a} {day.day} {day:%b} {part}: {b.title} {_fmt_range(b.start, b.end)}")
            if found:
                slots.append(found)
                break  # One slot per day keeps the proposals spread out.
    return slots, conflicts


async def check_availability(
    calendar_url: Optional[str],
    client: httpx.AsyncClient,
    now: Optional[datetime] = None,
) -> Availability:
    now = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    start = datetime.combine(now.date(), time.min, TIMEZONE)
    end = start + timedelta(days=HORIZON_DAYS + 1)
    error: Optional[str] = None
    busy: Optional[list[BusyBlock]] = None
    source: CalendarSource = "sample"

    try:
        url = resolve_calendar_url(calendar_url)
    except ValueError as exc:
        url, error = None, str(exc)
    if url:
        try:
            resp = await client.get(url, follow_redirects=True, timeout=15.0)
            resp.raise_for_status()
            busy = parse_ics(resp.content, start, end)
            source = "google" if "google.com" in url else "ical"
        except Exception as exc:  # Bad link, network, or not an iCal feed.
            error = f"Could not read the calendar ({exc.__class__.__name__})"
            busy = None
    if busy is None:
        busy = sample_week(now.date())
        source = "sample"

    slots, conflicts = find_free_slots(busy, now)
    in_window = [b for b in busy if b.end > now and b.start < end]
    return Availability(
        source=source,
        window_start=(now + timedelta(days=1)).date(),
        window_end=(now + timedelta(days=HORIZON_DAYS)).date(),
        events=len(in_window),
        slots=slots,
        conflicts=conflicts,
        error=error,
    )
