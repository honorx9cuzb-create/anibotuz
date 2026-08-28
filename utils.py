"""
utils.py — Shared utilities for Ani Telegram Bot.
"""

import html
import hashlib
import secrets
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def escape(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    if not text:
        return ""
    return html.escape(str(text), quote=False)


def format_currency(amount: int) -> str:
    """Format integer amount as currency string."""
    return f"{amount:,} UZS".replace(",", " ")


def make_transaction_id() -> str:
    """Generate a unique transaction ID."""
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:24]


def parse_callback(data: str) -> tuple:
    """
    Parse structured callback data.
    Returns (action, *args) tuple.
    E.g. 'anime:123' -> ('anime', '123')
    """
    parts = data.split(":")
    return parts[0], parts[1:]


def premium_until_str(days: int) -> str:
    """Return ISO-format datetime string for premium expiry."""
    return (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def is_premium_active(premium_until: str) -> bool:
    """Check if premium_until date is in the future."""
    if not premium_until:
        return False
    try:
        expiry = datetime.strptime(premium_until, "%Y-%m-%d %H:%M:%S")
        return datetime.utcnow() < expiry
    except ValueError:
        return False


def format_premium_until(premium_until: str) -> str:
    """Return a human-readable premium expiry string."""
    if not premium_until:
        return "Yo'q"
    try:
        expiry = datetime.strptime(premium_until, "%Y-%m-%d %H:%M:%S")
        if datetime.utcnow() < expiry:
            return expiry.strftime("%d.%m.%Y")
        return "Muddati tugagan"
    except ValueError:
        return "Noma'lum"


def paginate(items: list, page: int, page_size: int) -> tuple:
    """
    Paginate a list.
    Returns (page_items, total_pages, current_page).
    Pages are 0-indexed internally.
    """
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    end = start + page_size
    return items[start:end], total_pages, page


def safe_int(value, default: int = 0) -> int:
    """Safely convert value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate text to max_len characters."""
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def get_user_display(user_row) -> str:
    """Return display name for a user row."""
    if user_row["username"]:
        return f"@{escape(user_row['username'])}"
    return escape(user_row["first_name"] or "Foydalanuvchi")


def rate_limit_sleep(delay: float = 0.05):
    """Sleep to avoid Telegram flood limits."""
    time.sleep(delay)


def validate_referral_code(code: str) -> int | None:
    """Validate and parse a referral code (should be a telegram_id integer)."""
    try:
        val = int(code)
        if val > 0:
            return val
        return None
    except (ValueError, TypeError):
        return None


def build_progress_bar(current: int, total: int, width: int = 10) -> str:
    """Build a simple text progress bar."""
    if total == 0:
        return "░" * width
    filled = int(width * current / total)
    return "█" * filled + "░" * (width - filled)
