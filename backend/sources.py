"""Listing sources the search agent scans in parallel (one scanner agent per site).

Every source turns the shared `SearchPlan` (written once by Gemini in backend/agent.py) into
its own results-page URL, downloads it with Firecrawl and returns the listing cards on it:

  spitogatos  Gemini writes the URL (area slug + filters); Gemini reads the cards from markdown.
  xe          xe.gr keys areas by Google place id: looked up in `XE_PLACES`, else found with a
              Firecrawl web search, else all of Athens. The results page embeds its listings as
              JSON (`data-json-data`), parsed directly (no LLM call).
  booking     furnished short stays: a 30-night stay starting in two weeks, so the price shown
              is one month's cost. Gemini reads the cards from markdown.

Enable a subset with SEARCH_SOURCES=spitogatos,xe,booking (default: all of them).
Helpers from backend.agent are imported lazily (agent.py imports this module).
"""

from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Optional
from urllib.parse import urlencode, urlparse

from backend.photos import card_thumbnails

LogFn = Callable[..., None]  # log(text, kind="info")

MARKDOWN_CHARS = 25000


@dataclass
class ScanResult:
    url: str
    listings: list = field(default_factory=list)  # PropertyPreview
    thumbnails: dict[str, str] = field(default_factory=dict)
    kb: int = 0


def _bare(url: str) -> str:
    return url.replace("https://", "").replace("www.", "")


def _extract_cards(markdown: str, site: str, hint: str = "") -> list:
    """Gemini reads every listing card on a results page (markdown)."""
    from backend.agent import AllProperties, _generate

    prompt = f"""
    Read the following markdown from the {site} search results.
    Identify ALL property listings on the page.
    For each one, find its URL, price, square meters, and a brief description.
    Ignore ads or links that are not property listings.
    {hint}

    Markdown:
    {markdown[:MARKDOWN_CHARS]}
    """
    return _generate(prompt, AllProperties).properties


class ListingSource:
    key: str = ""
    name: str = ""
    domain: str = ""
    short_stay: bool = False  # Prices are not long-term rents (kept out of the scam-gate cohort).

    def scan(self, plan: Any, log: LogFn) -> ScanResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Spitogatos
# ---------------------------------------------------------------------------
class Spitogatos(ListingSource):
    key, name, domain = "spitogatos", "Spitogatos", "spitogatos.gr"

    def search_url(self, plan: Any) -> str:
        url = (getattr(plan, "spitogatos_url", "") or "").strip()
        if "spitogatos.gr" in url:
            return url
        return f"https://www.spitogatos.gr/enoikiaseis-katoikies/{_slug(_first_part(plan.area)) or 'athina'}"

    def scan(self, plan: Any, log: LogFn) -> ScanResult:
        from backend.agent import get_markdown

        url = self.search_url(plan)
        log(f"Opening {_bare(url)}")
        markdown = get_markdown(url)
        kb = len(markdown) // 1000 or 1
        log(f"Results page downloaded ({kb} KB); the agent is reading the listing cards")
        return ScanResult(url, _extract_cards(markdown, "Spitogatos"), card_thumbnails(markdown), kb)


# ---------------------------------------------------------------------------
# xe.gr
# ---------------------------------------------------------------------------
_ATHENS = "ChIJ8UNwBh-9oRQR3Y1mdkU1Nic"

