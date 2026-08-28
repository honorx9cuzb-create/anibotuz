"""
keyboards.py — Inline and reply keyboard builders for Ani Telegram Bot.
All keyboards return dicts compatible with Telegram's reply_markup JSON.
"""

from config import PREMIUM_PRICES, PAGINATION_SIZE
from utils import escape


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def inline(buttons: list) -> dict:
    """Build InlineKeyboardMarkup from a 2D list of (text, callback_data) tuples."""
    keyboard = []
    for row in buttons:
        keyboard_row = []
        for item in row:
            if len(item) == 2:
                text, callback = item
                keyboard_row.append({"text": text, "callback_data": callback})
            elif len(item) == 3 and item[2] == "url":
                text, url, _ = item
                keyboard_row.append({"text": text, "url": url})
        keyboard.append(keyboard_row)
    return {"inline_keyboard": keyboard}


def reply(buttons: list, resize: bool = True, one_time: bool = False) -> dict:
    """Build ReplyKeyboardMarkup from a 2D list of text strings."""
    keyboard = [[{"text": t} for t in row] for row in buttons]
    return {
        "keyboard": keyboard,
        "resize_keyboard": resize,
        "one_time_keyboard": one_time,
    }


def remove_keyboard() -> dict:
    return {"remove_keyboard": True}


# ─── MAIN MENU ────────────────────────────────────────────────────────────────

def main_menu() -> dict:
    return reply([
        ["🔎 Anime qidirish", "🔢 ID orqali qidirish"],
        ["📚 Katalog", "⭐ Sevimlilar"],
        ["👤 Profil", "💰 Balans"],
        ["💎 Premium", "🎁 Referal"],
    ])


# ─── SEARCH RESULTS ───────────────────────────────────────────────────────────

def anime_list_keyboard(anime_rows: list, back_callback: str = "main_menu") -> dict:
    """Show a list of anime as inline buttons."""
    rows = []
    for a in anime_rows:
        label = f"🎬 {escape(a['title'])}"
        if a["premium"]:
            label = "💎 " + label
        rows.append([(label, f"anime:{a['id']}")])
    rows.append([("⬅️ Orqaga", back_callback)])
    return inline(rows)


# ─── ANIME PAGE ───────────────────────────────────────────────────────────────

def anime_page_keyboard(anime_id: int, is_fav: bool = False,
                        back_callback: str = "catalog:0") -> dict:
    fav_text = "❌ Sevimlilardan o'chirish" if is_fav else "⭐ Sevimlilarga"
    return inline([
        [("▶️ Ko'rish", f"watch:{anime_id}")],
        [(fav_text, f"favorite:{anime_id}")],
        [("⬅️ Orqaga", back_callback)],
    ])


# ─── EPISODES ─────────────────────────────────────────────────────────────────

