"""
database.py — SQLite3 database layer for Ani Telegram Bot.
Auto-creates database and all tables on first startup.
All queries use parameterized statements to prevent SQL injection.
"""

import sqlite3
import logging
import threading
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)

# Thread-local storage for per-thread connections
_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    """Create all tables and indexes if they do not exist."""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username    TEXT,
            first_name  TEXT,
            balance     INTEGER DEFAULT 0,
            premium_until TEXT,
            referrals   INTEGER DEFAULT 0,
            referred_by INTEGER,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS anime (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT,
            genre       TEXT,
            year        INTEGER,
            country     TEXT,
            language    TEXT,
            poster      TEXT,
            premium     INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'ongoing',
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS episodes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id       INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            title          TEXT,
            video_file_id  TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS favorites (
            user_id  INTEGER NOT NULL,
            anime_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, anime_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channels (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_channel_id TEXT NOT NULL UNIQUE,
            username            TEXT,
            title               TEXT,
            required            INTEGER DEFAULT 1,
            created_at          TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            amount         INTEGER NOT NULL,
            provider       TEXT DEFAULT 'balance',
            transaction_id TEXT UNIQUE NOT NULL,
            status         TEXT DEFAULT 'pending',
            created_at     TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_anime_title       ON anime(title);
        CREATE INDEX IF NOT EXISTS idx_episodes_anime_id ON episodes(anime_id);
        CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id);
    """)
    conn.commit()
    logger.info("Database initialized successfully.")


def now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ─── USER OPERATIONS ─────────────────────────────────────────────────────────

def get_user(telegram_id: int) -> sqlite3.Row | None:
    c = get_conn().cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    return c.fetchone()


def create_user(telegram_id: int, username: str, first_name: str,
                referred_by: int = None, welcome_bonus: int = 0) -> sqlite3.Row:
    conn = get_conn()
    c = conn.cursor()
    ts = now_str()
    c.execute("""
        INSERT OR IGNORE INTO users
            (telegram_id, username, first_name, balance, referred_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (telegram_id, username, first_name, welcome_bonus, referred_by, ts, ts))
    conn.commit()
    return get_user(telegram_id)


def update_user(telegram_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    kwargs["updated_at"] = now_str()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [telegram_id]
    conn.execute(f"UPDATE users SET {fields} WHERE telegram_id = ?", values)
    conn.commit()


def get_all_users() -> list:
    c = get_conn().cursor()
    c.execute("SELECT * FROM users ORDER BY created_at DESC")
    return c.fetchall()


def get_users_count() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM users")
    return c.fetchone()[0]


def get_premium_users_count() -> int:
    c = get_conn().cursor()
    ts = now_str()
    c.execute("SELECT COUNT(*) FROM users WHERE premium_until > ?", (ts,))
    return c.fetchone()[0]


def get_total_balance() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COALESCE(SUM(balance), 0) FROM users")
    return c.fetchone()[0]


def add_referral(referrer_telegram_id: int, bonus: int):
    conn = get_conn()
    ts = now_str()
    conn.execute("""
        UPDATE users
        SET referrals = referrals + 1,
            balance   = balance + ?,
            updated_at = ?
        WHERE telegram_id = ?
    """, (bonus, ts, referrer_telegram_id))
    conn.commit()


def is_premium(telegram_id: int) -> bool:
    row = get_user(telegram_id)
    if not row:
        return False
    if not row["premium_until"]:
        return False
    return row["premium_until"] > now_str()


def add_balance(telegram_id: int, amount: int):
    conn = get_conn()
    ts = now_str()
    conn.execute("""
        UPDATE users SET balance = balance + ?, updated_at = ? WHERE telegram_id = ?
    """, (amount, ts, telegram_id))
    conn.commit()


def remove_balance(telegram_id: int, amount: int) -> bool:
    user = get_user(telegram_id)
    if not user or user["balance"] < amount:
        return False
    conn = get_conn()
    ts = now_str()
    conn.execute("""
        UPDATE users SET balance = balance - ?, updated_at = ? WHERE telegram_id = ?
    """, (amount, ts, telegram_id))
    conn.commit()
    return True


def set_premium(telegram_id: int, until: str):
    conn = get_conn()
    ts = now_str()
    conn.execute("""
        UPDATE users SET premium_until = ?, updated_at = ? WHERE telegram_id = ?
    """, (until, ts, telegram_id))
    conn.commit()


def search_user_by_id(telegram_id: int) -> sqlite3.Row | None:
    return get_user(telegram_id)


# ─── ANIME OPERATIONS ────────────────────────────────────────────────────────

def get_anime(anime_id: int) -> sqlite3.Row | None:
    c = get_conn().cursor()
    c.execute("SELECT * FROM anime WHERE id = ?", (anime_id,))
    return c.fetchone()


def search_anime(query: str) -> list:
    c = get_conn().cursor()
    c.execute("SELECT * FROM anime WHERE title LIKE ? ORDER BY title LIMIT 20",
              (f"%{query}%",))
    return c.fetchall()


def get_anime_catalog(offset: int = 0, limit: int = 8) -> list:
    c = get_conn().cursor()
    c.execute("SELECT * FROM anime ORDER BY created_at DESC LIMIT ? OFFSET ?",
              (limit, offset))
    return c.fetchall()


def get_anime_count() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM anime")
    return c.fetchone()[0]


def create_anime(title: str, description: str, genre: str, year: int,
                 country: str, language: str, poster: str,
                 premium: int, status: str) -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    c.execute("""
        INSERT INTO anime (title, description, genre, year, country, language, poster, premium, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, description, genre, year, country, language, poster, premium, status, ts))
    conn.commit()
    return c.lastrowid


def update_anime(anime_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [anime_id]
    conn.execute(f"UPDATE anime SET {fields} WHERE id = ?", values)
    conn.commit()


def delete_anime(anime_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM episodes  WHERE anime_id = ?", (anime_id,))
    conn.execute("DELETE FROM favorites WHERE anime_id = ?", (anime_id,))
    conn.execute("DELETE FROM anime     WHERE id = ?",       (anime_id,))
    conn.commit()


# ─── EPISODE OPERATIONS ──────────────────────────────────────────────────────

def get_episodes(anime_id: int) -> list:
    c = get_conn().cursor()
    c.execute("""
        SELECT * FROM episodes WHERE anime_id = ? ORDER BY episode_number
    """, (anime_id,))
    return c.fetchall()


def get_episode(episode_id: int) -> sqlite3.Row | None:
    c = get_conn().cursor()
    c.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
    return c.fetchone()


def get_episode_by_number(anime_id: int, episode_number: int) -> sqlite3.Row | None:
    c = get_conn().cursor()
    c.execute("""
        SELECT * FROM episodes WHERE anime_id = ? AND episode_number = ?
    """, (anime_id, episode_number))
    return c.fetchone()


def create_episode(anime_id: int, episode_number: int,
                   title: str, video_file_id: str) -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    c.execute("""
        INSERT INTO episodes (anime_id, episode_number, title, video_file_id, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (anime_id, episode_number, title, video_file_id, ts))
    conn.commit()
    return c.lastrowid


def get_episodes_count() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM episodes")
    return c.fetchone()[0]


def delete_episodes_for_anime(anime_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM episodes WHERE anime_id = ?", (anime_id,))
    conn.commit()


# ─── FAVORITES ───────────────────────────────────────────────────────────────

def add_favorite(user_id: int, anime_id: int) -> bool:
    """Returns True if added, False if already exists."""
    conn = get_conn()
    try:
        conn.execute("INSERT INTO favorites (user_id, anime_id) VALUES (?, ?)",
                     (user_id, anime_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def remove_favorite(user_id: int, anime_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM favorites WHERE user_id = ? AND anime_id = ?",
                 (user_id, anime_id))
    conn.commit()


def is_favorite(user_id: int, anime_id: int) -> bool:
    c = get_conn().cursor()
    c.execute("SELECT 1 FROM favorites WHERE user_id = ? AND anime_id = ?",
              (user_id, anime_id))
    return c.fetchone() is not None


def get_favorites(user_id: int) -> list:
    c = get_conn().cursor()
    c.execute("""
        SELECT a.* FROM anime a
        JOIN favorites f ON f.anime_id = a.id
        WHERE f.user_id = ?
        ORDER BY a.title
    """, (user_id,))
    return c.fetchall()


# ─── CHANNELS ────────────────────────────────────────────────────────────────

def get_required_channels() -> list:
    c = get_conn().cursor()
    c.execute("SELECT * FROM channels WHERE required = 1")
    return c.fetchall()


def get_channel(channel_id: int) -> sqlite3.Row | None:
    c = get_conn().cursor()
    c.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    return c.fetchone()


def add_channel(telegram_channel_id: str, username: str, title: str, required: int = 1) -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO channels (telegram_channel_id, username, title, required, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_channel_id, username, title, required, ts))
    conn.commit()
    return c.lastrowid


def delete_channel(channel_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    conn.commit()


def get_all_channels() -> list:
    c = get_conn().cursor()
    c.execute("SELECT * FROM channels ORDER BY created_at")
    return c.fetchall()


# ─── PAYMENTS ────────────────────────────────────────────────────────────────

def create_payment(user_id: int, amount: int, provider: str,
                   transaction_id: str, status: str = "completed") -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO payments (user_id, amount, provider, transaction_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, amount, provider, transaction_id, status, ts))
        conn.commit()
        return c.lastrowid
    except sqlite3.IntegrityError:
        return -1  # duplicate transaction


def payment_exists(transaction_id: str) -> bool:
    c = get_conn().cursor()
    c.execute("SELECT 1 FROM payments WHERE transaction_id = ?", (transaction_id,))
    return c.fetchone() is not None


# ─── SETTINGS ────────────────────────────────────────────────────────────────

def get_setting(key: str, default=None):
    c = get_conn().cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
