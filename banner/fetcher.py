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
PANALUX_MARKER = "serviced by panalux"


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
    return PANALUX_MARKER in m.group(1).lower()


def fetch_panalux_candidates(
    min_count: Optional[int] = None,
    max_count: int = 9,
) -> List[Credit]:
    """
    Return up to max_count Panalux candidates in newest-first order.

    We return more than strictly needed so the compositor has fallback
    options if any individual poster URL fails to download — that way a
    single broken poster on Panavision's CDN won't break the whole run.

    Raises FetcherError if fewer than min_count candidates are found, in
    which case the cache layer keeps serving last-good.
    """
    if min_count is None:
        min_count = config.NUM_CREDITS

    all_credits = parse_all_cards(fetch_html())
    log.info("Scanning %d listing cards for Panalux credits", len(all_credits))

    candidates: List[Credit] = []
    for credit in all_credits:
        if is_panalux_credit(credit.detail_url):
            log.info("Panalux candidate: %s", credit.title)
            candidates.append(credit)
            if len(candidates) >= max_count:
                break

    if len(candidates) < min_count:
        raise FetcherError(
            f"Only found {len(candidates)} Panalux candidates in {len(all_credits)} "
            f"listing cards — need at least {min_count}. Either Panalux's recent "
            f"share has dropped or the og:description format has changed."
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