# xe.gr area ids (Google place ids), from xe.gr's own area pages. Keys are accent-free lowercase.
XE_PLACES: dict[str, str] = {
    **dict.fromkeys(["athens", "athina", "athhna", "αθηνα", "athens center", "kentro"], _ATHENS),
    **dict.fromkeys(["pangrati", "pagkrati", "pagrati", "παγκρατι"], "ChIJy1stSUK9oRQRi9ObJcOmO20"),
    **dict.fromkeys(["neo pangrati", "neo pagkrati", "νεο παγκρατι"], "ChIJNZDiDGa9oRQR5teFQqTXY0A"),
    **dict.fromkeys(["kypseli", "kipseli", "κυψελη"], "ChIJc0WaHrmioRQRUk07-S29ACY"),
    **dict.fromkeys(["galatsi", "γαλατσι"], "ChIJLbYjnoSioRQRGDYRmwa6d6M"),
    **dict.fromkeys(["gouva", "goyva", "γουβα"], "ChIJy9cOQgy9oRQR8k87-S29ACY"),
    **dict.fromkeys(["piraeus", "peiraias", "pireas", "πειραιας"], "ChIJRzGst-u7oRQR9_0w_5XaINg"),
    **dict.fromkeys(["peristeri", "περιστερι"], "ChIJTazECEejoRQRYRYsuxSJ348"),
    **dict.fromkeys(["aigaleo", "egaleo", "αιγαλεω"], "ChIJvUGcxaS8oRQRhQVsOC1EXzw"),
    **dict.fromkeys(["ilion", "ιλιον"], "ChIJZfP8CqijoRQRoHm54iy9AAQ"),
    **dict.fromkeys(["petroupoli", "petroypolh", "πετρουπολη"], "ChIJ46nkZnejoRQRhcY8oQ1xtI4"),
    **dict.fromkeys(["chaidari", "haidari", "χαιδαρι"], "ChIJIZwoz9W6oRQREHu54iy9AAQ"),
    **dict.fromkeys(["ilioupoli", "hlioypolh", "ηλιουπολη"], "ChIJ6QytjI69oRQRmVCWR9qyKrA"),
    **dict.fromkeys(["thessaloniki", "thessalonikh", "θεσσαλονικη"], "ChIJ7eAoFPQ4qBQRqXTVuBXnugk"),
    **dict.fromkeys(["chalkida", "chalkis", "χαλκιδα"], "ChIJSxfWwksWoRQRBMk0e18KCzg"),
    **dict.fromkeys(["patra", "patras", "πατρα"], "ChIJLe0kpZk1XhMRoIy54iy9AAQ"),
    **dict.fromkeys(["kalamata", "καλαματα"], "ChIJKXhLYpmwYRMRnl9ice2VH_w"),
    **dict.fromkeys(["larisa", "larissa", "λαρισα"], "ChIJN86P3FaIWBMREMS54iy9AAM"),
    **dict.fromkeys(["trikala", "τρικαλα"], "ChIJXy53IjMZWRMRwJ-54iy9AAQ"),
}

# An xe.gr area page: /property/r/enoikiaseis-katoikion/<place id>_<slug> (ids may contain "_").
_XE_AREA_RE = re.compile(r"xe\.gr/property/r/enoikiaseis-(?:katoikion|diamerismaton)/([^/?#\s]+)_([a-z0-9-]+)")
_XE_JSON_RE = re.compile(r'data-json-data="([^"]+)"')
_NUMBER_RE = re.compile(r"\d[\d.]*")
_TAG_RE = re.compile(r"<[^>]+>")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.replace("-", " ")).strip().lower()


def _first_part(area: str) -> str:
    return (area or "").split(",")[0].strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalize(text)).strip("-")


def _number(text: Any) -> Optional[int]:
    """580 € -> 580, 1.200 € -> 1200, 47 τ.μ. -> 47."""
    match = _NUMBER_RE.search(str(text or ""))
    if not match:
        return None
    try:
        return int(match.group(0).replace(".", ""))
    except ValueError:
        return None


def _search_xe_place(name: str) -> Optional[tuple[str, str]]:
    """(place id, slug) of xe.gr's area page for `name`, found with a Firecrawl web search."""
    from backend.agent import _field, _firecrawl

    res = _firecrawl().search(f"xe.gr ενοικιάσεις κατοικιών {name}", include_domains=["xe.gr"], limit=5)
    items = _field(res, "web", "data") or []
    for item in items:
        match = _XE_AREA_RE.search(_field(item, "url") or "")
        if match:
            return match.group(1), match.group(2)
    return None


