"""
config.py — Configuration loader for Ani Telegram Bot.
Reads config.json from project root. Never hardcodes secrets.
"""

import json
import os
import logging
import sys

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> dict:
    """Load configuration from config.json."""
    if not os.path.exists(CONFIG_PATH):
        logger.critical(f"config.json not found at {CONFIG_PATH}. Please create it.")
        sys.exit(1)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        logger.critical(f"config.json is invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Failed to read config.json: {e}")
        sys.exit(1)

    required_keys = ["bot_token", "admin_ids", "bot_username"]
    for key in required_keys:
        if key not in cfg:
            logger.critical(f"Missing required config key: '{key}'")
            sys.exit(1)

    if cfg.get("bot_token") in ("", "YOUR_BOT_TOKEN_HERE", None):
        logger.critical("bot_token is not set in config.json. Please set a valid token.")
        sys.exit(1)

    return cfg


# Single global config instance
CONFIG = load_config()

BOT_TOKEN: str = CONFIG["bot_token"]
ADMIN_IDS: list = CONFIG.get("admin_ids", [])
BOT_USERNAME: str = CONFIG.get("bot_username", "")
REFERRAL_BONUS: int = CONFIG.get("referral_bonus", 1000)
WELCOME_BONUS: int = CONFIG.get("welcome_bonus", 1000)
PREMIUM_PRICES: dict = CONFIG.get("premium_prices", {"7": 5000, "30": 15000, "365": 100000})
POLLING_TIMEOUT: int = CONFIG.get("polling_timeout", 30)
RETRY_DELAY: int = CONFIG.get("retry_delay", 5)
MAX_RETRIES: int = CONFIG.get("max_retries", 3)
PAGINATION_SIZE: int = CONFIG.get("pagination_size", 8)
BROADCAST_DELAY: float = CONFIG.get("broadcast_delay", 0.05)
LOG_LEVEL: str = CONFIG.get("log_level", "INFO")

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
TMP_DIR = os.path.join(BASE_DIR, "tmp")
DB_PATH = os.path.join(DATA_DIR, "anime.db")
LOG_PATH = os.path.join(LOGS_DIR, "bot.log")

# Ensure directories exist
for _dir in (DATA_DIR, LOGS_DIR, TMP_DIR, os.path.join(BASE_DIR, "public")):
    os.makedirs(_dir, exist_ok=True)