def episodes_keyboard(episodes: list, anime_id: int) -> dict:
    """Build episode selection keyboard (max 5 per row)."""
    rows = []
    row = []
    for ep in episodes:
        label = f"▶️ {ep['episode_number']}-qism"
        row.append((label, f"episode:{anime_id}:{ep['episode_number']}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("⬅️ Orqaga", f"anime:{anime_id}")])
    return inline(rows)


# ─── PREMIUM ──────────────────────────────────────────────────────────────────

def premium_keyboard(prices: dict = None) -> dict:
    prices = prices or PREMIUM_PRICES
    rows = []
    plan_labels = {"7": "7 kun", "30": "30 kun", "365": "1 yil"}
    for days, price in prices.items():
        label = f"💎 Premium {plan_labels.get(days, days+' kun')} — {price:,} UZS"
        rows.append([(label, f"premium:{days}")])
    rows.append([("⬅️ Orqaga", "main_menu")])
    return inline(rows)


def premium_confirm_keyboard(days: str, price: int) -> dict:
    return inline([
        [(f"💎 Sotib olish ({price:,} UZS)", f"premium_buy:{days}")],
        [("⬅️ Orqaga", "premium_menu")],
    ])


# ─── CHANNELS ─────────────────────────────────────────────────────────────────

def channels_keyboard(channels: list) -> dict:
    rows = []
    for ch in channels:
        username = ch["username"] or ""
        title = ch["title"] or f"Kanal {ch['id']}"
        if username:
            url = f"https://t.me/{username.lstrip('@')}"
            rows.append([(f"📢 {escape(title)}", url, "url")])
        else:
            rows.append([(f"📢 {escape(title)}", f"noop")])
    rows.append([("✅ Tekshirish", "check_subscription")])
    return inline(rows)


# ─── CATALOG PAGINATION ───────────────────────────────────────────────────────

def catalog_keyboard(anime_rows: list, page: int, total_pages: int) -> dict:
    rows = []
    for a in anime_rows:
        label = f"🎬 {escape(a['title'])}"
        if a["premium"]:
            label = "💎 " + label
        rows.append([(label, f"anime:{a['id']}")])

    # Navigation row
    nav = []
    if page > 0:
        nav.append(("⬅️", f"catalog:{page - 1}"))
    nav.append((f"{page + 1}/{total_pages}", "noop"))
    if page < total_pages - 1:
        nav.append(("➡️", f"catalog:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([("🏠 Asosiy menyu", "main_menu")])
    return inline(rows)


# ─── FAVORITES ────────────────────────────────────────────────────────────────

def favorites_keyboard(anime_rows: list) -> dict:
    rows = []
    for a in anime_rows:
        rows.append([(f"🎬 {escape(a['title'])}", f"anime:{a['id']}")])
    rows.append([("⬅️ Orqaga", "main_menu")])
    return inline(rows)


# ─── ADMIN PANEL ─────────────────────────────────────────────────────────────

def admin_menu_keyboard() -> dict:
    return inline([
        [("➕ Anime qo'shish",  "admin:add_anime"),
         ("➕ Qism qo'shish",   "admin:add_episode")],
        [("✏️ Anime tahrirlash", "admin:edit_anime"),
         ("🗑 Anime o'chirish", "admin:delete_anime")],
        [("👥 Foydalanuvchilar", "admin:users"),
         ("📊 Statistika",      "admin:stats")],
        [("📢 Kanallar",        "admin:channels"),
         ("💰 Balans boshqaruvi", "admin:balance")],
        [("💎 Premium",         "admin:premium"),
         ("⚙️ Sozlamalar",      "admin:settings")],
        [("❌ Yopish",          "admin:close")],
    ])


def admin_user_keyboard(telegram_id: int) -> dict:
    return inline([
        [("💰 Balans qo'shish",  f"admin_balance:add:{telegram_id}"),
         ("💸 Balans ayirish",   f"admin_balance:remove:{telegram_id}")],
        [("💎 Premium berish",   f"admin_premium_give:{telegram_id}"),
         ("🚫 Block",            f"admin_block:{telegram_id}")],
        [("⬅️ Orqaga",           "admin:users")],
    ])


def admin_delete_confirm_keyboard(anime_id: int) -> dict:
    return inline([
        [("✅ Ha, o'chirish", f"admin_delete_confirm:{anime_id}"),
         ("❌ Yo'q",          "admin:delete_anime")],
    ])


def admin_channels_keyboard(channels: list) -> dict:
    rows = []
    for ch in channels:
        rows.append([
            (f"🗑 {escape(ch['title'] or ch['username'])}", f"admin_del_channel:{ch['id']}"),
        ])
    rows.append([("➕ Kanal qo'shish", "admin_add_channel")])
    rows.append([("⬅️ Orqaga", "admin:menu")])
    return inline(rows)


def admin_premium_plans_keyboard() -> dict:
    plan_labels = {"7": "7 kun", "30": "30 kun", "365": "1 yil"}
    rows = []
    for days in PREMIUM_PRICES:
        rows.append([(f"💎 {plan_labels.get(days, days+' kun')}", f"admin_premium_plan:{days}")])
    rows.append([("⬅️ Orqaga", "admin:menu")])
    return inline(rows)


def back_to_main() -> dict:
    return inline([[("⬅️ Orqaga", "main_menu")]])


def back_to_admin() -> dict:
    return inline([[("⬅️ Admin panelga", "admin:menu")]])


def yes_no_keyboard(yes_cb: str, no_cb: str) -> dict:
    return inline([[(f"✅ Ha", yes_cb), (f"❌ Yo'q", no_cb)]])
