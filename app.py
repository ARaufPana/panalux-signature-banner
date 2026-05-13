"""
Flask entrypoint for the Panalux signature banner service.

Endpoints:
  GET /signature/panalux-latest.jpg  -> the banner (served from on-disk cache)
  GET /healthz                       -> JSON status
  POST /admin/regenerate             -> force a regeneration (token-gated)

Boot behavior:
  1. If cache is empty, run regenerate_now() synchronously so /signature/...
     can serve immediately.
  2. Start background scheduler for daily regeneration at 03:00 UTC.

Caching:
  Banner is served with Cache-Control: public, max-age=3600 so intermediate
  caches refresh hourly. Gmail's image proxy will cache longer (~24-48h) —
  that's acceptable since Panalux credits update slowly.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file

from banner import cache, config, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def _cache_age_seconds(path: Path) -> int:
    return int(datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)


def create_app() -> Flask:
    app = Flask(__name__)

    # Warm the cache on boot so the endpoint never serves 404 on first hit.
    if not cache.cached_path().exists():
        log.info("Cache empty on boot — running initial regeneration")
        cache.regenerate_now()

    # Daily scheduler (won't double-start on flask --debug reloader).
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        scheduler.start_scheduler()

    admin_token = os.environ.get("ADMIN_TOKEN")

    @app.route("/signature/panalux-latest.png")
    def banner():
        path = cache.serve_path()
        if path is None:
            log.error("No cached banner available (cold start failed?)")
            abort(503, "Banner not yet available")

        resp = send_file(path, mimetype=config.BANNER_MIME, max_age=3600)
        resp.headers["Cache-Control"] = "public, max-age=3600"
        return resp

    @app.route("/healthz")
    def healthz():
        path = cache.cached_path()
        if not path.exists():
            return jsonify(status="degraded", reason="no cached banner"), 503
        age = _cache_age_seconds(path)
        return jsonify(
            status="ok",
            cached_banner=path.name,
            cached_size_bytes=path.stat().st_size,
            cached_age_seconds=age,
            cached_age_hours=round(age / 3600, 1),
            stale=age > 60 * 60 * 36,  # >36h is stale (scheduler should run every 24h)
        )

    @app.route("/admin/regenerate", methods=["POST"])
    def admin_regenerate():
        if not admin_token:
            abort(503, "ADMIN_TOKEN not configured")
        if request.headers.get("X-Admin-Token") != admin_token:
            abort(403)
        path = cache.regenerate_now()
        if path is None:
            return jsonify(status="failed"), 500
        return jsonify(status="ok", path=str(path), size=path.stat().st_size)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
