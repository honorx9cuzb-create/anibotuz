"""
bot.py — Entry point for ANIME BOT PRO v4.
Long-polling loop using ONLY Python standard library.
Run with: python bot.py
"""

import logging
import sys
import time
import os

# ── Setup logging FIRST before importing anything else ────────────────────────
from config import LOG_PATH, LOG_LEVEL

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# ── Import after logging is ready ─────────────────────────────────────────────
import database as db
import api
import handlers
import scheduler as sched
from config import POLLING_TIMEOUT, RETRY_DELAY, BOT_USERNAME


def polling_loop():
    """Main long-polling loop. Runs forever until KeyboardInterrupt."""
    offset = None
    consecutive_errors = 0
    max_consecutive_errors = 10

    logger.info("Polling boshlandi...")

    while True:
        try:
            updates = api.get_updates(
                offset=offset,
                timeout=POLLING_TIMEOUT,
                allowed_updates=["message", "callback_query"],
            )

            consecutive_errors = 0  # reset on success

            for update in updates:
                update_id = update.get("update_id")
                if update_id is None:
                    continue

                offset = update_id + 1

                try:
                    handlers.handle_update(update)
                except Exception as exc:
                    logger.error(
                        "handle_update xatosi (update_id={}): {}".format(update_id, exc),
                        exc_info=True,
                    )

        except KeyboardInterrupt:
            logger.info("Bot to'xtatildi (KeyboardInterrupt).")
            print("\n👋  Bot to'xtatildi.")
            sys.exit(0)

        except Exception as exc:
            consecutive_errors += 1
            logger.error(
                "Polling xatosi ({}/{}): {}".format(
                    consecutive_errors, max_consecutive_errors, exc),
                exc_info=False,
            )

            if consecutive_errors >= max_consecutive_errors:
                wait = RETRY_DELAY * 5
                logger.critical(
                    "{} ta ketma-ket xatolik. {}s kutilmoqda...".format(
                        max_consecutive_errors, wait)
                )
                time.sleep(wait)
                consecutive_errors = 0
            else:
                backoff = min(RETRY_DELAY * consecutive_errors, 60)
                logger.info("{}s kutilmoqda...".format(backoff))
                time.sleep(backoff)


def main():
    # ── Print startup banner ─────────────────────────────────────────────────
    print("")
    print("=========================================")
    print("  ANIME BOT PRO v4")
    print("  Python: {}.{}+".format(sys.version_info.major, sys.version_info.minor))
    print("  Dependencies: 0")
    print("  Database: SQLite")
    print("  Telegram API: Connecting...")
    print("=========================================")
    print("")

    logger.info("=" * 60)
    logger.info("  ANIME BOT PRO v4 ishga tushmoqda...")
    logger.info("=" * 60)

    # ── Python version check ─────────────────────────────────────────────────
    if sys.version_info < (3, 9):
        logger.critical(
            "Python 3.9+ talab qilinadi. Joriy versiya: {}".format(sys.version))
        sys.exit(1)

    logger.info("Python versiyasi: {}".format(sys.version.split()[0]))

    # ── Initialize database ──────────────────────────────────────────────────
    try:
        db.init_db()
        logger.info("Ma'lumotlar bazasi tayyor.")
    except Exception as exc:
        logger.critical("Ma'lumotlar bazasini ishga tushirishda xatolik: {}".format(exc))
        sys.exit(1)

    # ── Verify bot token ─────────────────────────────────────────────────────
    try:
        me = api.get_me()
        bot_name = me.get("first_name", "")
        bot_user = me.get("username", BOT_USERNAME)
        logger.info("Bot ulandi: @{} ({})".format(bot_user, bot_name))

        print("=========================================")
        print("  ANIME BOT PRO v4")
        print("  Python: {}".format(sys.version.split()[0]))
        print("  Dependencies: 0")
        print("  Database: SQLite")
        print("  Telegram API: Connected")
        print("  Status: ONLINE")
        print("=========================================")
        print("")
        print("  Bot: @{} ({})".format(bot_user, bot_name))
        print("  Loglar: logs/bot.log")
        print("  To'xtatish: Ctrl+C")
        print("")

    except Exception as exc:
        logger.critical("Bot token noto'g'ri yoki ulanish xatosi: {}".format(exc))
        print("\n❌  Bot ulanmadi: {}".format(exc))
        print("config.json da bot_token ni tekshiring.\n")
        sys.exit(1)

    # ── Start background scheduler ────────────────────────────────────────────
    try:
        sched.start()
        logger.info("Scheduler ishga tushdi.")
    except Exception as exc:
        logger.warning("Scheduler xatosi: {}".format(exc))

    # ── Start polling loop ────────────────────────────────────────────────────
    polling_loop()


if __name__ == "__main__":
    main()
