"""Composes the email-signature banner PNG from a list of credits.

Layout: "Proudly Supporting" caption centered at the top, 3 posters
centered in a row below. Background is fully transparent so the banner
adapts to the email client's light/dark mode (the text colour is a
neutral grey that's legible on both).
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

from . import config
from .fetcher import Credit

log = logging.getLogger(__name__)


class CompositorError(RuntimeError):
    """Raised when not enough posters can be downloaded to render the banner."""


POSTER_RATIO = 350 / 525  # 2:3

# Neutral grey that reads on both white and dark backgrounds — matches
# the existing Panalux 2025 signature text colour exactly.
COLOR_TEXT = (123, 124, 126, 255)  # #7B7C7E with full alpha
COLOR_ACCENT = (215, 40, 47, 255)  # #D7282F Panalux red

# Font paths — try real Arial first (macOS native + Microsoft Core Fonts
# package on Linux), then Liberation Sans (metric-compatible) as fallback.
FONT_BOLD_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",                # macOS
    "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",           # Ubuntu w/ ttf-mscorefonts-installer
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",     # Ubuntu metric-compatible fallback
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_REGULAR_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _resolve_font(candidates: List[str]) -> str:
    for p in candidates:
        if Path(p).exists():
            return p
    raise FileNotFoundError(
        f"None of the candidate font paths exist on this system: {candidates}"
    )


def _load_font(candidates: List[str], display_size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_resolve_font(candidates), display_size * config.SCALE)


def _fetch_poster(url: str) -> Image.Image:
    resp = requests.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content)).convert("RGB")


def _download_posters_resilient(
    candidates: List[Credit], needed: int = 3
) -> Tuple[List[Image.Image], List[Credit]]:
    posters: List[Image.Image] = []
    used: List[Credit] = []
    for c in candidates:
        try:
            poster = _fetch_poster(c.poster_url)
        except Exception as exc:
            log.warning("Poster download failed for %s (%s) — skipping", c.title, exc)
            continue
        posters.append(poster)
        used.append(c)
        if len(posters) >= needed:
            break

    if len(posters) < needed:
        raise CompositorError(
            f"Only {len(posters)}/{needed} posters downloaded successfully "
            f"from {len(candidates)} candidates"
        )
    return posters, used


def compose(credits: List[Credit]) -> Image.Image:
    """
    Compose the banner with a fully transparent background.

    Layout (display dimensions, 320 × 130 — matches the 320px signature):
      ├── 12px top padding
      ├── "PROUDLY SUPPORTING" — Arial Bold, left-aligned at x=14, #7B7C7E
      ├── 4px gap
      ├── 22px red accent bar (#D7282F, 2px tall, x=14)
      ├── 10px gap
      ├── 5 posters in a row, each 52×78px display, edge-to-edge with 8px gaps
      └── 8px bottom padding
    """
    needed = config.NUM_CREDITS
    if len(credits) < needed:
        raise ValueError(
            f"compose() needs at least {needed} candidates, got {len(credits)}"
        )

    W, H = config.W, config.H
    SCALE = config.SCALE

    # Fully transparent RGBA canvas
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # --- "PROUDLY SUPPORTING" left-aligned with padding ---
    font_supporting = _load_font(FONT_BOLD_CANDIDATES, 12)
    text = "PROUDLY SUPPORTING"
    text_x = 14 * SCALE  # align with poster row's left edge
    text_y_display = 12
    text_y = text_y_display * SCALE
    draw.text((text_x, text_y), text, font=font_supporting, fill=COLOR_TEXT)

    # Measure the rendered text so the accent bar sits cleanly under it
    bbox = draw.textbbox((text_x, text_y), text, font=font_supporting)
    text_bottom = bbox[3]

    # --- Red accent bar under the text (matches original "LATEST CREDITS" treatment) ---
    accent_gap = 4 * SCALE
    accent_y = text_bottom + accent_gap
    accent_w = 22 * SCALE
    accent_h = 2 * SCALE
    draw.rectangle(
        [text_x, accent_y, text_x + accent_w, accent_y + accent_h],
        fill=COLOR_ACCENT,
    )
    accent_bottom = accent_y + accent_h

    # --- Posters in a row below, edge-to-edge ---
    posters, used = _download_posters_resilient(credits, needed=needed)
    log.info("Banner credits: %s", [c.title for c in used])

    # Edge-to-edge: zero side padding, 5px gap between posters.
    #   5 * poster_w + 4 * gap = 320  →  poster_w = 60, poster_h = 90 (2:3)
    side_pad = 0
    gap = 5 * SCALE
    poster_w = (W - 4 * gap) // 5
    poster_h = int(poster_w / POSTER_RATIO)

    gap_above_posters = 10 * SCALE
    y_start = accent_bottom + gap_above_posters
    x_start = side_pad

    for i, poster in enumerate(posters):
        poster = poster.resize((poster_w, poster_h), Image.LANCZOS)
        x = x_start + i * (poster_w + gap)
        img.paste(poster, (x, y_start))

    return img


def render_to_bytes(credits: List[Credit]) -> bytes:
    img = compose(credits)
    buf = BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def render_to_file(credits: List[Credit], path: Path) -> Path:
    img = compose(credits)
    img.save(path, "PNG", optimize=True)
    return path
