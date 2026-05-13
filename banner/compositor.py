"""Composes the email-signature banner PNG from a list of credits."""

import logging
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

from . import config
from .fetcher import Credit

log = logging.getLogger(__name__)


class CompositorError(RuntimeError):
    """Raised when not enough posters can be downloaded to render the banner."""

POSTER_RATIO = 350 / 525  # 2:3

COLOR_BG = "white"
COLOR_POSTER_ZONE = "#000000"
COLOR_HEADLINE = "#000000"
COLOR_META = "#7B7C7E"
COLOR_ACCENT = "#D7282F"  # Panalux red

FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"


def _load_font(path: str, display_size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, display_size * config.SCALE)


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
    """
    Try each candidate in order; collect the first `needed` whose posters
    download successfully. Returns (posters, used_credits). Raises
    CompositorError if fewer than `needed` posters are usable.
    """
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
    Compose the banner. Accepts a list of candidate credits; uses the
    first 3 whose posters successfully download.
    """
    if len(credits) < 3:
        raise ValueError(f"compose() needs at least 3 candidates, got {len(credits)}")

    W, H = config.W, config.H
    SCALE = config.SCALE
    SPLIT_X = W // 2

    img = Image.new("RGB", (W, H), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # Right half: black poster zone
    draw.rectangle([SPLIT_X, 0, W, H], fill=COLOR_POSTER_ZONE)

    posters, used = _download_posters_resilient(credits, needed=3)
    log.info("Banner credits: %s", [c.title for c in used])

    # Posters
    pad_tb = 10 * SCALE
    poster_h = H - pad_tb * 2
    poster_w = int(poster_h * POSTER_RATIO)
    gap = 10 * SCALE
    right_zone_w = W - SPLIT_X
    total_w = 3 * poster_w + 2 * gap
    x_start = SPLIT_X + (right_zone_w - total_w) // 2
    y_start = (H - poster_h) // 2

    for i, poster in enumerate(posters):
        poster = poster.resize((poster_w, poster_h), Image.LANCZOS)
        x = x_start + i * (poster_w + gap)
        img.paste(poster, (x, y_start))

    # Brand zone
    pad_left = 28 * SCALE
    logo = Image.open(config.ASSETS_DIR / "Panalux_Logo_2025_colour.png").convert("RGBA")
    target_logo_h = 50 * SCALE
    ratio = target_logo_h / logo.height
    logo = logo.resize((int(logo.width * ratio), target_logo_h), Image.LANCZOS)
    logo_y = 18 * SCALE
    img.paste(logo, (pad_left, logo_y), logo)

    font_headline = _load_font(FONT_BOLD, 20)
    font_subtitle = _load_font(FONT_REGULAR, 13)

    headline_y = logo_y + logo.height + 14 * SCALE
    draw.text((pad_left, headline_y), "LATEST CREDITS", font=font_headline, fill=COLOR_HEADLINE)

    accent_y = headline_y + 26 * SCALE
    draw.rectangle(
        [pad_left, accent_y, pad_left + 32 * SCALE, accent_y + 3 * SCALE],
        fill=COLOR_ACCENT,
    )

    subtitle_y = accent_y + 9 * SCALE
    draw.text((pad_left, subtitle_y), "Serviced by Panalux", font=font_subtitle, fill=COLOR_META)

    return img


JPEG_QUALITY = 92


def render_to_bytes(credits: List[Credit]) -> bytes:
    img = compose(credits)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buf.getvalue()


def render_to_file(credits: List[Credit], path: Path) -> Path:
    img = compose(credits)
    img.save(path, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return path
