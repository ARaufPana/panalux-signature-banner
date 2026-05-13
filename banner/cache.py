"""
On-disk cache with last-good fallback.

Two files in CACHE_DIR:
  - panalux-latest.png     -> the most recent successful render
  - panalux-last-good.png  -> redundant copy kept around as fallback,
                              promoted iff the latest render succeeds

If a regeneration cycle fails, latest stays untouched. If the cache is
empty (e.g. first run after a fresh deploy), regenerate_now() must
succeed at least once before the endpoint can serve a banner.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from . import compositor, config, fetcher

log = logging.getLogger(__name__)

# Sensible bounds for a valid Panalux banner. PNG with transparency +
# 3 photographic posters tends to land around 250–600 KB; we allow a
# wider range to catch obviously corrupt output without being precious.
MIN_VALID_BYTES = 50_000
MAX_VALID_BYTES = 2_000_000


class ValidationError(RuntimeError):
    """Raised when a freshly rendered banner fails sanity checks."""


def _validate_rendered(path: Path) -> None:
    """Open the new banner and check it's a sane Panalux JPEG. Raises on bad output."""
    size = path.stat().st_size
    if not (MIN_VALID_BYTES <= size <= MAX_VALID_BYTES):
        raise ValidationError(
            f"Rendered banner size {size} bytes is outside expected "
            f"range [{MIN_VALID_BYTES}, {MAX_VALID_BYTES}]"
        )
    try:
        with Image.open(path) as im:
            im.verify()  # detects truncated / corrupt JPEG
        with Image.open(path) as im:
            if im.size != (config.W, config.H):
                raise ValidationError(
                    f"Rendered banner has wrong dimensions {im.size}, "
                    f"expected {(config.W, config.H)}"
                )
            if im.format != "PNG":
                raise ValidationError(f"Rendered banner is {im.format}, expected PNG")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError(f"Rendered banner won't open: {exc}") from exc


def cached_path() -> Path:
    return config.CACHE_DIR / config.LIVE_BANNER_NAME


def last_good_path() -> Path:
    return config.CACHE_DIR / config.LAST_GOOD_NAME


def regenerate_now() -> Optional[Path]:
    """
    Fetch candidates + render + validate + atomically promote.

    Guarantees the cached banner is only replaced when:
      1. We can fetch a list of Panalux candidates
      2. The compositor produces a complete JPEG using working posters
      3. The new JPEG passes sanity validation (dimensions, format, size)

    Returns the cache path on success, or None on any failure. On failure,
    cached_path() and last_good_path() are left exactly as they were.
    """
    try:
        candidates = fetcher.fetch_panalux_candidates()
    except Exception:
        log.exception("Fetcher failed; keeping last-good cached banner")
        return None

    tmp_path: Optional[Path] = None
    try:
        # Render into a temp file, validate, THEN atomically rename. This
        # way the existing cached file is never replaced by a broken or
        # partial render.
        with tempfile.NamedTemporaryFile(
            dir=str(config.CACHE_DIR),
            prefix=".tmp-banner-",
            suffix=".png",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)

        compositor.render_to_file(candidates, tmp_path)
        _validate_rendered(tmp_path)

        tmp_path.replace(cached_path())
        shutil.copy2(cached_path(), last_good_path())

        log.info("Banner regenerated successfully at %s", cached_path())
        return cached_path()

    except Exception:
        log.exception("Render/validation failed; keeping last-good cached banner")
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
        return None


def serve_path() -> Optional[Path]:
    """Return the path that should be served, with last-good fallback."""
    if cached_path().exists():
        return cached_path()
    if last_good_path().exists():
        return last_good_path()
    return None
