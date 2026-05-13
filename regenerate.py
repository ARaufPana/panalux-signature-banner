"""
Standalone CLI: regenerate the cached banner once and exit.

Useful for:
  - Triggering regeneration from an external cron job (preferred over the
    in-process APScheduler if you're running on a host where the Flask app
    might not stay alive 24/7)
  - Smoke-testing the pipeline after deployment
"""

import logging
import sys

from banner import cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> int:
    path = cache.regenerate_now()
    if path is None:
        print("FAILED — see logs above", file=sys.stderr)
        return 1
    size_kb = path.stat().st_size / 1024
    print(f"OK -> {path} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
