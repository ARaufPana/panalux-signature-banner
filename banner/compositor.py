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

    Layout (display dimensions, 320 × 120 — matches the 320px signature):
      ├── 10px top padding
      ├── "Proudly Supporting" — Arial Bold 11pt-ish, centered, #7B7C7E
      ├── 6px gap
      ├── 5 posters in a row, each 52×78px display, centered with 8px gaps
      └── 10px bottom padding
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

    # --- "Proudly Supporting" text, centered horizontally near top ---
    # Size 11 → matches the signature's display name typographic weight
    font_supporting = _load_font(FONT_BOLD_CANDIDATES, 11)
    text = "PROUDLY SUPPORTING"
    bbox = draw.textbbox((0, 0), text, font=font_supporting)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (W - text_w) // 2
    text_y_display = 10
    text_y = text_y_display * SCALE
    draw.text((text_x, text_y), text, font=font_supporting, fill=COLOR_TEXT)

    # --- Posters centered below ---
    posters, used = _download_posters_resilient(credits, needed=needed)
    log.info("Banner credits: %s", [c.title for c in used])

    # Horizontal layout for 5 posters across 320px width:
    #   2*side_pad + 5*poster_w + 4*gap = 320  (display px)
    #   With side_pad=14 and gap=8: poster_w = (320 - 28 - 32) / 5 = 52
    side_pad = 14 * SCALE
    gap = 8 * SCALE
    poster_w = (W - 2 * side_pad - 4 * gap) // 5
    poster_h = int(poster_w / POSTER_RATIO)  # 2:3 ratio

    # Vertical positioning
    gap_below_text = 6 * SCALE
    text_block_h = text_y_display * SCALE + text_h
    y_start = text_block_h + gap_below_text
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
