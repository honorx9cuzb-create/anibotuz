"""
keyboards.py — Inline and reply keyboard builders for ANIME BOT PRO v4.
All keyboards return dicts compatible with Telegram's reply_markup JSON.
Python 3.9 compatible.
"""

from typing import Optional, List, Tuple
from config import PREMIUM_PRICES, PAGINATION_SIZE
from utils import escape

# ──────────────────────────────────────────────────────────────────────────────
# LOW-LEVEL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def inline(buttons: List[List[Tuple]]) -> dict:
    """
    Build InlineKeyboardMarkup.
    Each row is a list of tuples:
      (text, callback_data)          — callback button
      (text, url, "url")             — URL button
    """
    keyboard = []
    for row in buttons:
        kb_row = []
        for item in row:
            if len(item) == 3 and item[2] == "url":
                kb_row.append({"text": item[0], "url": item[1]})
            else:
                kb_row.append({"text": item[0], "callback_data": item[1]})
        keyboard.append(kb_row)
    return {"inline_keyboard": keyboard}


def reply(buttons: List[List[str]], resize: bool = True,
          one_time: bool = False) -> dict:
    """Build ReplyKeyboardMarkup from a 2D list of text strings."""
    keyboard = [[{"text": t} for t in row] for row in buttons]
    return {
        "keyboard": keyboard,
        "resize_keyboard": resize,
        "one_time_keyboard": one_time,
    }


def remove_keyboard() -> dict:
    return {"remove_keyboard": True}


# ──────────────────────────────────────────────────────────────────────────────
# MAIN MENU
# ──────────────────────────────────────────────────────────────────────────────

def main_menu() -> dict:
    return reply([
        ["🔎 Qidirish", "🔢 ID qidirish"],
        ["📚 Katalog", "⭐ Sevimlilar"],
        ["▶️ Davom ettirish", "📌 Kuzatmoqda"],
        ["👤 Profil", "🎁 Kunlik bonus"],
        ["💎 Premium", "🏆 Top Otaku"],
        ["💰 Balans", "🎁 Referal"],
    ])


# ──────────────────────────────────────────────────────────────────────────────
# CATALOG / FILTERS
# ──────────────────────────────────────────────────────────────────────────────

def catalog_filter_keyboard() -> dict:
    return inline([
        [("🆕 Yangi", "cat:new:0"), ("🔥 Trending", "cat:trending:0")],
        [("⭐ Reyting", "cat:rating:0"), ("👁 Ko'p ko'rilgan", "cat:views:0")],
        [("❤️ Ko'p saqlangan", "cat:favorites:0"), ("💎 Premium", "cat:premium:0")],
        [("🎯 Featured", "cat:featured:0"), ("🎭 Janrlar", "genres:0")],
        [("⬅️ Orqaga", "main_menu")],
    ])


def genres_keyboard() -> dict:
    genres = [
        "Action", "Comedy", "Romance", "Horror", "Fantasy",
        "Sci-Fi", "Drama", "School", "Mystery", "Supernatural",
        "Martial Arts", "Game",
    ]
    rows = []
    row = []
    for g in genres:
        row.append(("🎭 {}".format(g), "genre:{}:0".format(g)))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("⬅️ Orqaga", "catalog:0")])
    return inline(rows)


def catalog_keyboard(anime_rows: list, page: int, total_pages: int,
                     sort: str = "new") -> dict:
    rows = []
    for a in anime_rows:
        label = "🎬 {}".format(escape(a["title"]))
        if a["premium"]:
            label = "💎 " + label
        rows.append([(label, "anime:{}".format(a["id"]))])

    nav = []
    if page > 0:
        nav.append(("⬅️", "cat:{}:{}".format(sort, page - 1)))
    nav.append(("{}/{}".format(page + 1, total_pages), "noop"))
    if page < total_pages - 1:
        nav.append(("➡️", "cat:{}:{}".format(sort, page + 1)))
    if nav:
        rows.append(nav)

    rows.append([("🏠 Asosiy menyu", "main_menu")])
    return inline(rows)


