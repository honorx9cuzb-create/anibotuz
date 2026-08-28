"""
bot.py — Entry point for Ani Telegram Bot.
Long-polling loop using only Python standard library.
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
from config import POLLING_TIMEOUT, RETRY_DELAY, BOT_TOKEN, BOT_USERNAME


def main():
    logger.info("=" * 60)
    logger.info("  Ani Telegram Bot ishga tushmoqda...")
    logger.info("=" * 60)

    # ── Python version check ─────────────────────────────────────────────────
    if sys.version_info < (3, 9):
        logger.critical(f"Python 3.9+ talab qilinadi. Joriy versiya: {sys.version}")
        sys.exit(1)

    logger.info(f"Python versiyasi: {sys.version.split()[0]}")

    # ── Initialize database ──────────────────────────────────────────────────
    try:
        db.init_db()
        logger.info("Ma'lumotlar bazasi tayyor.")
    except Exception as e:
        logger.critical(f"Ma'lumotlar bazasini ishga tushirishda xatolik: {e}")
        sys.exit(1)

    # ── Verify bot token ─────────────────────────────────────────────────────
    try:
        me = api.get_me()
        bot_name = me.get("first_name", "")
        bot_user = me.get("username", BOT_USERNAME)
        logger.info(f"Bot ulandi: @{bot_user} ({bot_name})")
        print(f"\n✅  Bot ishga tushdi: @{bot_user} ({bot_name})")
        print(f"📋  Loglar: logs/bot.log")
        print(f"🛑  To'xtatish uchun: Ctrl+C\n")
    except Exception as e:
        logger.critical(f"Bot token noto'g'ri yoki ulanish xatosi: {e}")
        sys.exit(1)

    # ── Start polling loop ───────────────────────────────────────────────────
    polling_loop()


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

                # Advance offset past this update
                offset = update_id + 1

                try:
                    handlers.handle_update(update)
                except Exception as e:
                    logger.error(
                        f"handle_update xatosi (update_id={update_id}): {e}",
                        exc_info=True,
                    )
                    # Continue processing next updates even if one fails

        except KeyboardInterrupt:
            logger.info("Bot to'xtatildi (KeyboardInterrupt).")
            print("\n👋  Bot to'xtatildi.")
            sys.exit(0)

        except Exception as e:
            consecutive_errors += 1
            logger.error(
                f"Polling xatosi ({consecutive_errors}/{max_consecutive_errors}): {e}",
                exc_info=False,
            )

            if consecutive_errors >= max_consecutive_errors:
                logger.critical(
                    f"{max_consecutive_errors} ta ketma-ket xatolik. "
                    f"{RETRY_DELAY * 5}s kutilmoqda..."
                )
                time.sleep(RETRY_DELAY * 5)
                consecutive_errors = 0
            else:
                backoff = min(RETRY_DELAY * consecutive_errors, 60)
                logger.info(f"{backoff}s kutilmoqda...")
                time.sleep(backoff)


if __name__ == "__main__":
    main()
