"""Project-wide constants and paths."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUT_DIR = PROJECT_ROOT / "output"

CACHE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

SOURCE_URL = "https://www.panavision.com/highlights/credits?divisions=_panalux"
CLICK_THROUGH_URL = "https://www.panavision.com/highlights/credits?divisions=_panalux"

# Banner dimensions — matches the 320px-wide email signature table
DISPLAY_W, DISPLAY_H = 320, 115
SCALE = 2
W, H = DISPLAY_W * SCALE, DISPLAY_H * SCALE

# Fetcher
NUM_CREDITS = 5
HTTP_TIMEOUT = 15
USER_AGENT = "PanaluxSignatureBanner/1.0 (+aaron.rauf@panavision.co.uk)"

# Cache
LIVE_BANNER_NAME = "panalux-latest.png"
LAST_GOOD_NAME = "panalux-last-good.png"
BANNER_MIME = "image/png"