# ──────────────────────────────────────────────────────────────────────────────
# ANIME LIST (search results, genre)
# ──────────────────────────────────────────────────────────────────────────────

def anime_list_keyboard(anime_rows: list, back_callback: str = "main_menu") -> dict:
    rows = []
    for a in anime_rows:
        label = "🎬 {}".format(escape(a["title"]))
        if a["premium"]:
            label = "💎 " + label
        rows.append([(label, "anime:{}".format(a["id"]))])
    rows.append([("⬅️ Orqaga", back_callback)])
    return inline(rows)


# ──────────────────────────────────────────────────────────────────────────────
# ANIME PAGE
# ──────────────────────────────────────────────────────────────────────────────

def anime_page_keyboard(anime_id: int, is_fav: bool = False,
                        is_following: bool = False,
                        user_rating: int = 0,
                        back_callback: str = "cat:new:0") -> dict:
    fav_text = "❌ Sevimlilardan o'chirish" if is_fav else "⭐ Sevimlilarga"
    follow_text = "📌 Kuzatishni bekor qilish" if is_following else "📌 Kuzatish"
    rows = [
        [("▶️ Ko'rish", "watch:{}".format(anime_id))],
        [(fav_text, "favorite:{}".format(anime_id)),
         (follow_text, "follow:{}".format(anime_id))],
        [("⭐ Baholash", "rate_menu:{}".format(anime_id)),
         ("💬 Fikr qoldirish", "review:{}".format(anime_id))],
        [("📤 Ulashish", "share:{}".format(anime_id))],
        [("⬅️ Orqaga", back_callback)],
    ]
    return inline(rows)


# ──────────────────────────────────────────────────────────────────────────────
# EPISODES
# ──────────────────────────────────────────────────────────────────────────────

def episodes_keyboard(episodes: list, anime_id: int,
                      page: int = 0) -> dict:
    """Episode selection keyboard with pagination (20 per page)."""
    page_size = 20
    total = len(episodes)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_eps = episodes[start:start + page_size]

    rows = []
    row = []
    for ep in page_eps:
        label = "▶️ {}".format(ep["episode_number"])
        row.append((label, "episode:{}:{}".format(anime_id, ep["episode_number"])))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav = []
    if page > 0:
        nav.append(("⬅️", "ep_page:{}:{}".format(anime_id, page - 1)))
    nav.append(("{}/{}".format(page + 1, total_pages), "noop"))
    if page < total_pages - 1:
        nav.append(("➡️", "ep_page:{}:{}".format(anime_id, page + 1)))
    if len(nav) > 1:
        rows.append(nav)

    rows.append([("⬅️ Orqaga", "anime:{}".format(anime_id))])
    return inline(rows)


# ──────────────────────────────────────────────────────────────────────────────
# RATING
# ──────────────────────────────────────────────────────────────────────────────

def rating_keyboard(anime_id: int) -> dict:
    stars = [
        [("⭐ 1", "rate:{}:1".format(anime_id)),
         ("⭐⭐ 2", "rate:{}:2".format(anime_id))],
        [("⭐⭐⭐ 3", "rate:{}:3".format(anime_id)),
         ("⭐⭐⭐⭐ 4", "rate:{}:4".format(anime_id))],
        [("⭐⭐⭐⭐⭐ 5", "rate:{}:5".format(anime_id))],
        [("⬅️ Orqaga", "anime:{}".format(anime_id))],
    ]
    return inline(stars)


# ──────────────────────────────────────────────────────────────────────────────
# PREMIUM
# ──────────────────────────────────────────────────────────────────────────────

def premium_keyboard(prices: Optional[dict] = None) -> dict:
    prices = prices or PREMIUM_PRICES
    plan_labels = {
        "7": "7 kun", "30": "30 kun", "90": "90 kun", "365": "1 yil"
    }
    rows = []
    for days, price in sorted(prices.items(), key=lambda x: int(x[0])):
        label = "💎 Premium {} — {:,} UZS".format(
            plan_labels.get(days, "{} kun".format(days)), price
        ).replace(",", " ")
        rows.append([(label, "premium:{}".format(days))])
    rows.append([("⬅️ Orqaga", "main_menu")])
    return inline(rows)


