"""Listing photos: extraction from scraped pages and the image proxy's safety checks."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.photos import ImageFetchError, card_thumbnails, fetch_image, listing_photos

PAGE = "https://www.spitogatos.gr/aggelia/123"


def test_listing_photos_prefers_og_image_and_drops_non_photos_and_size_variants():
    markdown = """
![logo](https://static.spitogatos.gr/img/logo.svg)
![](https://m1.spitogatos.gr/123456789_900x675.jpg?v=2)
![map](https://maps.googleapis.com/maps/api/staticmap?center=x)
![](https://m1.spitogatos.gr/987654321_900x675.jpg)
![](https://m1.spitogatos.gr/987654321_300x225.jpg)
![agent](https://m1.spitogatos.gr/agents/avatar_55.jpg)
"""
    photos = listing_photos(
        PAGE,
        markdown,
        og_image="https://m1.spitogatos.gr/123456789_1200x900.jpg",
        images=["https://www.spitogatos.gr/assets/icons/heart.png", "/relative/555555555_900x675.webp"],
    )
    assert photos == [
        "https://m1.spitogatos.gr/123456789_1200x900.jpg",
        "https://www.spitogatos.gr/relative/555555555_900x675.webp",
        "https://m1.spitogatos.gr/987654321_900x675.jpg",
    ]


def test_listing_photos_respects_limit():
    imgs = [f"https://cdn.example.org/photos/{n:09d}.jpg" for n in range(20)]
    assert len(listing_photos(PAGE, images=imgs, limit=5)) == 5


def test_card_thumbnails_maps_listing_links_to_their_image():
    md = "[![Flat](https://m1.spitogatos.gr/111111111_300x225.jpg) 2-bed €600](https://www.spitogatos.gr/aggelia/111)"
    assert card_thumbnails(md) == {
        "https://www.spitogatos.gr/aggelia/111": "https://m1.spitogatos.gr/111111111_300x225.jpg"
    }


def test_scrape_page_reads_v2_document(monkeypatch):
    import backend.agent as agent

    class FakeFirecrawl:
        def scrape(self, url, formats):
            assert formats == ["markdown", "images"]
            return SimpleNamespace(
                markdown="# Listing",
                images=["https://cdn.example.org/a.jpg"],
                metadata=SimpleNamespace(og_image="https://cdn.example.org/main.jpg"),
            )

    monkeypatch.setattr(agent, "_firecrawl", lambda: FakeFirecrawl())
    page = agent.scrape_page(PAGE, images=True)
    assert page.markdown == "# Listing"
    assert page.og_image == "https://cdn.example.org/main.jpg"
    assert page.images == ["https://cdn.example.org/a.jpg"]


def test_fetch_image_follows_redirects_and_checks_type():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start.jpg":
            return httpx.Response(302, headers={"location": "/real.jpg"})
        if request.url.path == "/real.jpg":
            assert request.headers["referer"] == "https://cdn.example.org/"
            return httpx.Response(200, content=b"\xff\xd8jpeg", headers={"content-type": "image/jpeg"})
        return httpx.Response(200, content=b"<svg/>", headers={"content-type": "image/svg+xml"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            ok = await fetch_image("https://cdn.example.org/start.jpg", client, check_host=False)
            with pytest.raises(ImageFetchError) as bad:
                await fetch_image("https://cdn.example.org/vector.svg", client, check_host=False)
        return ok, bad.value

    (content, ctype), err = asyncio.run(run())
    assert content == b"\xff\xd8jpeg" and ctype == "image/jpeg"
    assert err.status == 415


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8000/api/health", "http://localhost/x.jpg", "file:///etc/passwd", "http://10.0.0.5/a.jpg"],
)
def test_image_proxy_refuses_private_and_non_http_targets(url):
    with TestClient(app) as client:
        res = client.get("/api/image", params={"url": url})
    assert res.status_code == 400
