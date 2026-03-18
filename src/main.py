"""
KALBI-2: Autonomous Multi-Agent Trading System -- Main Entry Point

Uses APScheduler to schedule trading crews on fixed intervals:

  - KalshiCrew   : every 15 minutes
  - EquitiesCrew : every 30 minutes (market hours 9:30 AM -- 4:00 PM ET only)
  - MetaCrew     : every 2 hours
  - Portfolio snapshot : every 5 minutes
  - Daily summary      : at 5:00 PM ET

Startup sequence:
  1. Load config from .env
  2. Initialise database (create tables if needed)
  3. Initialise Redis cache
  4. Initialise notification service
  5. Start scheduler
  6. Log startup to Telegram

Graceful shutdown on SIGINT / SIGTERM:
  1. Stop scheduler
  2. Send shutdown notification
  3. Close DB connections
"""

from __future__ import annotations

import signal
import sys
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.config import Settings
from src.data.cache import CacheService
from src.data.models import create_tables

# ---------------------------------------------------------------------------
# Structured logging setup
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger("kalbi2.main")

# ---------------------------------------------------------------------------
# Global handles (populated in main)
# ---------------------------------------------------------------------------

_scheduler: BackgroundScheduler | None = None
_engine: Engine | None = None
_settings: Settings | None = None


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------