def premium_confirm_keyboard(days: str, price: int) -> dict:
    return inline([
        [("✅ Sotib olish ({:,} UZS)".format(price).replace(",", " "),
          "premium_buy:{}".format(days))],
        [("⬅️ Orqaga", "premium_menu")],
    ])


# ──────────────────────────────────────────────────────────────────────────────
# CHANNELS
# ──────────────────────────────────────────────────────────────────────────────

def channels_keyboard(channels: list) -> dict:
    rows = []
    for ch in channels:
        username = ch["username"] or ""
        title = ch["title"] or "Kanal {}".format(ch["id"])
        if username:
            url = "https://t.me/{}".format(username.lstrip("@"))
            rows.append([("📢 {}".format(escape(title)), url, "url")])
        else:
            rows.append([("📢 {}".format(escape(title)), "noop")])
    rows.append([("✅ Tekshirish", "check_subscription")])
    return inline(rows)


# ──────────────────────────────────────────────────────────────────────────────
# FAVORITES
# ──────────────────────────────────────────────────────────────────────────────

def favorites_keyboard(anime_rows: list) -> dict:
    rows = []
    for a in anime_rows:
        rows.append([("🎬 {}".format(escape(a["title"])), "anime:{}".format(a["id"]))])
    rows.append([("⬅️ Orqaga", "main_menu")])
    return inline(rows)


# ──────────────────────────────────────────────────────────────────────────────
# WATCHLIST
# ──────────────────────────────────────────────────────────────────────────────

def watchlist_keyboard(anime_rows: list) -> dict:
    rows = []
    for a in anime_rows:
        rows.append([("📌 {}".format(escape(a["title"])), "anime:{}".format(a["id"]))])
    rows.append([("⬅️ Orqaga", "main_menu")])
    return inline(rows)


# ──────────────────────────────────────────────────────────────────────────────
# LEADERBOARD
# ──────────────────────────────────────────────────────────────────────────────

def leaderboard_keyboard(page: int, total_pages: int) -> dict:
    nav = []
    if page > 0:
        nav.append(("⬅️", "leaderboard:{}".format(page - 1)))
    nav.append(("{}/{}".format(page + 1, total_pages), "noop"))
    if page < total_pages - 1:
        nav.append(("➡️", "leaderboard:{}".format(page + 1)))
    rows = []
    if len(nav) > 1:
        rows.append(nav)
    rows.append([("⬅️ Orqaga", "main_menu")])
    return inline(rows)


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN PANEL
# ──────────────────────────────────────────────────────────────────────────────

def admin_menu_keyboard() -> dict:
    return inline([
        [("🎬 Anime", "admin:anime_menu"),
         ("📺 Qismlar", "admin:episode_menu")],
        [("👥 Foydalanuvchilar", "admin:users"),
         ("💎 Premium", "admin:premium_menu")],
        [("💰 To'lovlar", "admin:payments"),
         ("📢 Kanallar", "admin:channels")],
        [("📣 Broadcast", "admin:broadcast"),
         ("📢 Reklama", "admin:ads_menu")],
        [("📊 Statistika", "admin:analytics"),
         ("⭐ Sharhlar", "admin:reviews")],
        [("💾 Backup", "admin:backup"),
         ("📤 Export", "admin:export")],
        [("⚙️ Sozlamalar", "admin:settings"),
         ("🔧 Texnik ish", "admin:maintenance")],
        [("❌ Yopish", "admin:close")],
    ])


def admin_anime_menu_keyboard() -> dict:
    return inline([
        [("➕ Anime qo'shish", "admin:add_anime"),
         ("✏️ Tahrirlash", "admin:edit_anime")],
        [("🗑 O'chirish", "admin:delete_anime"),
         ("📋 Ro'yxat", "admin:list_anime")],
        [("⬅️ Orqaga", "admin:menu")],
    ])


