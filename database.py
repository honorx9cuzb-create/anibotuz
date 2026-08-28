"""
database.py — SQLite3 database layer for ANIME BOT PRO v4.
Auto-creates all tables on first startup.
Uses parameterized queries, WAL mode, foreign keys, and indexes.
Python 3.9 compatible.
"""

import sqlite3
import logging
import threading
from datetime import datetime
from typing import Optional, List
from config import DB_PATH

logger = logging.getLogger(__name__)

_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with WAL and foreign keys enabled."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    """Create all tables and indexes. Safe to call multiple times."""
    conn = get_conn()
    c = conn.cursor()

    # ── USERS ────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id    INTEGER UNIQUE NOT NULL,
            username       TEXT,
            first_name     TEXT,
            last_name      TEXT,
            language       TEXT DEFAULT 'uz',
            balance        INTEGER DEFAULT 0,
            xp             INTEGER DEFAULT 0,
            level          INTEGER DEFAULT 1,
            premium_until  TEXT,
            is_blocked     INTEGER DEFAULT 0,
            is_admin       INTEGER DEFAULT 0,
            referred_by    INTEGER,
            referral_count INTEGER DEFAULT 0,
            daily_streak   INTEGER DEFAULT 0,
            last_daily_reward TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        )
    """)

    # ── ANIME ─────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS anime (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT NOT NULL,
            original_title TEXT,
            description    TEXT,
            genre          TEXT,
            year           INTEGER,
            country        TEXT,
            language       TEXT,
            status         TEXT DEFAULT 'ongoing',
            poster         TEXT,
            rating         REAL DEFAULT 0.0,
            rating_count   INTEGER DEFAULT 0,
            views          INTEGER DEFAULT 0,
            favorites      INTEGER DEFAULT 0,
            premium        INTEGER DEFAULT 0,
            featured       INTEGER DEFAULT 0,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        )
    """)

    # ── EPISODES ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id       INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            title          TEXT,
            video_file_id  TEXT NOT NULL,
            views          INTEGER DEFAULT 0,
            created_at     TEXT NOT NULL,
            UNIQUE(anime_id, episode_number),
            FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
        )
    """)

    # ── FAVORITES ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id    INTEGER NOT NULL,
            anime_id   INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, anime_id),
            FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
        )
    """)

    # ── WATCH HISTORY ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS watch_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            anime_id   INTEGER NOT NULL,
            episode_id INTEGER NOT NULL,
            watched_at TEXT NOT NULL,
            FOREIGN KEY (user_id)    REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (anime_id)   REFERENCES anime(id) ON DELETE CASCADE,
            FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
        )
    """)

    # ── WATCHLIST (follow) ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id    INTEGER NOT NULL,
            anime_id   INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, anime_id),
            FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
        )
    """)

    # ── RATINGS ───────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            anime_id   INTEGER NOT NULL,
            score      INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, anime_id),
            FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
        )
    """)

    # ── REVIEWS ───────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            anime_id   INTEGER NOT NULL,
            text       TEXT NOT NULL,
            status     TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
        )
    """)

    # ── CHANNELS ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_channel_id  TEXT NOT NULL UNIQUE,
            username             TEXT,
            title                TEXT,
            required             INTEGER DEFAULT 1,
            created_at           TEXT NOT NULL
        )
    """)

    # ── PAYMENTS ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            amount         INTEGER NOT NULL,
            provider       TEXT DEFAULT 'balance',
            transaction_id TEXT UNIQUE NOT NULL,
            status         TEXT DEFAULT 'pending',
            created_at     TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ── ADVERTISEMENTS ────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS advertisements (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            text        TEXT NOT NULL,
            button_text TEXT,
            button_url  TEXT,
            image       TEXT,
            start_at    TEXT,
            end_at      TEXT,
            active      INTEGER DEFAULT 1,
            views       INTEGER DEFAULT 0,
            clicks      INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL
        )
    """)

    # ── NOTIFICATION QUEUE ────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS notification_queue (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            message    TEXT NOT NULL,
            anime_id   INTEGER,
            episode_id INTEGER,
            sent       INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── SETTINGS ──────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # ── INDEXES ───────────────────────────────────────────────────────────────
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_users_telegram_id    ON users(telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_referred_by    ON users(referred_by)",
        "CREATE INDEX IF NOT EXISTS idx_anime_title          ON anime(title)",
        "CREATE INDEX IF NOT EXISTS idx_anime_genre          ON anime(genre)",
        "CREATE INDEX IF NOT EXISTS idx_anime_year           ON anime(year)",
        "CREATE INDEX IF NOT EXISTS idx_anime_rating         ON anime(rating DESC)",
        "CREATE INDEX IF NOT EXISTS idx_anime_views          ON anime(views DESC)",
        "CREATE INDEX IF NOT EXISTS idx_anime_featured       ON anime(featured)",
        "CREATE INDEX IF NOT EXISTS idx_episodes_anime_id    ON episodes(anime_id)",
        "CREATE INDEX IF NOT EXISTS idx_favorites_user_id    ON favorites(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_favorites_anime_id   ON favorites(anime_id)",
        "CREATE INDEX IF NOT EXISTS idx_watch_history_user   ON watch_history(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_watchlist_anime_id   ON watchlist(anime_id)",
        "CREATE INDEX IF NOT EXISTS idx_ratings_anime_id     ON ratings(anime_id)",
        "CREATE INDEX IF NOT EXISTS idx_reviews_anime_id     ON reviews(anime_id)",
        "CREATE INDEX IF NOT EXISTS idx_notif_queue_sent     ON notification_queue(sent, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_payments_user_id     ON payments(user_id)",
    ]
    for idx in indexes:
        c.execute(idx)

    conn.commit()
    logger.info("Database initialized successfully.")


# ══════════════════════════════════════════════════════════════════════════════
# USER OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_user(telegram_id: int) -> Optional[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    return c.fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return c.fetchone()


def create_user(telegram_id: int, username: str, first_name: str,
                last_name: str = "", language: str = "uz",
                referred_by: Optional[int] = None,
                welcome_bonus: int = 0) -> Optional[sqlite3.Row]:
    conn = get_conn()
    ts = now_str()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO users
                (telegram_id, username, first_name, last_name, language,
                 balance, referred_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (telegram_id, username, first_name, last_name, language,
              welcome_bonus, referred_by, ts, ts))
        conn.commit()
    except Exception as exc:
        logger.error("create_user error: {}".format(exc))
    return get_user(telegram_id)


def update_user(telegram_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    kwargs["updated_at"] = now_str()
    fields = ", ".join("{} = ?".format(k) for k in kwargs)
    values = list(kwargs.values()) + [telegram_id]
    conn.execute("UPDATE users SET {} WHERE telegram_id = ?".format(fields), values)
    conn.commit()


def get_all_users() -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM users ORDER BY created_at DESC")
    return c.fetchall()


def get_users_count() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM users")
    return c.fetchone()[0]


def get_new_users_today() -> int:
    c = get_conn().cursor()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (today + "%",))
    return c.fetchone()[0]


def get_active_users_today() -> int:
    """Users who sent a message in the last 24h (updated_at proxy)."""
    c = get_conn().cursor()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) FROM users WHERE updated_at LIKE ?", (today + "%",))
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


def get_leaderboard(limit: int = 20, offset: int = 0) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT * FROM users WHERE is_blocked = 0
        ORDER BY xp DESC LIMIT ? OFFSET ?
    """, (limit, offset))
    return c.fetchall()