def _send_telegram(message: str) -> None:
    """Best-effort Telegram notification.  Silently ignores failures."""
    try:
        import requests

        if not _settings or not _settings.telegram_bot_token or not _settings.telegram_chat_id:
            log.debug("telegram.skipped", reason="no credentials configured")
            return

        url = f"https://api.telegram.org/bot{_settings.telegram_bot_token}/sendMessage"
        requests.post(
            url,
            json={
                "chat_id": _settings.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        log.info("telegram.sent", message_length=len(message))
    except Exception:
        log.warning("telegram.send_failed", exc_info=True)


# ---------------------------------------------------------------------------
# Market-hours guard
# ---------------------------------------------------------------------------


def _is_us_market_open() -> bool:
    """Return True if the current time is within US equities regular hours.

    Regular session: 9:30 AM -- 4:00 PM Eastern Time.

    Uses a simplified UTC-4 (EDT) offset.  For production, swap in
    ``zoneinfo.ZoneInfo("America/New_York")``.
    """
    now_utc = datetime.now(timezone.utc)
    et_hour = (now_utc.hour - 4) % 24
    et_minute = now_utc.minute
    current_minutes = et_hour * 60 + et_minute

    market_open = 9 * 60 + 30   # 09:30 ET
    market_close = 16 * 60      # 16:00 ET

    weekday = now_utc.weekday()  # Mon=0 .. Sun=6
    if weekday >= 5:
        return False

    return market_open <= current_minutes < market_close


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------


def run_kalshi_crew() -> None:
    """Execute a full Kalshi prediction-markets scanning cycle."""
    log.info("job.kalshi_crew.start")
    try:
        # Placeholder -- wire up the actual CrewAI crew when ready.
        log.info("job.kalshi_crew.complete")
    except Exception:
        log.exception("job.kalshi_crew.failed")


def run_equities_crew() -> None:
    """Execute an equities analysis cycle (market hours only)."""
    if not _is_us_market_open():
        log.info("job.equities_crew.skipped", reason="market closed")
        return
    log.info("job.equities_crew.start")
    try:
        log.info("job.equities_crew.complete")
    except Exception:
        log.exception("job.equities_crew.failed")


def run_meta_crew() -> None:
    """Execute the meta-review crew cycle."""
    log.info("job.meta_crew.start")
    try:
        log.info("job.meta_crew.complete")
    except Exception:
        log.exception("job.meta_crew.failed")


def take_portfolio_snapshot() -> None:
    """Record a point-in-time portfolio snapshot to the database."""
    log.info("job.portfolio_snapshot.start")
    try:
        log.info("job.portfolio_snapshot.complete")
    except Exception:
        log.exception("job.portfolio_snapshot.failed")


def send_daily_summary() -> None:
    """Compile and send the end-of-day performance summary."""
    log.info("job.daily_summary.start")
    try:
        _send_telegram("*KALBI-2 Daily Summary*\n(placeholder -- full report coming soon)")
        log.info("job.daily_summary.complete")
    except Exception:
        log.exception("job.daily_summary.failed")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _init_database(settings: Settings) -> Engine:
    """Create the SQLAlchemy engine and ensure all tables exist."""
    engine = create_engine(
        settings.timescaledb_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    create_tables(engine)
    log.info("database.initialized", url=settings.timescaledb_url.split("@")[-1])
    return engine


def _init_cache(settings: Settings) -> CacheService:
    """Create and verify the Redis cache service."""
    cache = CacheService(settings.redis_url)
    log.info("cache.initialized", url=settings.redis_url)
    return cache


def _build_scheduler(settings: Settings) -> BackgroundScheduler:
    """Create the APScheduler instance and register all jobs."""
    scheduler = BackgroundScheduler(
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }
    )

    # Kalshi crew -- every N minutes (default 15)
    scheduler.add_job(
        run_kalshi_crew,
        trigger=IntervalTrigger(minutes=settings.kalshi_scan_interval_minutes),
        id="kalshi_crew",
        name="Kalshi Crew",
    )

    # Equities crew -- every N minutes (default 30), market-hours guard inside
    scheduler.add_job(
        run_equities_crew,
        trigger=IntervalTrigger(minutes=settings.equities_scan_interval_minutes),
        id="equities_crew",
        name="Equities Crew",
    )

    # Meta crew -- every N minutes (default 120)
    scheduler.add_job(
        run_meta_crew,
        trigger=IntervalTrigger(minutes=settings.meta_review_interval_minutes),
        id="meta_crew",
        name="Meta Crew",
    )

    # Portfolio snapshot -- every 5 minutes
    scheduler.add_job(
        take_portfolio_snapshot,
        trigger=IntervalTrigger(minutes=5),
        id="portfolio_snapshot",
        name="Portfolio Snapshot",
    )

    # Daily summary -- 5:00 PM ET (21:00 UTC during EDT)
    scheduler.add_job(
        send_daily_summary,
        trigger=CronTrigger(hour=21, minute=0, timezone="UTC"),
        id="daily_summary",
        name="Daily Summary",
    )

    return scheduler


def _shutdown(signum: int | None = None, frame=None) -> None:
    """Graceful shutdown handler for SIGINT / SIGTERM."""
    sig_name = signal.Signals(signum).name if signum else "manual"
    log.info("shutdown.initiated", signal=sig_name)

    # 1. Stop the scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler.stopped")

    # 2. Send shutdown notification
    _send_telegram(f"KALBI-2 shutting down ({sig_name})")

    # 3. Close database connections
    if _engine:
        _engine.dispose()
        log.info("database.connections_closed")

    log.info("shutdown.complete")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the KALBI-2 trading system."""
    global _scheduler, _engine, _settings

    log.info("startup.begin", version="0.1.0")

    # 1. Load configuration
    _settings = Settings()
    log.info(
        "config.loaded",
        paper_mode=_settings.paper_trading_mode,
        kalshi_interval=_settings.kalshi_scan_interval_minutes,
        equities_interval=_settings.equities_scan_interval_minutes,
        meta_interval=_settings.meta_review_interval_minutes,
    )

    # 2. Initialise database
    _engine = _init_database(_settings)

    # 3. Initialise Redis cache
    _cache = _init_cache(_settings)

    # 4. Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 5. Build and start the scheduler
    _scheduler = _build_scheduler(_settings)
    _scheduler.start()
    log.info(
        "scheduler.started",
        jobs=[job.name for job in _scheduler.get_jobs()],
    )

    # 6. Startup notification
    mode = "PAPER" if _settings.paper_trading_mode else "LIVE"
    _send_telegram(f"KALBI-2 started in *{mode}* mode")

    log.info("startup.complete", mode=mode)

    # Block the main thread until a signal arrives.
    try:
        while True:
            signal.pause()
    except AttributeError:
        # signal.pause() is not available on Windows; use a fallback.
        import time

        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