def parse_xe_results(raw_html: str) -> tuple[list, dict[str, str]]:
    """Listing cards from the JSON xe.gr embeds in its results page: (previews, thumbnails)."""
    from backend.agent import PropertyPreview

    match = _XE_JSON_RE.search(raw_html or "")
    if not match:
        return [], {}
    try:
        data = json.loads(html.unescape(match.group(1)))
    except ValueError:
        return [], {}
    previews, thumbs = [], {}
    for r in data.get("results") or []:
        url = r.get("url")
        if not isinstance(url, str) or "/property/d/" not in url:
            continue
        text = html.unescape(_TAG_RE.sub(" ", r.get("publication_text_html") or ""))
        text = re.sub(r"\s+", " ", text).strip()
        bits = [r.get("title"), r.get("address")]
        if r.get("levels"):
            bits.append(f"floor {', '.join(map(str, r['levels']))}")
        if r.get("bedrooms"):
            bits.append(f"{r['bedrooms']} bedroom{'' if r['bedrooms'] == 1 else 's'}")
        if r.get("construction_year"):
            bits.append(f"built {r['construction_year']}")
        if text:
            bits.append(text[:180])
        previews.append(
            PropertyPreview(
                url=url,
                price=_number(r.get("price")),
                sqm=_number(r.get("size_with_square_meter")),
                basic_info=" · ".join(str(b) for b in bits if b),
            )
        )
        gallery = r.get("image_gallery") or []
        photo = (gallery[0].get("medium") or {}).get("jpeg") if gallery and isinstance(gallery[0], dict) else None
        if isinstance(photo, str):
            thumbs[url] = photo
    return previews, thumbs


class Xe(ListingSource):
    key, name, domain = "xe", "xe.gr", "xe.gr"

    def resolve_place(self, plan: Any, log: LogFn) -> str:
        """xe.gr place id for the requested area: known table → web search → city → Athens."""
        parts = [p.strip() for p in (plan.area or "").split(",") if p.strip()]
        local = [plan.area_greek] if getattr(plan, "area_greek", None) else []
        for name in (parts[:1] + local):
            place = XE_PLACES.get(_normalize(name))
            if place:
                log(f"Area {name} is a known xe.gr area")
                return place
        query = (local or parts or ["Αθήνα"])[0]
        try:
            found = _search_xe_place(query)
        except Exception as exc:  # Search unavailable: fall back to the city.
            found = None
            log(f"Could not look up the area on xe.gr ({exc.__class__.__name__})", "warn")
        if found:
            log(f"Found the xe.gr area page for {query} ({found[1]})")
            return found[0]
        for name in parts[1:]:
            place = XE_PLACES.get(_normalize(name))
            if place:
                log(f"Area not found on xe.gr: searching all of {name}", "warn")
                return place
        log("Area not found on xe.gr: searching all of Athens", "warn")
        return _ATHENS

    def search_url(self, plan: Any, place_id: str) -> str:
        url = (
            "https://www.xe.gr/property/results?transaction_name=rent&item_type=re_residence"
            f"&geo_place_ids[]={place_id}"
        )
        if getattr(plan, "max_price", None):
            url += f"&maximum_price={int(plan.max_price)}"
        return url

    def scan(self, plan: Any, log: LogFn) -> ScanResult:
        from backend.agent import scrape_page

        url = self.search_url(plan, self.resolve_place(plan, log))
        log(f"Opening {_bare(url)}")
        page = scrape_page(url, raw_html=True)
        kb = len(page.raw_html or page.markdown) // 1000 or 1
        listings, thumbs = parse_xe_results(page.raw_html)
        if listings:
            log(f"Results page downloaded ({kb} KB); read {len(listings)} listings from its data")
            return ScanResult(url, listings, thumbs, kb)
        log("No structured data on the page: the agent is reading the listing cards", "warn")
        return ScanResult(url, _extract_cards(page.markdown, "xe.gr"), card_thumbnails(page.markdown), kb)


