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

# Font paths are platform-specific. Liberation Sans is metric-compatible
# with Arial — renders nearly identically.
FONT_BOLD_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_REGULAR_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
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

    Layout (display dimensions, 600 × 200):
      ├── 14px top padding
      ├── "Proudly Supporting" — Arial Bold 18pt, centered, #7B7C7E
      ├── 14px gap
      ├── 3 posters in a row, each ~130×87px, centered with 14px gaps
      └── 14px bottom padding
    """
    if len(credits) < 3:
        raise ValueError(f"compose() needs at least 3 candidates, got {len(credits)}")

    W, H = config.W, config.H
    SCALE = config.SCALE

    # Fully transparent RGBA canvas
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # --- "Proudly Supporting" text, centered horizontally near top ---
    font_supporting = _load_font(FONT_BOLD_CANDIDATES, 18)
    text = "Proudly Supporting"
    bbox = draw.textbbox((0, 0), text, font=font_supporting)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (W - text_w) // 2
    text_y_display = 14
    text_y = text_y_display * SCALE
    draw.text((text_x, text_y), text, font=font_supporting, fill=COLOR_TEXT)

    # --- Posters centered below ---
    posters, used = _download_posters_resilient(credits, needed=3)
    log.info("Banner credits: %s", [c.title for c in used])

    # Vertical layout: top pad + text + gap + posters + bottom pad
    text_block_h = text_y_display * SCALE + text_h
    gap_below_text = 14 * SCALE
    pad_bottom = 14 * SCALE

    poster_h = H - text_block_h - gap_below_text - pad_bottom
    poster_w = int(poster_h * POSTER_RATIO)
    gap = 14 * SCALE
    total_w = 3 * poster_w + 2 * gap
    x_start = (W - total_w) // 2
    y_start = text_block_h + gap_below_text

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