def get_user_rank(telegram_id: int) -> int:
    c = get_conn().cursor()
    user = get_user(telegram_id)
    if not user:
        return 0
    c.execute("SELECT COUNT(*) FROM users WHERE xp > ? AND is_blocked = 0",
              (user["xp"],))
    return c.fetchone()[0] + 1


def add_balance(telegram_id: int, amount: int):
    conn = get_conn()
    conn.execute("""
        UPDATE users SET balance = balance + ?, updated_at = ? WHERE telegram_id = ?
    """, (amount, now_str(), telegram_id))
    conn.commit()


def remove_balance(telegram_id: int, amount: int) -> bool:
    """Atomic balance removal. Returns False if insufficient."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    if not row or row[0] < amount:
        return False
    conn.execute("""
        UPDATE users SET balance = balance - ?, updated_at = ?
        WHERE telegram_id = ? AND balance >= ?
    """, (amount, now_str(), telegram_id, amount))
    conn.commit()
    return conn.execute(
        "SELECT changes()"
    ).fetchone()[0] > 0


def add_xp(telegram_id: int, xp_amount: int):
    """Add XP and auto-update level."""
    conn = get_conn()
    ts = now_str()
    conn.execute("""
        UPDATE users SET xp = xp + ?, updated_at = ? WHERE telegram_id = ?
    """, (xp_amount, ts, telegram_id))
    conn.commit()
    # Recalculate level
    user = get_user(telegram_id)
    if user:
        new_level = _calculate_level(user["xp"])
        if new_level != user["level"]:
            conn.execute(
                "UPDATE users SET level = ?, updated_at = ? WHERE telegram_id = ?",
                (new_level, ts, telegram_id)
            )
            conn.commit()


def _calculate_level(xp: int) -> int:
    """
    Level thresholds:
    1=0xp  5=500xp  10=2000xp  20=8000xp  50=30000xp
    """
    if xp >= 30000:
        return 50
    if xp >= 8000:
        return 20
    if xp >= 2000:
        return 10
    if xp >= 500:
        return 5
    return 1


def get_level_name(level: int) -> str:
    names = {1: "Newbie", 5: "Otaku", 10: "Senpai", 20: "Master", 50: "Anime God"}
    # Return nearest label
    for threshold in sorted(names.keys(), reverse=True):
        if level >= threshold:
            return names[threshold]
    return "Newbie"


def add_referral(referrer_telegram_id: int, bonus: int):
    conn = get_conn()
    conn.execute("""
        UPDATE users
        SET referral_count = referral_count + 1,
            balance        = balance + ?,
            updated_at     = ?
        WHERE telegram_id = ?
    """, (bonus, now_str(), referrer_telegram_id))
    conn.commit()


def is_premium(telegram_id: int) -> bool:
    row = get_user(telegram_id)
    if not row or not row["premium_until"]:
        return False
    return row["premium_until"] > now_str()


def set_premium(telegram_id: int, until_str: str):
    conn = get_conn()
    conn.execute("""
        UPDATE users SET premium_until = ?, updated_at = ? WHERE telegram_id = ?
    """, (until_str, now_str(), telegram_id))
    conn.commit()


def block_user(telegram_id: int):
    update_user(telegram_id, is_blocked=1)


def unblock_user(telegram_id: int):
    update_user(telegram_id, is_blocked=0)


def get_expired_premium_users() -> List[sqlite3.Row]:
    """Users whose premium just expired (premium_until in the past, not null)."""
    c = get_conn().cursor()
    ts = now_str()
    c.execute("""
        SELECT * FROM users
        WHERE premium_until IS NOT NULL
          AND premium_until != ''
          AND premium_until < ?
    """, (ts,))
    return c.fetchall()


def claim_daily_reward(telegram_id: int, amount: int) -> bool:
    """
    Claim daily reward. Returns True if successfully claimed.
    Enforces one claim per 24 hours.
    """
    from datetime import timedelta
    user = get_user(telegram_id)
    if not user:
        return False
    now = datetime.utcnow()
    if user["last_daily_reward"]:
        try:
            last = datetime.strptime(user["last_daily_reward"], "%Y-%m-%d %H:%M:%S")
            if (now - last).total_seconds() < 86400:
                return False
        except ValueError:
            pass

    # Calculate streak
    streak = user["daily_streak"]
    if user["last_daily_reward"]:
        try:
            last = datetime.strptime(user["last_daily_reward"], "%Y-%m-%d %H:%M:%S")
            diff = (now - last).total_seconds()
            if diff < 172800:  # within 48h
                streak = streak + 1
            else:
                streak = 1
        except ValueError:
            streak = 1
    else:
        streak = 1

    conn = get_conn()
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        UPDATE users
        SET balance = balance + ?,
            daily_streak = ?,
            last_daily_reward = ?,
            updated_at = ?
        WHERE telegram_id = ?
    """, (amount, streak, ts, ts, telegram_id))
    conn.commit()
    add_xp(telegram_id, 10)
    return True