# ---------------------------------------------------------------------------
# Booking.com
# ---------------------------------------------------------------------------
STAY_NIGHTS = 30
STAY_LEAD_DAYS = 14

_BOOKING_HOTEL_RE = re.compile(r"(https://www\.booking\.com/hotel/[a-z]{2}/[^?#\s)\"]+?\.html)(?:\?[^)\s\"]*)?")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


class Booking(ListingSource):
    key, name, domain = "booking", "Booking.com", "booking.com"
    short_stay = True

    @staticmethod
    def stay(today: Optional[date] = None) -> tuple[date, date]:
        checkin = (today or date.today()) + timedelta(days=STAY_LEAD_DAYS)
        return checkin, checkin + timedelta(days=STAY_NIGHTS)

    def stay_params(self, today: Optional[date] = None) -> dict[str, Any]:
        checkin, checkout = self.stay(today)
        return {
            "checkin": checkin.isoformat(),
            "checkout": checkout.isoformat(),
            "group_adults": 1,
            "no_rooms": 1,
            "group_children": 0,
            "selected_currency": "EUR",
        }

    def search_url(self, plan: Any, today: Optional[date] = None) -> str:
        area = plan.area or "Athens"
        if "greece" not in area.lower():
            area += ", Greece"
        params: dict[str, Any] = {"ss": area, **self.stay_params(today), "lang": "en-gb", "nflt": "ht_id=201"}
        if getattr(plan, "max_price", None):
            params["order"] = "price"  # Cheapest first, so budget stays make the first page.
        return "https://www.booking.com/searchresults.html?" + urlencode(params)

    def listing_url(self, url: str, today: Optional[date] = None) -> str:
        """Property page without tracking params, with the stay dates so it shows the price."""
        base = url.split("?", 1)[0].split("#", 1)[0]
        return f"{base}?{urlencode(self.stay_params(today))}"

    def scan(self, plan: Any, log: LogFn) -> ScanResult:
        from backend.agent import get_markdown

        url = self.search_url(plan)
        checkin, checkout = self.stay()
        log(f"Pricing a {STAY_NIGHTS}-night stay, {checkin:%d %b} to {checkout:%d %b}")
        log(f"Opening {_bare(url.split('&lang=')[0])}")
        markdown = get_markdown(url)
        kb = len(markdown) // 1000 or 1
        thumbs = {
            self.listing_url(link): image
            for link, image in card_thumbnails(markdown).items()
            if "booking.com/hotel/" in link
        }
        # Skip the filter sidebar, drop images and tracking params: the cards fit in the prompt.
        start = markdown.find("booking.com/hotel/")
        cards = markdown[max(0, start - 1500):] if start >= 0 else markdown
        cards = _BOOKING_HOTEL_RE.sub(r"\1", _MD_IMAGE_RE.sub("", cards))
        log(f"Results page downloaded ({kb} KB); the agent is reading the listing cards")
        hint = (
            f"Prices shown are the total for a {STAY_NIGHTS}-night stay: report that total as the price. "
            "Only include links to booking.com/hotel/ property pages."
        )
        listings = [
            item.model_copy(update={"url": self.listing_url(item.url)})
            for item in _extract_cards(cards, "Booking.com", hint)
            if "booking.com/hotel/" in item.url
        ]
        return ScanResult(url, listings, thumbs, kb)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
ALL_SOURCES: tuple[ListingSource, ...] = (Spitogatos(), Xe(), Booking())


def enabled_sources() -> list[ListingSource]:
    """Sources named in SEARCH_SOURCES (comma-separated keys), or all of them."""
    wanted = {s.strip().lower() for s in os.getenv("SEARCH_SOURCES", "").split(",") if s.strip()}
    chosen = [s for s in ALL_SOURCES if not wanted or s.key in wanted]
    return chosen or list(ALL_SOURCES)


def source_for_url(url: str) -> Optional[ListingSource]:
    host = urlparse(url or "").netloc.lower()
    return next((s for s in ALL_SOURCES if host == s.domain or host.endswith("." + s.domain)), None)
