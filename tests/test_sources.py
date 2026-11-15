"""Listing-source adapters (backend/sources.py). No network: Firecrawl / Gemini are never called."""

import html
import json
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from backend import sources
from backend.sources import Booking, Spitogatos, Xe, enabled_sources, parse_xe_results, source_for_url


def _plan(**kw):
    base = dict(spitogatos_url="", area="Pangrati, Athens", area_greek="Παγκράτι",
                max_price=600, min_sqm=None, min_bedrooms=None)
    return SimpleNamespace(**{**base, **kw})


def _xe_page(results):
    blob = html.escape(json.dumps({"results": results}, ensure_ascii=False), quote=True)
    return f'<html><body><div data-json-data="{blob}"></div></body></html>'


XE_RESULT = {
    "url": "https://www.xe.gr/property/d/enoikiaseis-katoikion/ab63/athhna-pagkrati-580-47",
    "title": "Διαμέρισμα 47 τ.μ.",
    "address": "Αθήνα (Παγκράτι)",
    "price": "1.200 €",
    "size_with_square_meter": "47 τ.μ.",
    "levels": ["4ος"],
    "bedrooms": 1,
    "construction_year": 1972,
    "publication_text_html": "<p>Φωτεινό &amp; ανακαινισμένο</p>",
    "image_gallery": [{"medium": {"jpeg": "https://blob.cdn.xe.gr/photo.jpg"}}],
}


def test_parse_xe_results_reads_embedded_json():
    previews, thumbs = parse_xe_results(_xe_page([XE_RESULT, {"url": "https://www.xe.gr/property/r/x"}]))
    assert len(previews) == 1  # Area links are not listings.
    p = previews[0]
    assert (p.url, p.price, p.sqm) == (XE_RESULT["url"], 1200, 47)
    assert "Αθήνα (Παγκράτι)" in p.basic_info and "1 bedroom" in p.basic_info
    assert "Φωτεινό & ανακαινισμένο" in p.basic_info and "<p>" not in p.basic_info
    assert thumbs == {XE_RESULT["url"]: "https://blob.cdn.xe.gr/photo.jpg"}


def test_parse_xe_results_without_data_is_empty():
    assert parse_xe_results("<html>footer only</html>") == ([], {})


def test_xe_resolves_known_areas_without_searching(monkeypatch):
    monkeypatch.setattr(sources, "_search_xe_place", lambda name: pytest.fail("must not search"))
    xe = Xe()
    assert xe.resolve_place(_plan(), lambda *a: None) == "ChIJy1stSUK9oRQRi9ObJcOmO20"
    assert xe.resolve_place(_plan(area="Κυψέλη", area_greek=None), lambda *a: None) == "ChIJc0WaHrmioRQRUk07-S29ACY"
    url = xe.search_url(_plan(), "ChIJy1stSUK9oRQRi9ObJcOmO20")
    assert "geo_place_ids[]=ChIJy1stSUK9oRQRi9ObJcOmO20" in url and "maximum_price=600" in url


def test_xe_searches_unknown_areas_then_falls_back_to_the_city(monkeypatch):
    seen = []
    monkeypatch.setattr(sources, "_search_xe_place", lambda name: seen.append(name) or ("Eh_x_y", "vyronas"))
    assert Xe().resolve_place(_plan(area="Vyronas, Athens", area_greek="Βύρωνας"), lambda *a: None) == "Eh_x_y"
    assert seen == ["Βύρωνας"]

    monkeypatch.setattr(sources, "_search_xe_place", lambda name: None)
    city = Xe().resolve_place(_plan(area="Vyronas, Thessaloniki", area_greek="Βύρωνας"), lambda *a: None)
    assert city == sources.XE_PLACES["thessaloniki"]


def test_xe_area_regex_keeps_underscores_in_place_ids():
    m = sources._XE_AREA_RE.search(
        "https://www.xe.gr/property/r/enoikiaseis-katoikion/ChIJRzGst-u7oRQR9_0w_5XaINg_peiraias"
    )
    assert m and m.groups() == ("ChIJRzGst-u7oRQR9_0w_5XaINg", "peiraias")


def test_booking_prices_a_month_long_stay():
    url = Booking().search_url(_plan(), today=date(2026, 11, 15))
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["ss"] == "Pangrati, Athens, Greece"
    assert (q["checkin"], q["checkout"]) == ("2026-11-29", "2026-12-29")
    assert q["nflt"] == "ht_id=201" and q["selected_currency"] == "EUR" and q["order"] == "price"


def test_booking_listing_url_drops_tracking_and_keeps_dates():
    url = Booking().listing_url(
        "https://www.booking.com/hotel/gr/nice-flat.en-gb.html?aid=1&sid=abc#map", today=date(2026, 11, 15)
    )
    assert url.startswith("https://www.booking.com/hotel/gr/nice-flat.en-gb.html?checkin=2026-11-29&")
    assert "aid=" not in url and "#" not in url


def test_spitogatos_uses_the_planned_url_or_builds_one():
    planned = "https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati?max_price=600"
    assert Spitogatos().search_url(_plan(spitogatos_url=planned)) == planned
    assert Spitogatos().search_url(_plan(spitogatos_url="nonsense")).endswith("/enoikiaseis-katoikies/pangrati")


def test_source_for_url_and_enabled_sources(monkeypatch):
    assert source_for_url("https://www.xe.gr/property/d/x").key == "xe"
    assert source_for_url("https://www.booking.com/hotel/gr/x.html").short_stay is True
    assert source_for_url("https://example.com/") is None
    monkeypatch.setenv("SEARCH_SOURCES", "xe, booking")
    assert [s.key for s in enabled_sources()] == ["xe", "booking"]
    monkeypatch.setenv("SEARCH_SOURCES", "")
    assert [s.key for s in enabled_sources()] == ["spitogatos", "xe", "booking"]
