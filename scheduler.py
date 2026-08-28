"""
scheduler.py — Background task scheduler for ANIME BOT PRO v4.
Uses ONLY Python standard library: threading, time, datetime.
No APScheduler. No Celery. No external packages.
Python 3.9 compatible.
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

_thread = None
_running = False
_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════════
# TASK DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

def _task_process_notifications():
    """Send pending notifications from the notification queue."""
    try:
        import database as db
        import api
        from config import BROADCAST_DELAY

        notifications = db.get_pending_notifications(limit=30)
        for notif in notifications:
            try:
                result = api.send_message(
                    notif["user_id"],
                    notif["message"],
                )
                if result:
                    db.mark_notification_sent(notif["id"])
                time.sleep(BROADCAST_DELAY)
            except Exception as exc:
                logger.warning(
                    "Notification send failed (id={}): {}".format(notif["id"], exc))
                db.mark_notification_sent(notif["id"])  # mark as sent to avoid retry loops

    except Exception as exc:
        logger.error("_task_process_notifications error: {}".format(exc), exc_info=False)


def _task_cleanup_notifications():
    """Remove old sent notifications to keep DB lean."""
    try:
        import database as db
        db.cleanup_old_notifications(days=7)
        logger.debug("Old notifications cleaned up.")
    except Exception as exc:
        logger.warning("_task_cleanup_notifications error: {}".format(exc))


def _task_expire_premium():
    """
    Log expired premium users. The actual expiry is enforced
    server-side by checking premium_until < now() on every request.
    This task just logs for monitoring purposes.
    """
    try:
        import database as db
        expired = db.get_expired_premium_users()
        if expired:
            logger.info("Expired premium users detected: {}".format(len(expired)))
    except Exception as exc:
        logger.warning("_task_expire_premium error: {}".format(exc))


def _task_rate_limiter_cleanup():
    """Periodically clean up stale rate-limiter entries."""
    try:
        from utils import message_rate_limiter, callback_rate_limiter
        message_rate_limiter.cleanup()
        callback_rate_limiter.cleanup()
    except Exception as exc:
        logger.warning("_task_rate_limiter_cleanup error: {}".format(exc))


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULER LOOP
# ══════════════════════════════════════════════════════════════════════════════

class _TaskRunner:
    """Simple interval-based task runner."""

    def __init__(self, func, interval_seconds: int, name: str):
        self.func = func
        self.interval = interval_seconds
        self.name = name
        self.last_run = 0.0

    def should_run(self, now: float) -> bool:
        return (now - self.last_run) >= self.interval

    def run(self):
        self.last_run = time.time()
        try:
            self.func()
        except Exception as exc:
            logger.error("Task '{}' failed: {}".format(self.name, exc), exc_info=False)


_TASKS = [
    _TaskRunner(_task_process_notifications, interval_seconds=10,   name="process_notifications"),
    _TaskRunner(_task_expire_premium,        interval_seconds=3600,  name="expire_premium"),
    _TaskRunner(_task_cleanup_notifications, interval_seconds=86400, name="cleanup_notifications"),
    _TaskRunner(_task_rate_limiter_cleanup,  interval_seconds=300,   name="rate_limiter_cleanup"),
]


def _scheduler_loop():
    """Main scheduler loop. Runs in a background daemon thread."""
    global _running
    logger.info("Scheduler loop started.")

    while _running:
        try:
            now = time.time()
            for task in _TASKS:
                if task.should_run(now):
                    task.run()
        except Exception as exc:
            logger.error("Scheduler loop error: {}".format(exc), exc_info=False)

        # Sleep in small increments to allow clean shutdown
        for _ in range(50):
            if not _running:
                break
            time.sleep(0.2)

    logger.info("Scheduler loop stopped.")


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def start():
    """Start the background scheduler thread."""
    global _thread, _running

    with _lock:
        if _running:
            logger.warning("Scheduler already running.")
            return

        _running = True
        _thread = threading.Thread(
            target=_scheduler_loop,
            name="SchedulerThread",
            daemon=True,
        )
        _thread.start()
        logger.info("Scheduler started (daemon thread).")


def stop():
    """Signal the scheduler to stop gracefully."""
    global _running

    with _lock:
        if not _running:
            return
        _running = False
        logger.info("Scheduler stop requested.")

    if _thread and _thread.is_alive():
        _thread.join(timeout=5.0)
        logger.info("Scheduler thread joined.")