def get_daily_streak(telegram_id: int) -> int:
    user = get_user(telegram_id)
    if not user:
        return 0
    return user["daily_streak"] or 0


def can_claim_daily(telegram_id: int) -> bool:
    from datetime import timedelta
    user = get_user(telegram_id)
    if not user or not user["last_daily_reward"]:
        return True
    try:
        last = datetime.strptime(user["last_daily_reward"], "%Y-%m-%d %H:%M:%S")
        return (datetime.utcnow() - last).total_seconds() >= 86400
    except ValueError:
        return True


def seconds_until_daily(telegram_id: int) -> int:
    user = get_user(telegram_id)
    if not user or not user["last_daily_reward"]:
        return 0
    try:
        last = datetime.strptime(user["last_daily_reward"], "%Y-%m-%d %H:%M:%S")
        elapsed = (datetime.utcnow() - last).total_seconds()
        remaining = 86400 - elapsed
        return max(0, int(remaining))
    except ValueError:
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# ANIME OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_anime(anime_id: int) -> Optional[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM anime WHERE id = ?", (anime_id,))
    return c.fetchone()


def search_anime(query: str) -> List[sqlite3.Row]:
    """Search by title, original_title, genre, year. Partial matching."""
    c = get_conn().cursor()
    q = "%{}%".format(query)
    # Year search
    try:
        year_val = int(query)
        c.execute("""
            SELECT * FROM anime
            WHERE title LIKE ? OR original_title LIKE ? OR genre LIKE ? OR year = ?
            ORDER BY views DESC LIMIT 20
        """, (q, q, q, year_val))
    except ValueError:
        c.execute("""
            SELECT * FROM anime
            WHERE title LIKE ? OR original_title LIKE ? OR genre LIKE ?
            ORDER BY views DESC LIMIT 20
        """, (q, q, q))
    return c.fetchall()


