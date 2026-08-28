"""
config.py — Configuration loader for ANIME BOT PRO v4.
Reads config.json. Never hardcodes secrets.
Environment variables take priority over config.json values.
"""

import json
import os
import logging
import sys

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> dict:
    """Load configuration from config.json with environment variable overrides."""
    if not os.path.exists(CONFIG_PATH):
        logger.critical(
            f"config.json topilmadi: {CONFIG_PATH}\n"
            "config.example.json dan nusxa oling va to'ldiring."
        )
        sys.exit(1)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        logger.critical(f"config.json noto'g'ri JSON: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"config.json o'qishda xatolik: {e}")
        sys.exit(1)

    # Environment variable overrides (higher priority)
    if os.environ.get("BOT_TOKEN"):
        cfg["bot_token"] = os.environ["BOT_TOKEN"]
    if os.environ.get("BOT_USERNAME"):
        cfg["bot_username"] = os.environ["BOT_USERNAME"]

    required_keys = ["bot_token", "admin_ids", "bot_username"]
    for key in required_keys:
        if key not in cfg:
            logger.critical(f"config.json da majburiy kalit yo'q: '{key}'")
            sys.exit(1)

    if cfg.get("bot_token") in ("", "YOUR_BOT_TOKEN_HERE", None):
        logger.critical(
            "bot_token o'rnatilmagan. config.json da haqiqiy token kiriting."
        )
        sys.exit(1)

    return cfg


CONFIG = load_config()

# ── Core
BOT_TOKEN: str = CONFIG["bot_token"]
ADMIN_IDS: list = CONFIG.get("admin_ids", [])
BOT_USERNAME: str = CONFIG.get("bot_username", "")

# ── Bonuses
REFERRAL_BONUS: int = CONFIG.get("referral_bonus", 1000)
WELCOME_BONUS: int = CONFIG.get("welcome_bonus", 1000)

# ── Premium
PREMIUM_PRICES: dict = CONFIG.get("premium_prices", {
    "7": 5000, "30": 15000, "90": 35000, "365": 100000
})

# ── Polling
POLLING_TIMEOUT: int = CONFIG.get("polling_timeout", 30)
RETRY_DELAY: int = CONFIG.get("retry_delay", 5)
MAX_RETRIES: int = CONFIG.get("max_retries", 3)

# ── UI
PAGINATION_SIZE: int = CONFIG.get("pagination_size", 8)
BROADCAST_DELAY: float = CONFIG.get("broadcast_delay", 0.05)

# ── Logging
LOG_LEVEL: str = CONFIG.get("log_level", "INFO")

# ── Maintenance
MAINTENANCE_MODE: bool = CONFIG.get("maintenance_mode", False)

# ── Payment providers
CLICK_CONFIG: dict = CONFIG.get("click", {})
PAYME_CONFIG: dict = CONFIG.get("payme", {})

# ── AI
AI_CONFIG: dict = CONFIG.get("ai", {"enabled": False})

# ── Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
TMP_DIR = os.path.join(BASE_DIR, "tmp")
BACKUPS_DIR = os.path.join(DATA_DIR, "backups")
EXPORTS_DIR = os.path.join(DATA_DIR, "exports")
DB_PATH = os.path.join(DATA_DIR, "anime.db")
LOG_PATH = os.path.join(LOGS_DIR, "bot.log")

# Ensure required directories exist
for _dir in (DATA_DIR, LOGS_DIR, TMP_DIR, BACKUPS_DIR, EXPORTS_DIR,
             os.path.join(BASE_DIR, "public")):
    os.makedirs(_dir, exist_ok=True)