def admin_episode_menu_keyboard() -> dict:
    return inline([
        [("➕ Qism qo'shish", "admin:add_episode"),
         ("🗑 Qism o'chirish", "admin:delete_episode")],
        [("⬅️ Orqaga", "admin:menu")],
    ])


def admin_user_keyboard(telegram_id: int) -> dict:
    return inline([
        [("💰 Balans qo'shish", "admin_balance:add:{}".format(telegram_id)),
         ("💸 Balans ayirish", "admin_balance:remove:{}".format(telegram_id))],
        [("💎 Premium berish", "admin_premium_give:{}".format(telegram_id)),
         ("💎 Premium o'chirish", "admin_premium_remove:{}".format(telegram_id))],
        [("🚫 Block", "admin_block:{}".format(telegram_id)),
         ("✅ Blokni ochish", "admin_unblock:{}".format(telegram_id))],
        [("⬅️ Orqaga", "admin:users")],
    ])


def admin_delete_confirm_keyboard(anime_id: int) -> dict:
    return inline([
        [("✅ Ha, o'chirish", "admin_delete_confirm:{}".format(anime_id)),
         ("❌ Yo'q", "admin:anime_menu")],
    ])


def admin_channels_keyboard(channels: list) -> dict:
    rows = []
    for ch in channels:
        rows.append([
            ("🗑 {}".format(escape(ch["title"] or ch["username"] or ch["telegram_channel_id"])),
             "admin_del_channel:{}".format(ch["id"])),
        ])
    rows.append([("➕ Kanal qo'shish", "admin_add_channel")])
    rows.append([("⬅️ Orqaga", "admin:menu")])
    return inline(rows)


def admin_premium_plans_keyboard(target_id: int) -> dict:
    plan_labels = {
        "7": "7 kun", "30": "30 kun", "90": "90 kun", "365": "1 yil"
    }
    rows = []
    for days in sorted(PREMIUM_PRICES.keys(), key=int):
        rows.append([(
            "💎 {}".format(plan_labels.get(days, "{} kun".format(days))),
            "admin_premium_plan:{}:{}".format(target_id, days)
        )])
    rows.append([("⬅️ Orqaga", "admin:users")])
    return inline(rows)


def admin_ads_keyboard(ads: list) -> dict:
    rows = []
    for ad in ads:
        status = "✅" if ad["active"] else "❌"
        rows.append([(
            "{} {} ({}x)".format(status, escape(ad["title"]), ad["views"]),
            "admin_ad:{}".format(ad["id"])
        )])
    rows.append([("➕ Reklama qo'shish", "admin:add_ad")])
    rows.append([("⬅️ Orqaga", "admin:menu")])
    return inline(rows)


def admin_ad_manage_keyboard(ad_id: int, active: int) -> dict:
    toggle_text = "❌ O'chirish" if active else "✅ Yoqish"
    return inline([
        [(toggle_text, "admin_ad_toggle:{}".format(ad_id)),
         ("🗑 O'chirish", "admin_ad_delete:{}".format(ad_id))],
        [("⬅️ Orqaga", "admin:ads_menu")],
    ])


def admin_review_keyboard(review_id: int) -> dict:
    return inline([
        [("✅ Tasdiqlash", "admin_review:approve:{}".format(review_id)),
         ("❌ Rad etish", "admin_review:reject:{}".format(review_id))],
        [("⬅️ Orqaga", "admin:reviews")],
    ])


def back_to_main() -> dict:
    return inline([[("⬅️ Orqaga", "main_menu")]])


def back_to_admin() -> dict:
    return inline([[("⬅️ Admin panelga", "admin:menu")]])


def yes_no_keyboard(yes_cb: str, no_cb: str) -> dict:
    return inline([
        [("✅ Ha", yes_cb), ("❌ Yo'q", no_cb)]
    ])