def get_anime_catalog(offset: int = 0, limit: int = 8,
                      sort: str = "new") -> List[sqlite3.Row]:
    c = get_conn().cursor()
    order = {
        "new":       "created_at DESC",
        "trending":  "views DESC",
        "rating":    "rating DESC",
        "views":     "views DESC",
        "favorites": "favorites DESC",
    }.get(sort, "created_at DESC")
    c.execute(
        "SELECT * FROM anime ORDER BY {} LIMIT ? OFFSET ?".format(order),
        (limit, offset)
    )
    return c.fetchall()


def get_featured_anime(limit: int = 10) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM anime WHERE featured = 1 ORDER BY created_at DESC LIMIT ?",
              (limit,))
    return c.fetchall()


def get_premium_anime(limit: int = 20, offset: int = 0) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM anime WHERE premium = 1 ORDER BY rating DESC LIMIT ? OFFSET ?",
              (limit, offset))
    return c.fetchall()


def get_anime_by_genre(genre: str, offset: int = 0, limit: int = 8) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT * FROM anime WHERE genre LIKE ? ORDER BY rating DESC LIMIT ? OFFSET ?
    """, ("%{}%".format(genre), limit, offset))
    return c.fetchall()


def get_anime_count() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM anime")
    return c.fetchone()[0]


def create_anime(title: str, original_title: str, description: str,
                 genre: str, year: int, country: str, language: str,
                 poster: str, premium: int, status: str,
                 featured: int = 0) -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    c.execute("""
        INSERT INTO anime
            (title, original_title, description, genre, year, country,
             language, poster, premium, status, featured, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, original_title, description, genre, year, country,
          language, poster, premium, status, featured, ts, ts))
    conn.commit()
    return c.lastrowid


