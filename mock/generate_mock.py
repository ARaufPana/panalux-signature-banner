"""
Standalone design mock generator.

Pulls 3 real Panalux posters from panavision.com and composes a 600x150
email-signature banner (rendered at 2x = 1200x300 for retina).

No Flask, no scheduler — this exists purely so the design can be reviewed
before the full app is wired up.
"""

from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# Banner dimensions
DISPLAY_W, DISPLAY_H = 600, 150
SCALE = 2  # render at 2x for retina
W, H = DISPLAY_W * SCALE, DISPLAY_H * SCALE  # 1200 x 300

# Brand zone split — left half is brand/copy, right half is posters
SPLIT_X = W // 2  # 600

# Poster source aspect ratio (350x525 = 2:3)
POSTER_RATIO = 350 / 525

# Brand colors (from existing 2025 Panalux signature)
COLOR_BG = "white"
COLOR_POSTER_ZONE = "#000000"
COLOR_HEADLINE = "#000000"
COLOR_BODY = "#1A1A1A"
COLOR_META = "#7B7C7E"  # existing signature grey

# Sample posters — first 3 from live panavision.com/highlights/credits?divisions=_panalux
# These are for design mock only; the live app will scrape these from the page.
SAMPLE_POSTERS = [
    (
        "The Punisher: One Last Kill",
        "https://www.panavision.com/images/default-source/credits/credit_poster_the_punisher_one_last_kill-350x525-8110fa5.jpg?sfvrsn=3c1eda49_1",
    ),
    (
        "Remarkably Bright Creatures",
        "https://www.panavision.com/images/default-source/credits/credit_poster_remarkably-bright-creatures-350x525-8110fa5.jpg?sfvrsn=94757ac4_1",
    ),
    (
        "Mortal Kombat 2",
        "https://www.panavision.com/images/default-source/credits/credit_poster_mortal_kombat_ii-350x525-8110fa5.jpg?sfvrsn=4f795886_1",
    ),
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = PROJECT_ROOT / "assets" / "Panalux_Logo_2021_white.png"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size * SCALE)


def fetch_poster(url: str) -> Image.Image:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content)).convert("RGB")


def compose() -> Image.Image:
    img = Image.new("RGB", (W, H), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # Right half = black poster zone
    draw.rectangle([SPLIT_X, 0, W, H], fill=COLOR_POSTER_ZONE)

    # ---- Posters (right half) ----
    pad_tb = 10 * SCALE  # 10px top/bottom
    poster_h = H - pad_tb * 2  # 280
    poster_w = int(poster_h * POSTER_RATIO)  # ~186
    gap = 10 * SCALE  # 10px display gap
    right_zone_w = W - SPLIT_X
    total_w = 3 * poster_w + 2 * gap
    x_start = SPLIT_X + (right_zone_w - total_w) // 2
    y_start = (H - poster_h) // 2

    for i, (_title, url) in enumerate(SAMPLE_POSTERS):
        poster = fetch_poster(url).resize((poster_w, poster_h), Image.LANCZOS)
        x = x_start + i * (poster_w + gap)
        img.paste(poster, (x, y_start))

    # ---- Brand zone (left half) ----
    pad_left = 28 * SCALE  # 28px display

    # 2025 Panalux logo with red frame
    logo_path = PROJECT_ROOT / "assets" / "Panalux_Logo_2025_colour.png"
    logo = Image.open(logo_path).convert("RGBA")
    target_logo_h = 50 * SCALE  # 50px display tall
    ratio = target_logo_h / logo.height
    logo = logo.resize((int(logo.width * ratio), target_logo_h), Image.LANCZOS)
    logo_y = 18 * SCALE
    img.paste(logo, (pad_left, logo_y), logo)

    # Headline + subtitle
    font_headline = load_font("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 20)
    font_subtitle = load_font("/System/Library/Fonts/Supplemental/Arial.ttf", 13)

    headline_y = logo_y + logo.height + 14 * SCALE
    draw.text(
        (pad_left, headline_y),
        "LATEST CREDITS",
        font=font_headline,
        fill=COLOR_HEADLINE,
    )

    # Red accent bar under headline (echoes 2025 logo frame)
    accent_y = headline_y + 26 * SCALE
    draw.rectangle(
        [pad_left, accent_y, pad_left + 32 * SCALE, accent_y + 3 * SCALE],
        fill="#D7282F",  # Panalux red, eyeballed from 2025 logo
    )

    subtitle_y = accent_y + 9 * SCALE
    draw.text(
        (pad_left, subtitle_y),
        "Serviced by Panalux",
        font=font_subtitle,
        fill=COLOR_META,
    )

    return img


def main():
    print("Fetching posters and composing banner...")
    banner_2x = compose()

    out_2x = OUTPUT_DIR / "mock-v1-2x.png"
    banner_2x.save(out_2x, "PNG", optimize=True)
    print(f"  -> {out_2x} ({banner_2x.size[0]}x{banner_2x.size[1]})")

    banner_1x = banner_2x.resize((DISPLAY_W, DISPLAY_H), Image.LANCZOS)
    out_1x = OUTPUT_DIR / "mock-v1.png"
    banner_1x.save(out_1x, "PNG", optimize=True)
    print(f"  -> {out_1x} ({banner_1x.size[0]}x{banner_1x.size[1]})")


if __name__ == "__main__":
    main()
