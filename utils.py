"""
utils.py — Shared utilities for ANIME BOT PRO v4.
Python 3.9 compatible. Standard library only.
"""

import html
import hashlib
import secrets
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# HTML / TEXT
# ══════════════════════════════════════════════════════════════════════════════

def escape(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    if not text:
        return ""
    return html.escape(str(text), quote=False)


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate text to max_len characters."""
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def format_currency(amount: int) -> str:
    """Format integer amount as currency string."""
    try:
        return "{:,} UZS".format(int(amount)).replace(",", " ")
    except (ValueError, TypeError):
        return "0 UZS"


def format_number(n: int) -> str:
    """Format large numbers with commas."""
    try:
        return "{:,}".format(int(n)).replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def build_star_rating(score: int) -> str:
    """Build a star rating string from 1-5."""
    score = max(0, min(5, score))
    return "⭐" * score + "☆" * (5 - score)


def build_progress_bar(current: int, total: int, width: int = 10) -> str:
    """Build a text progress bar."""
    if total == 0:
        return "░" * width
    filled = int(width * current / total)
    return "█" * filled + "░" * (width - filled)


def format_seconds(seconds: int) -> str:
    """Format seconds into h:m:s string."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return "{}s {}d {}s".format(h, m, s)
    if m:
        return "{}d {}s".format(m, s)
    return "{}s".format(s)


def format_time_remaining(seconds: int) -> str:
    """Human-readable time remaining."""
    if seconds <= 0:
        return "0 soniya"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h:
        parts.append("{}s".format(h))
    if m:
        parts.append("{}d".format(m))
    if s and not h:
        parts.append("{}s".format(s))
    return " ".join(parts) if parts else "0 soniya"


# ══════════════════════════════════════════════════════════════════════════════
# PREMIUM / DATE
# ══════════════════════════════════════════════════════════════════════════════

def is_premium_active(premium_until: Optional[str]) -> bool:
    """Check if premium_until date is in the future."""
    if not premium_until:
        return False
    try:
        expiry = datetime.strptime(premium_until, "%Y-%m-%d %H:%M:%S")
        return datetime.utcnow() < expiry
    except ValueError:
        return False


def premium_until_str(days: int) -> str:
    """Return ISO-format datetime string for premium expiry N days from now."""
    return (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def format_premium_until(premium_until: Optional[str]) -> str:
    """Human-readable premium expiry."""
    if not premium_until:
        return "Yo'q"
    try:
        expiry = datetime.strptime(premium_until, "%Y-%m-%d %H:%M:%S")
        if datetime.utcnow() < expiry:
            return expiry.strftime("%d.%m.%Y")
        return "Muddati tugagan"
    except ValueError:
        return "Noma'lum"


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY / IDs
# ══════════════════════════════════════════════════════════════════════════════

def make_transaction_id() -> str:
    """Generate a cryptographically secure unique transaction ID."""
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:24]


def validate_referral_code(code: str) -> Optional[int]:
    """Validate and parse a referral code (must be a positive integer telegram_id)."""
    try:
        val = int(code)
        if val > 0:
            return val
        return None
    except (ValueError, TypeError):
        return None


def parse_callback(data: str) -> Tuple[str, List[str]]:
    """Parse structured callback data. Returns (action, args_list)."""
    parts = data.split(":")
    return parts[0], parts[1:]


def safe_int(value: object, default: int = 0) -> int:
    """Safely convert value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_user_display(user_row) -> str:
    """Return display name for a user row."""
    if user_row["username"]:
        return "@{}".format(escape(user_row["username"]))
    return escape(user_row["first_name"] or "Foydalanuvchi")


def paginate(items: list, page: int, page_size: int) -> Tuple[list, int, int]:
    """
    Paginate a list. Pages are 0-indexed.
    Returns (page_items, total_pages, current_page).
    """
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    end = start + page_size
    return items[start:end], total_pages, page


# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING (in-memory, no Redis)
# ══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """
    Simple token-bucket rate limiter per user.
    Thread-safe using threading.Lock.
    """

    def __init__(self, max_calls: int = 5, period: float = 3.0):
        self._max_calls = max_calls
        self._period = period
        self._calls: dict = {}  # telegram_id -> list of timestamps
        self._lock = threading.Lock()

    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        with self._lock:
            timestamps = self._calls.get(user_id, [])
            # Remove old timestamps outside the window
            timestamps = [t for t in timestamps if now - t < self._period]
            if len(timestamps) >= self._max_calls:
                self._calls[user_id] = timestamps
                return False
            timestamps.append(now)
            self._calls[user_id] = timestamps
            return True

    def cleanup(self):
        """Remove stale entries. Call periodically from scheduler."""
        now = time.time()
        with self._lock:
            stale = [uid for uid, ts in self._calls.items()
                     if not any(now - t < self._period for t in ts)]
            for uid in stale:
                del self._calls[uid]


# Global rate limiters
message_rate_limiter = RateLimiter(max_calls=8, period=5.0)
callback_rate_limiter = RateLimiter(max_calls=15, period=5.0)


# ══════════════════════════════════════════════════════════════════════════════
# MISC
# ══════════════════════════════════════════════════════════════════════════════

def rate_limit_sleep(delay: float = 0.05):
    """Sleep briefly to respect Telegram rate limits."""
    time.sleep(delay)