def update_anime(anime_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    kwargs["updated_at"] = now_str()
    fields = ", ".join("{} = ?".format(k) for k in kwargs)
    values = list(kwargs.values()) + [anime_id]
    conn.execute("UPDATE anime SET {} WHERE id = ?".format(fields), values)
    conn.commit()


def delete_anime(anime_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM anime WHERE id = ?", (anime_id,))
    conn.commit()


def increment_anime_views(anime_id: int):
    conn = get_conn()
    conn.execute("UPDATE anime SET views = views + 1 WHERE id = ?", (anime_id,))
    conn.commit()


def recalculate_anime_rating(anime_id: int):
    """Recalculate average rating from ratings table."""
    c = get_conn().cursor()
    c.execute("""
        SELECT AVG(score), COUNT(*) FROM ratings WHERE anime_id = ?
    """, (anime_id,))
    row = c.fetchone()
    avg = round(row[0] or 0.0, 2)
    count = row[1] or 0
    conn = get_conn()
    conn.execute(
        "UPDATE anime SET rating = ?, rating_count = ?, updated_at = ? WHERE id = ?",
        (avg, count, now_str(), anime_id)
    )
    conn.commit()


def update_anime_favorites_count(anime_id: int):
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM favorites WHERE anime_id = ?", (anime_id,))
    count = c.fetchone()[0]
    get_conn().execute(
        "UPDATE anime SET favorites = ?, updated_at = ? WHERE id = ?",
        (count, now_str(), anime_id)
    )
    get_conn().commit()


# ══════════════════════════════════════════════════════════════════════════════
# EPISODE OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_episodes(anime_id: int) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT * FROM episodes WHERE anime_id = ? ORDER BY episode_number
    """, (anime_id,))
    return c.fetchall()


def get_episode(episode_id: int) -> Optional[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
    return c.fetchone()


def get_episode_by_number(anime_id: int, episode_number: int) -> Optional[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT * FROM episodes WHERE anime_id = ? AND episode_number = ?
    """, (anime_id, episode_number))
    return c.fetchone()


def get_episodes_count() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM episodes")
    return c.fetchone()[0]


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


def increment_episode_views(episode_id: int):
    conn = get_conn()
    conn.execute("UPDATE episodes SET views = views + 1 WHERE id = ?", (episode_id,))
    conn.commit()


def delete_episode(episode_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
    conn.commit()


def get_latest_episodes(limit: int = 10) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT e.*, a.title as anime_title FROM episodes e
        JOIN anime a ON a.id = e.anime_id
        ORDER BY e.created_at DESC LIMIT ?
    """, (limit,))
    return c.fetchall()


# ══════════════════════════════════════════════════════════════════════════════
# FAVORITES
# ══════════════════════════════════════════════════════════════════════════════

def add_favorite(user_id: int, anime_id: int) -> bool:
    """Returns True if added, False if already exists."""
    conn = get_conn()
    ts = now_str()
    try:
        conn.execute(
            "INSERT INTO favorites (user_id, anime_id, created_at) VALUES (?, ?, ?)",
            (user_id, anime_id, ts)
        )
        conn.commit()
        update_anime_favorites_count(anime_id)
        return True
    except sqlite3.IntegrityError:
        return False


def remove_favorite(user_id: int, anime_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM favorites WHERE user_id = ? AND anime_id = ?",
                 (user_id, anime_id))
    conn.commit()
    update_anime_favorites_count(anime_id)


def is_favorite(user_id: int, anime_id: int) -> bool:
    c = get_conn().cursor()
    c.execute("SELECT 1 FROM favorites WHERE user_id = ? AND anime_id = ?",
              (user_id, anime_id))
    return c.fetchone() is not None


def get_favorites(user_id: int) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT a.* FROM anime a
        JOIN favorites f ON f.anime_id = a.id
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC
    """, (user_id,))
    return c.fetchall()


# ══════════════════════════════════════════════════════════════════════════════
# WATCH HISTORY
# ══════════════════════════════════════════════════════════════════════════════

def add_watch_history(user_id: int, anime_id: int, episode_id: int):
    conn = get_conn()
    ts = now_str()
    # Update if already exists, otherwise insert
    conn.execute("""
        INSERT INTO watch_history (user_id, anime_id, episode_id, watched_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, anime_id, episode_id, ts))
    conn.commit()


def get_watch_history(user_id: int, limit: int = 10) -> List[sqlite3.Row]:
    """Returns last watched episodes with anime info, most recent first."""
    c = get_conn().cursor()
    c.execute("""
        SELECT wh.*, a.title as anime_title, e.episode_number
        FROM watch_history wh
        JOIN anime a ON a.id = wh.anime_id
        JOIN episodes e ON e.id = wh.episode_id
        WHERE wh.user_id = ?
        ORDER BY wh.watched_at DESC LIMIT ?
    """, (user_id, limit))
    return c.fetchall()


def get_last_watched(user_id: int, anime_id: int) -> Optional[sqlite3.Row]:
    """Get most recently watched episode for an anime."""
    c = get_conn().cursor()
    c.execute("""
        SELECT wh.*, e.episode_number FROM watch_history wh
        JOIN episodes e ON e.id = wh.episode_id
        WHERE wh.user_id = ? AND wh.anime_id = ?
        ORDER BY wh.watched_at DESC LIMIT 1
    """, (user_id, anime_id))
    return c.fetchone()


# ══════════════════════════════════════════════════════════════════════════════
# WATCHLIST (follow)
# ══════════════════════════════════════════════════════════════════════════════

def add_watchlist(user_id: int, anime_id: int) -> bool:
    conn = get_conn()
    ts = now_str()
    try:
        conn.execute(
            "INSERT INTO watchlist (user_id, anime_id, created_at) VALUES (?, ?, ?)",
            (user_id, anime_id, ts)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def remove_watchlist(user_id: int, anime_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM watchlist WHERE user_id = ? AND anime_id = ?",
                 (user_id, anime_id))
    conn.commit()


def is_in_watchlist(user_id: int, anime_id: int) -> bool:
    c = get_conn().cursor()
    c.execute("SELECT 1 FROM watchlist WHERE user_id = ? AND anime_id = ?",
              (user_id, anime_id))
    return c.fetchone() is not None


def get_watchlist(user_id: int) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT a.* FROM anime a
        JOIN watchlist w ON w.anime_id = a.id
        WHERE w.user_id = ?
        ORDER BY a.title
    """, (user_id,))
    return c.fetchall()


def get_anime_followers(anime_id: int) -> List[sqlite3.Row]:
    """Get all users following an anime for new episode notifications."""
    c = get_conn().cursor()
    c.execute("""
        SELECT u.* FROM users u
        JOIN watchlist w ON w.user_id = u.id
        WHERE w.anime_id = ? AND u.is_blocked = 0
    """, (anime_id,))
    return c.fetchall()


# ══════════════════════════════════════════════════════════════════════════════
# RATINGS
# ══════════════════════════════════════════════════════════════════════════════

def rate_anime(user_id: int, anime_id: int, score: int) -> bool:
    """Add or update a rating. Returns True on success."""
    if not 1 <= score <= 5:
        return False
    conn = get_conn()
    ts = now_str()
    try:
        conn.execute("""
            INSERT INTO ratings (user_id, anime_id, score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, anime_id) DO UPDATE SET score = ?, updated_at = ?
        """, (user_id, anime_id, score, ts, ts, score, ts))
        conn.commit()
        recalculate_anime_rating(anime_id)
        return True
    except Exception as exc:
        logger.error("rate_anime error: {}".format(exc))
        return False


def get_user_rating(user_id: int, anime_id: int) -> int:
    c = get_conn().cursor()
    c.execute("SELECT score FROM ratings WHERE user_id = ? AND anime_id = ?",
              (user_id, anime_id))
    row = c.fetchone()
    return row[0] if row else 0


# ══════════════════════════════════════════════════════════════════════════════
# REVIEWS
# ══════════════════════════════════════════════════════════════════════════════

def add_review(user_id: int, anime_id: int, text: str) -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    c.execute("""
        INSERT INTO reviews (user_id, anime_id, text, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
    """, (user_id, anime_id, text, ts))
    conn.commit()
    return c.lastrowid


def get_approved_reviews(anime_id: int, limit: int = 5) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT r.*, u.first_name, u.username FROM reviews r
        JOIN users u ON u.id = r.user_id
        WHERE r.anime_id = ? AND r.status = 'approved'
        ORDER BY r.created_at DESC LIMIT ?
    """, (anime_id, limit))
    return c.fetchall()


def get_pending_reviews(limit: int = 20) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT r.*, u.first_name, u.username, a.title as anime_title
        FROM reviews r
        JOIN users u ON u.id = r.user_id
        JOIN anime a ON a.id = r.anime_id
        WHERE r.status = 'pending' ORDER BY r.created_at ASC LIMIT ?
    """, (limit,))
    return c.fetchall()


