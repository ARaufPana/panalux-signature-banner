"""
Scrape the credits page on panavision.com and filter to Panalux-serviced
titles.

The listing page renders 26 latest credits but the `?divisions=_panalux`
query string is applied client-side via JS — the initial HTML always
returns the full unfiltered list. To identify which credits are Panalux,
we visit each detail page and read the og:description meta tag, which
follows the format:

    <meta property="og:description" content="<Title> (YYYY), serviced by <Division>." />

We walk the listing in DOM order (newest-first) and keep the first N that
are serviced by Panalux.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import config

log = logging.getLogger(__name__)

OG_DESCRIPTION_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']og:description["\']\s+content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
# A credit counts as Panalux if "Panalux" appears anywhere in the
# "serviced by ..." clause — not just immediately after "serviced by".
# Joint credits list both divisions in either order ("serviced by Panalux
# & Panavision" OR "serviced by Panavision & Panalux"), so a plain substring
# check on "serviced by panalux" silently dropped Panavision-first joints.
# Anchoring on "serviced by" (rather than matching "panalux" anywhere) avoids
# false positives from a title that happened to contain the word.
PANALUX_MARKER_RE = re.compile(r"serviced by\b.*\bpanalux\b", re.IGNORECASE)


@dataclass
class Credit:
    title: str
    detail_url: str
    poster_url: str


class FetcherError(RuntimeError):
    """Raised when the credits page can't be parsed."""


def fetch_html(url: Optional[str] = None) -> str:
    target = url or config.SOURCE_URL
    resp = requests.get(
        target,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.text


def parse_all_cards(html: str) -> List[Credit]:
    """Parse every credit card from the listing page HTML (no filtering)."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.credit-grid li")
    if not cards:
        raise FetcherError("No credit cards found — page structure may have changed")

    out: List[Credit] = []
    for card in cards:
        link = card.find("a", href=True)
        img = card.find("img")
        if not link or not img:
            continue

        title_el = card.select_one(".credit-grid-content h2")
        title = (title_el.get_text(strip=True) if title_el else
                 (img.get("alt") or "").removesuffix(" poster").strip())
        if not title:
            continue

        detail_url = urljoin(config.SOURCE_URL, link["href"])
        poster_src = img.get("src") or img.get("data-src")
        if not poster_src:
            continue
        poster_url = urljoin(config.SOURCE_URL, poster_src)

        out.append(Credit(title=title, detail_url=detail_url, poster_url=poster_url))
    return out


def is_panalux_credit(detail_url: str) -> bool:
    """Visit a credit's detail page and read og:description to check division."""
    try:
        resp = requests.get(
            detail_url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Detail-page fetch failed for %s: %s", detail_url, exc)
        return False

    m = OG_DESCRIPTION_RE.search(resp.text)
    if not m:
        return False
    return bool(PANALUX_MARKER_RE.search(m.group(1)))


LISTING_BASE_URL = "https://www.panavision.com/highlights/credits"


def _page_url(page: int) -> str:
    """Build the listing URL for a given page number (page 1 has no query)."""
    if page <= 1:
        return LISTING_BASE_URL
    return f"{LISTING_BASE_URL}?page={page}"


def fetch_panalux_candidates(
    min_count: Optional[int] = None,
    max_count: int = 12,
    max_pages: int = 5,
) -> List[Credit]:
    """
    Walk the credits listing across multiple pages and return Panalux
    candidates in newest-first order.

    The site renders ~16-26 cards per listing page; `?page=N` requests
    older pages. We stop as soon as we have `max_count` candidates or
    we've walked `max_pages` pages, whichever comes first.

    Raises FetcherError if fewer than `min_count` candidates are found,
    in which case the cache layer keeps serving last-good.
    """
    if min_count is None:
        min_count = config.NUM_CREDITS

    candidates: List[Credit] = []
    seen_urls = set()
    cards_scanned = 0

    for page in range(1, max_pages + 1):
        if len(candidates) >= max_count:
            break
        try:
            html = fetch_html(_page_url(page))
        except requests.RequestException as exc:
            log.warning("Page %d fetch failed (%s) — stopping pagination", page, exc)
            break

        page_cards = parse_all_cards(html)
        log.info("Page %d: %d listing cards", page, len(page_cards))

        for credit in page_cards:
            if credit.detail_url in seen_urls:
                continue
            seen_urls.add(credit.detail_url)
            cards_scanned += 1

            if is_panalux_credit(credit.detail_url):
                log.info("Panalux candidate: %s (page %d)", credit.title, page)
                candidates.append(credit)
                if len(candidates) >= max_count:
                    break

    if len(candidates) < min_count:
        raise FetcherError(
            f"Only found {len(candidates)} Panalux candidates across "
            f"{cards_scanned} cards in {max_pages} pages — need at least {min_count}."
        )

    log.info("Returning %d Panalux candidates", len(candidates))
    return candidates


# Backwards-compat alias for callers that expected the old name.
def fetch_latest_credits(limit: Optional[int] = None) -> List[Credit]:
    return fetch_panalux_candidates(min_count=limit)


if __name__ == "__main__":
    for c in fetch_latest_credits():
        print(f"- {c.title}")
        print(f"    {c.detail_url}")
        print(f"    {c.poster_url}")
