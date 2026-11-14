"""Listing photos: pick real property photos out of a scraped page, and proxy them to the UI.

Collection (no LLM call, deterministic):
  1. the page's `og:image` (portals set it to the listing's main photo),
  2. every image Firecrawl reports on the page (`formats=["images"]`),
  3. images embedded in the markdown (`![alt](url)`),
then drop logos / icons / maps / tracking pixels and size variants of the same photo.

The proxy (`fetch_image`) exists because portals often block hot-linking from other sites. It
only fetches public http(s) addresses (no private / loopback / link-local IPs, re-checked on
every redirect), only returns raster images, and caps the size.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections import OrderedDict
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import httpx

MAX_PHOTOS = 8

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)")
# A results-page card: [![alt](thumb) ...](listing-url)
_MD_LINKED_IMAGE_RE = re.compile(r"\[!\[[^\]]*\]\((https?://[^)\s]+)\)[^\]]*\]\((https?://[^)\s]+)\)")

_NOT_A_PHOTO = re.compile(
    r"logo|icon|sprite|favicon|avatar|badge|placeholder|banner|flag|pixel|tracking|blank|"
    r"spacer|loader|loading|emoji|captcha|staticmap|maps\.google|maps\.googleapis|/maps/|"
    r"googletagmanager|doubleclick|facebook\.com/tr|/ads?/|advert|qr[-_]?code|watermark|"
    r"app[-_]?store|google[-_]?play|social|share",
    re.IGNORECASE,
)
_BAD_EXTENSIONS = (".svg", ".gif", ".ico", ".bmp", ".tif", ".tiff")
# Size variants of one photo differ only by these path parts or query params.
_SIZE_TOKEN = re.compile(r"(?:^|[/_\-.])(?:w|h|s|size|width|height|thumb|thumbnail|small|medium|large|"
                         r"\d{2,4}x\d{2,4}|full|original)(?=[/_\-.]|$)", re.IGNORECASE)


def _is_photo_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    path = parsed.path.lower()
    if path.endswith(_BAD_EXTENSIONS) or url.startswith("data:"):
        return False
    return not _NOT_A_PHOTO.search(url)


def _photo_key(url: str) -> str:
    """Identity of a photo regardless of the size variant / CDN params in its URL."""
    parsed = urlparse(url)
    stem = parsed.path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    stem = re.sub(r"[_\-](?:\d{2,4}x\d{2,4}|w\d{2,4}|h\d{2,4}|thumb|small|medium|large|xl|lg|sm)$", "", stem)
    if len(stem) >= 6:
        return stem
    return _SIZE_TOKEN.sub("", parsed.path.lower())


def listing_photos(
    page_url: str,
    markdown: str = "",
    og_image: Optional[str] = None,
    images: Optional[Iterable[str]] = None,
    limit: int = MAX_PHOTOS,
) -> list[str]:
    """The listing's photos, main photo first, de-duplicated, at most `limit`."""
    candidates: list[str] = []
    if og_image:
        candidates.append(og_image)
    candidates.extend(images or [])
    candidates.extend(_MD_IMAGE_RE.findall(markdown or ""))

    seen: set[str] = set()
    photos: list[str] = []
    for raw in candidates:
        if not isinstance(raw, str) or not raw.strip():
            continue
        url = urljoin(page_url, raw.strip())
        if url.startswith("//"):
            url = "https:" + url
        if not _is_photo_url(url):
            continue
        key = _photo_key(url)
        if key in seen:
            continue
        seen.add(key)
        photos.append(url)
        if len(photos) >= limit:
            break
    return photos


def card_thumbnails(markdown: str) -> dict[str, str]:
    """{listing url: thumbnail} from a search-results page, where cards link an image."""
    thumbs: dict[str, str] = {}
    for image, link in _MD_LINKED_IMAGE_RE.findall(markdown or ""):
        if _is_photo_url(image):
            thumbs.setdefault(link.split("#")[0], image)
    return thumbs


# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp", "image/avif", "image/gif")
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


class ImageFetchError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def _assert_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImageFetchError(400, "Only http(s) image URLs are allowed")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ImageFetchError(400, "Unknown image host") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise ImageFetchError(400, "Image host is not public")


class _Cache:
    """Tiny in-memory LRU so re-renders don't re-download the same photos."""

    def __init__(self, size: int = 96) -> None:
        self.size = size
        self.items: OrderedDict[str, tuple[bytes, str]] = OrderedDict()

    def get(self, key: str) -> Optional[tuple[bytes, str]]:
        hit = self.items.get(key)
        if hit:
            self.items.move_to_end(key)
        return hit

    def put(self, key: str, value: tuple[bytes, str]) -> None:
        self.items[key] = value
        self.items.move_to_end(key)
        while len(self.items) > self.size:
            self.items.popitem(last=False)


_cache = _Cache()


async def fetch_image(
    url: str, client: Optional[httpx.AsyncClient] = None, check_host: bool = True
) -> tuple[bytes, str]:
    """Downloads a public image. Returns (bytes, content type) or raises ImageFetchError."""
    cached = _cache.get(url)
    if cached:
        return cached
    owns = client is None
    http = client or httpx.AsyncClient(timeout=12.0)
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if check_host:
                await _assert_public(current)
            parsed = urlparse(current)
            headers = {
                "User-Agent": BROWSER_UA,
                "Accept": "image/avif,image/webp,image/jpeg,image/png,image/*;q=0.8",
                # Same-site referer: what the portal's own pages send.
                "Referer": f"{parsed.scheme}://{parsed.netloc}/",
            }
            async with http.stream("GET", current, headers=headers, follow_redirects=False) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    current = urljoin(current, resp.headers["location"])
                    continue
                if resp.status_code != 200:
                    raise ImageFetchError(502, f"Image host answered {resp.status_code}")
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype not in ALLOWED_TYPES:
                    raise ImageFetchError(415, "Not a supported image")
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise ImageFetchError(413, "Image too large")
                    chunks.append(chunk)
                result = (b"".join(chunks), ctype)
                _cache.put(url, result)
                return result
        raise ImageFetchError(502, "Too many redirects")
    except httpx.HTTPError as exc:
        raise ImageFetchError(502, f"Could not download the image ({exc.__class__.__name__})") from exc
    finally:
        if owns:
            await http.aclose()
