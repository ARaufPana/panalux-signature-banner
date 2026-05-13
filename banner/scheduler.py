"""APScheduler config — runs cache.regenerate_now() on a daily cron."""

import logging
from apscheduler.schedulers.background import BackgroundScheduler

from . import cache

log = logging.getLogger(__name__)


def start_scheduler() -> BackgroundScheduler:
    """Kick off a daily 03:00 UTC regeneration."""
    scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    scheduler.add_job(
        cache.regenerate_now,
        trigger="cron",
        hour=3,
        minute=0,
        id="regenerate_banner",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info("Scheduler started (daily regeneration at 03:00 UTC)")
    return scheduler