def update_review_status(review_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE reviews SET status = ? WHERE id = ?", (status, review_id))
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# CHANNELS
# ══════════════════════════════════════════════════════════════════════════════

def get_required_channels() -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM channels WHERE required = 1")
    return c.fetchall()


def get_all_channels() -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM channels ORDER BY created_at")
    return c.fetchall()


def add_channel(telegram_channel_id: str, username: str,
                title: str, required: int = 1) -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO channels
            (telegram_channel_id, username, title, required, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_channel_id, username, title, required, ts))
    conn.commit()
    return c.lastrowid


def delete_channel(channel_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    conn.commit()


def get_channel(channel_id: int) -> Optional[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    return c.fetchone()


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════

def create_payment(user_id: int, amount: int, provider: str,
                   transaction_id: str, status: str = "completed") -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO payments
                (user_id, amount, provider, transaction_id, status, created_at)
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


def get_total_revenue() -> int:
    c = get_conn().cursor()
    c.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM payments
        WHERE status = 'completed' AND provider NOT LIKE 'admin:%'
    """)
    return c.fetchone()[0]


def get_payments_count() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM payments WHERE status = 'completed'")
    return c.fetchone()[0]


# ══════════════════════════════════════════════════════════════════════════════
# ADVERTISEMENTS
# ══════════════════════════════════════════════════════════════════════════════

def get_active_ads() -> List[sqlite3.Row]:
    c = get_conn().cursor()
    ts = now_str()
    c.execute("""
        SELECT * FROM advertisements
        WHERE active = 1
          AND (start_at IS NULL OR start_at <= ?)
          AND (end_at IS NULL OR end_at >= ?)
        ORDER BY created_at DESC LIMIT 1
    """, (ts, ts))
    return c.fetchall()


def create_ad(title: str, text: str, button_text: str, button_url: str,
              image: str, start_at: str, end_at: str) -> int:
    conn = get_conn()
    ts = now_str()
    c = conn.cursor()
    c.execute("""
        INSERT INTO advertisements
            (title, text, button_text, button_url, image, start_at, end_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, text, button_text, button_url, image, start_at, end_at, ts))
    conn.commit()
    return c.lastrowid


def increment_ad_views(ad_id: int):
    conn = get_conn()
    conn.execute("UPDATE advertisements SET views = views + 1 WHERE id = ?", (ad_id,))
    conn.commit()


def increment_ad_clicks(ad_id: int):
    conn = get_conn()
    conn.execute("UPDATE advertisements SET clicks = clicks + 1 WHERE id = ?", (ad_id,))
    conn.commit()


def get_all_ads() -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM advertisements ORDER BY created_at DESC")
    return c.fetchall()


def delete_ad(ad_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM advertisements WHERE id = ?", (ad_id,))
    conn.commit()


def toggle_ad(ad_id: int):
    conn = get_conn()
    conn.execute("UPDATE advertisements SET active = 1 - active WHERE id = ?", (ad_id,))
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION QUEUE
# ══════════════════════════════════════════════════════════════════════════════

def queue_notification(user_id: int, message: str,
                       anime_id: Optional[int] = None,
                       episode_id: Optional[int] = None):
    conn = get_conn()
    ts = now_str()
    conn.execute("""
        INSERT INTO notification_queue (user_id, message, anime_id, episode_id, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, message, anime_id, episode_id, ts))
    conn.commit()


def get_pending_notifications(limit: int = 50) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("""
        SELECT * FROM notification_queue WHERE sent = 0
        ORDER BY created_at ASC LIMIT ?
    """, (limit,))
    return c.fetchall()


def mark_notification_sent(notif_id: int):
    conn = get_conn()
    conn.execute("UPDATE notification_queue SET sent = 1 WHERE id = ?", (notif_id,))
    conn.commit()


def cleanup_old_notifications(days: int = 7):
    """Delete sent notifications older than N days."""
    conn = get_conn()
    cutoff = datetime.utcnow().strftime("%Y-%m-%d")
    conn.execute("""
        DELETE FROM notification_queue
        WHERE sent = 1 AND created_at < ?
    """, (cutoff,))
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
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


def is_maintenance_mode() -> bool:
    val = get_setting("maintenance_mode", "0")
    return val == "1"


def set_maintenance_mode(enabled: bool):
    set_setting("maintenance_mode", "1" if enabled else "0")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

def get_top_anime(limit: int = 5) -> List[sqlite3.Row]:
    c = get_conn().cursor()
    c.execute("SELECT * FROM anime ORDER BY views DESC LIMIT ?", (limit,))
    return c.fetchall()


def get_total_views() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COALESCE(SUM(views), 0) FROM anime")
    return c.fetchone()[0]


def get_total_favorites() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM favorites")
    return c.fetchone()[0]


def get_total_ratings() -> int:
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM ratings")
    return c.fetchone()[0]


# ══════════════════════════════════════════════════════════════════════════════
# BACKUP
# ══════════════════════════════════════════════════════════════════════════════

def create_backup(backup_path: str) -> bool:
    """Create a SQLite backup using the sqlite3 backup API."""
    try:
        source = get_conn()
        dest = sqlite3.connect(backup_path)
        source.backup(dest)
        dest.close()
        logger.info("Backup created: {}".format(backup_path))
        return True
    except Exception as exc:
        logger.error("Backup failed: {}".format(exc))
        return False


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def export_users_csv(path: str) -> bool:
    import csv
    try:
        c = get_conn().cursor()
        c.execute("SELECT * FROM users ORDER BY id")
        rows = c.fetchall()
        if not rows:
            return False
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in c.description])
            writer.writerows([list(r) for r in rows])
        return True
    except Exception as exc:
        logger.error("export_users_csv error: {}".format(exc))
        return False


def export_anime_csv(path: str) -> bool:
    import csv
    try:
        c = get_conn().cursor()
        c.execute("SELECT * FROM anime ORDER BY id")
        rows = c.fetchall()
        if not rows:
            return False
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in c.description])
            writer.writerows([list(r) for r in rows])
        return True
    except Exception as exc:
        logger.error("export_anime_csv error: {}".format(exc))
        return False


def export_payments_csv(path: str) -> bool:
    import csv
    try:
        c = get_conn().cursor()
        c.execute("SELECT * FROM payments ORDER BY id")
        rows = c.fetchall()
        if not rows:
            return False
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in c.description])
            writer.writerows([list(r) for r in rows])
        return True
    except Exception as exc:
        logger.error("export_payments_csv error: {}".format(exc))
        return False
