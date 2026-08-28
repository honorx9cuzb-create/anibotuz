"""
admin.py — Complete Admin Panel logic for ANIME BOT PRO v4.
All admin state is stored in a simple in-memory dict per admin user.
Python 3.9 compatible. Standard library only.
"""

import logging
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Optional

from config import ADMIN_IDS, BROADCAST_DELAY, PAGINATION_SIZE, BACKUPS_DIR, EXPORTS_DIR
import database as db
import api
import keyboards as kb
from utils import escape, format_currency, format_premium_until, is_premium_active, safe_int

logger = logging.getLogger(__name__)

# In-memory admin session state: {telegram_id: {step, data, ts}}
admin_sessions: dict = {}
SESSION_TIMEOUT = 900  # 15 minutes


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


def get_session(telegram_id: int) -> dict:
    sess = admin_sessions.get(telegram_id, {})
    # Expire stale sessions
    if sess and time.time() - sess.get("ts", 0) > SESSION_TIMEOUT:
        admin_sessions[telegram_id] = {}
        return {}
    return sess


def clear_session(telegram_id: int):
    admin_sessions[telegram_id] = {}


def set_session(telegram_id: int, **kwargs):
    sess = get_session(telegram_id)
    sess.update(kwargs)
    sess["ts"] = time.time()
    admin_sessions[telegram_id] = sess


# ─── ADMIN MENU ───────────────────────────────────────────────────────────────

def show_admin_menu(chat_id: int):
    api.send_message(
        chat_id,
        "👑 <b>ADMIN PANEL</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        reply_markup=kb.admin_menu_keyboard(),
    )


# ─── ANIME MENU ───────────────────────────────────────────────────────────────

def show_anime_menu(chat_id: int):
    api.send_message(
        chat_id,
        "🎬 <b>Anime boshqaruvi</b>\n\nAmalni tanlang:",
        reply_markup=kb.admin_anime_menu_keyboard(),
    )


def show_episode_menu(chat_id: int):
    api.send_message(
        chat_id,
        "📺 <b>Qism boshqaruvi</b>\n\nAmalni tanlang:",
        reply_markup=kb.admin_episode_menu_keyboard(),
    )


def list_anime(chat_id: int, page: int = 0):
    page_size = 10
    anime_list = db.get_anime_catalog(offset=page * page_size, limit=page_size, sort="new")
    total = db.get_anime_count()
    total_pages = max(1, (total + page_size - 1) // page_size)

    if not anime_list:
        api.send_message(chat_id, "🎬 Hali anime qo'shilmagan.",
                         reply_markup=kb.admin_menu_keyboard())
        return

    lines = []
    for a in anime_list:
        premium_mark = "💎" if a["premium"] else "  "
        lines.append("{} <code>{}</code> — {}".format(
            premium_mark, a["id"], escape(a["title"])))

    text = "🎬 <b>Anime ro'yxati</b> ({}/{})\n\n".format(page + 1, total_pages)
    text += "\n".join(lines)

    nav_rows = []
    nav = []
    if page > 0:
        nav.append(("⬅️ Oldingi", "admin:list_anime_{}".format(page - 1)))
    if page < total_pages - 1:
        nav.append(("Keyingi ➡️", "admin:list_anime_{}".format(page + 1)))
    if nav:
        nav_rows.append(nav)
    nav_rows.append([("⬅️ Orqaga", "admin:anime_menu")])

    api.send_message(chat_id, text, reply_markup=kb.inline(nav_rows))


# ─── ANALYTICS ────────────────────────────────────────────────────────────────

def show_analytics(chat_id: int):
    users_total = db.get_users_count()
    users_today = db.get_new_users_today()
    active_today = db.get_active_users_today()
    anime_count = db.get_anime_count()
    episodes_count = db.get_episodes_count()
    premium_count = db.get_premium_users_count()
    total_views = db.get_total_views()
    total_favs = db.get_total_favorites()
    total_ratings = db.get_total_ratings()
    revenue = db.get_total_revenue()

    top_anime = db.get_top_anime(limit=5)
    top_lines = []
    for i, a in enumerate(top_anime, 1):
        top_lines.append("  {}. {} — <b>{}</b> ko'rish".format(
            i, escape(a["title"]), a["views"] or 0))

    top_text = "\n".join(top_lines) if top_lines else "  Hali anime yo'q"

    text = (
        "📊 <b>STATISTIKA</b>\n\n"
        "👥 Jami foydalanuvchilar: <b>{}</b>\n"
        "📅 Bugun yangi: <b>{}</b>\n"
        "🟢 Bugun aktiv: <b>{}</b>\n"
        "💎 Premium foydalanuvchilar: <b>{}</b>\n\n"
        "🎬 Anime: <b>{}</b>\n"
        "📺 Qismlar: <b>{}</b>\n"
        "👁 Jami ko'rishlar: <b>{}</b>\n"
        "⭐ Sevimlilar: <b>{}</b>\n"
        "⭐ Baholashlar: <b>{}</b>\n\n"
        "💰 Jami daromad: <b>{}</b>\n\n"
        "🔥 <b>Top Anime:</b>\n{}"
    ).format(
        users_total, users_today, active_today, premium_count,
        anime_count, episodes_count, total_views, total_favs, total_ratings,
        format_currency(revenue),
        top_text,
    )
    api.send_message(chat_id, text, reply_markup=kb.back_to_admin())


# ─── BACKUP ───────────────────────────────────────────────────────────────────

def do_backup(chat_id: int):
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_filename = "anime_{}.db".format(ts)
    backup_path = os.path.join(BACKUPS_DIR, backup_filename)

    os.makedirs(BACKUPS_DIR, exist_ok=True)

    ok = db.create_backup(backup_path)
    if ok:
        size_kb = os.path.getsize(backup_path) // 1024
        logger.info("Admin {} created backup: {}".format(chat_id, backup_path))
        api.send_message(
            chat_id,
            "💾 <b>Backup muvaffaqiyatli yaratildi!</b>\n\n"
            "📁 Fayl: <code>{}</code>\n"
            "📦 Hajm: <b>{} KB</b>".format(backup_filename, size_kb),
            reply_markup=kb.back_to_admin(),
        )
    else:
        api.send_message(
            chat_id,
            "❌ Backup yaratishda xatolik yuz berdi.\nLoglarga qarang.",
            reply_markup=kb.back_to_admin(),
        )


# ─── EXPORT ───────────────────────────────────────────────────────────────────

def do_export(chat_id: int):
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    results = []
    exports = [
        ("users_{}.csv".format(ts), db.export_users_csv),
        ("anime_{}.csv".format(ts), db.export_anime_csv),
        ("payments_{}.csv".format(ts), db.export_payments_csv),
    ]

    for filename, export_fn in exports:
        path = os.path.join(EXPORTS_DIR, filename)
        ok = export_fn(path)
        if ok:
            size_kb = os.path.getsize(path) // 1024
            results.append("✅ {} ({} KB)".format(filename, size_kb))
        else:
            results.append("⚠️ {} — ma'lumot yo'q".format(filename))

    logger.info("Admin {} ran export.".format(chat_id))
    api.send_message(
        chat_id,
        "📤 <b>Export yakunlandi!</b>\n\n" + "\n".join(results),
        reply_markup=kb.back_to_admin(),
    )


# ─── PREMIUM MENU ─────────────────────────────────────────────────────────────

def show_premium_menu(chat_id: int):
    premium_count = db.get_premium_users_count()
    text = (
        "💎 <b>Premium boshqaruvi</b>\n\n"
        "💎 Aktiv premium foydalanuvchilar: <b>{}</b>\n\n"
        "Foydalanuvchiga premium berish uchun\n"
        "avval '👥 Foydalanuvchilar' bo'limidan foydalanuvchini toping."
    ).format(premium_count)
    api.send_message(chat_id, text, reply_markup=kb.back_to_admin())


# ─── PAYMENTS ─────────────────────────────────────────────────────────────────

def show_payments(chat_id: int):
    total_revenue = db.get_total_revenue()
    payments_count = db.get_payments_count()

    text = (
        "💰 <b>To'lovlar</b>\n\n"
        "✅ Muvaffaqiyatli to'lovlar: <b>{}</b>\n"
        "💰 Jami daromad: <b>{}</b>\n\n"
        "<i>To'lov tarixi SQLite bazasida saqlanadi.</i>"
    ).format(payments_count, format_currency(total_revenue))
    api.send_message(chat_id, text, reply_markup=kb.back_to_admin())


# ─── REVIEWS ──────────────────────────────────────────────────────────────────

def show_pending_reviews(chat_id: int):
    reviews = db.get_pending_reviews(limit=10)
    if not reviews:
        api.send_message(
            chat_id,
            "⭐ <b>Sharhlar</b>\n\nTasdiqlash kutayotgan sharhlar yo'q.",
            reply_markup=kb.back_to_admin(),
        )
        return

    for review in reviews:
        user_name = escape(review["first_name"] or "Foydalanuvchi")
        anime_title = escape(review["anime_title"] or "Noma'lum")
        review_text = escape(review["text"][:500])
        text = (
            "⭐ <b>Sharh</b>\n\n"
            "🎬 Anime: <b>{}</b>\n"
            "👤 Foydalanuvchi: {}\n"
            "📅 Sana: {}\n\n"
            "💬 {}"
        ).format(anime_title, user_name,
                 (review["created_at"] or "")[:10], review_text)
        api.send_message(
            chat_id, text,
            reply_markup=kb.admin_review_keyboard(review["id"]),
        )

    logger.info("Admin {} viewed {} pending reviews.".format(chat_id, len(reviews)))


# ─── ADVERTISEMENTS ───────────────────────────────────────────────────────────

def show_ads_list(chat_id: int):
    ads = db.get_all_ads()
    if not ads:
        api.send_message(
            chat_id,
            "📢 <b>Reklamalar</b>\n\nHali reklama qo'shilmagan.",
            reply_markup=kb.inline([
                [("➕ Reklama qo'shish", "admin:add_ad")],
                [("⬅️ Orqaga", "admin:menu")],
            ]),
        )
        return
    api.send_message(
        chat_id,
        "📢 <b>Reklamalar ro'yxati</b>",
        reply_markup=kb.admin_ads_keyboard(ads),
    )


def show_ad_detail(chat_id: int, ad_id: int):
    ad = _get_ad(ad_id)
    if not ad:
        api.send_message(chat_id, "❌ Reklama topilmadi.",
                         reply_markup=kb.admin_menu_keyboard())
        return
    status = "✅ Aktiv" if ad["active"] else "❌ Nofaol"
    text = (
        "📢 <b>Reklama #{}</b>\n\n"
        "📌 Nomi: <b>{}</b>\n"
        "📝 Matn: {}\n"
        "🔘 Tugma: {} → {}\n"
        "📅 Boshlanish: {}\n"
        "📅 Tugash: {}\n"
        "📊 Ko'rishlar: <b>{}</b>\n"
        "👆 Bosishlar: <b>{}</b>\n"
        "💡 Status: {}"
    ).format(
        ad_id,
        escape(ad["title"] or ""),
        escape(ad["text"][:200] or ""),
        escape(ad["button_text"] or "Yo'q"),
        escape(ad["button_url"] or "Yo'q"),
        ad["start_at"] or "Har doim",
        ad["end_at"] or "Cheksiz",
        ad["views"] or 0,
        ad["clicks"] or 0,
        status,
    )
    api.send_message(chat_id, text,
                     reply_markup=kb.admin_ad_manage_keyboard(ad_id, ad["active"]))


def _get_ad(ad_id: int):
    """Helper to get a single ad."""
    import sqlite3
    try:
        conn = db.get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM advertisements WHERE id = ?", (ad_id,))
        return c.fetchone()
    except Exception:
        return None


ADD_AD_STEPS = [
    ("title",       "Reklama nomini kiriting:"),
    ("text",        "Reklama matnini kiriting (HTML qo'llab-quvvatlanadi):"),
    ("button_text", "Tugma matnini kiriting (yo'q bo'lsa — 'yo'q' yozing):"),
    ("button_url",  "Tugma URL sini kiriting (yo'q bo'lsa — 'yo'q' yozing):"),
    ("start_at",    "Boshlanish sanasini kiriting (YYYY-MM-DD yoki 'yo'q'):"),
    ("end_at",      "Tugash sanasini kiriting (YYYY-MM-DD yoki 'yo'q'):"),
]


def start_add_ad(chat_id: int):
    set_session(chat_id, step="add_ad_0", data={})
    api.send_message(
        chat_id,
        "📢 <b>Reklama qo'shish</b>\n\n{}".format(ADD_AD_STEPS[0][1]),
        reply_markup=kb.back_to_admin(),
    )


def handle_add_ad_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    step_key = sess.get("step", "")
    if not step_key.startswith("add_ad_"):
        return False

    step_index = safe_int(step_key.split("_")[-1])
    field_name, _ = ADD_AD_STEPS[step_index]
    data = sess.get("data", {})

    empty_fields = {"button_text", "button_url", "start_at", "end_at"}
    if field_name in empty_fields and text.strip().lower() in ("yo'q", "yoq", "no", "-", ""):
        data[field_name] = ""
    elif field_name in ("start_at", "end_at") and text.strip().lower() not in ("yo'q", "yoq", "no", "-"):
        # Validate date format
        try:
            datetime.strptime(text.strip(), "%Y-%m-%d")
            data[field_name] = text.strip() + " 00:00:00"
        except ValueError:
            api.send_message(chat_id,
                             "❌ Noto'g'ri sana formati. YYYY-MM-DD formatida kiriting:")
            return True
    else:
        data[field_name] = text.strip()

    sess["data"] = data
    next_step = step_index + 1

    if next_step < len(ADD_AD_STEPS):
        set_session(chat_id, step="add_ad_{}".format(next_step), data=data)
        api.send_message(chat_id, ADD_AD_STEPS[next_step][1],
                         reply_markup=kb.back_to_admin())
        return True
    else:
        try:
            ad_id = db.create_ad(
                title=data.get("title", ""),
                text=data.get("text", ""),
                button_text=data.get("button_text", ""),
                button_url=data.get("button_url", ""),
                image=data.get("image", ""),
                start_at=data.get("start_at", ""),
                end_at=data.get("end_at", ""),
            )
            clear_session(chat_id)
            logger.info("Admin {} created ad id={}".format(chat_id, ad_id))
            api.send_message(
                chat_id,
                "✅ <b>Reklama muvaffaqiyatli qo'shildi!</b>\n🆔 ID: <code>{}</code>".format(
                    ad_id),
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as exc:
            logger.error("Failed to create ad: {}".format(exc))
            api.send_message(chat_id, "❌ Xatolik: {}".format(escape(str(exc))),
                             reply_markup=kb.admin_menu_keyboard())
        return False


# ─── MAINTENANCE ──────────────────────────────────────────────────────────────

def toggle_maintenance(chat_id: int):
    current = db.is_maintenance_mode()
    new_state = not current
    db.set_maintenance_mode(new_state)
    status = "✅ Yoqildi" if new_state else "❌ O'chirildi"
    logger.info("Admin {} toggled maintenance mode: {}".format(chat_id, new_state))
    api.send_message(
        chat_id,
        "🔧 <b>Texnik ish rejimi: {}</b>\n\n{}".format(
            status,
            "Normal foydalanuvchilar botni ishlata olmaydi." if new_state
            else "Barcha foydalanuvchilar uchun bot ochiq."),
        reply_markup=kb.admin_menu_keyboard(),
    )


# ─── STATISTICS (alias for show_analytics) ────────────────────────────────────

def show_stats(chat_id: int):
    show_analytics(chat_id)


# ─── ADD ANIME FLOW ───────────────────────────────────────────────────────────

ADD_ANIME_STEPS = [
    ("title",          "Anime nomini kiriting (uzbekcha):"),
    ("original_title", "Anime asl nomini kiriting (yaponcha/inglizcha, yo'q bo'lsa — kiritmang):"),
    ("description",    "Anime tavsifini kiriting:"),
    ("genre",          "Janrini kiriting (masalan: Action, Romance, Comedy):"),
    ("year",           "Yilini kiriting (masalan: 2002):"),
    ("country",        "Mamlakatini kiriting (masalan: Japan):"),
    ("language",       "Tilini kiriting (masalan: O'zbek):"),
    ("poster",         "Poster URL yoki file_id kiriting (yo'q bo'lsa — 'yo'q' yozing):"),
    ("premium",        "Premium animemi? (ha / yo'q):"),
    ("status",         "Status: ongoing yoki completed?"),
]


def start_add_anime(chat_id: int):
    set_session(chat_id, step="add_anime_0", data={})
    api.send_message(
        chat_id,
        "➕ <b>Anime qo'shish</b>\n\n{}".format(ADD_ANIME_STEPS[0][1]),
        reply_markup=kb.reply([["❌ Bekor qilish"]]),
    )


def handle_add_anime_step(chat_id: int, text: str) -> bool:
    """Process one step of add_anime flow. Returns True while still in flow."""
    sess = get_session(chat_id)
    step_key = sess.get("step", "")
    if not step_key.startswith("add_anime_"):
        return False

    step_index = safe_int(step_key.split("_")[-1])
    if step_index >= len(ADD_ANIME_STEPS):
        return False

    field_name, _ = ADD_ANIME_STEPS[step_index]
    data = sess.get("data", {})

    if field_name == "year":
        val = safe_int(text, 0)
        if val < 1900 or val > 2100:
            api.send_message(chat_id, "❌ Noto'g'ri yil. Qaytadan kiriting:")
            return True
        data[field_name] = val
    elif field_name == "premium":
        data[field_name] = 1 if text.strip().lower() in ("ha", "yes", "1", "true") else 0
    elif field_name == "status":
        data[field_name] = "completed" if "compl" in text.lower() else "ongoing"
    elif field_name in ("poster", "original_title"):
        val = text.strip()
        data[field_name] = "" if val.lower() in ("yo'q", "yoq", "no", "-", "") else val
    else:
        data[field_name] = text.strip()

    sess["data"] = data
    next_step = step_index + 1

    if next_step < len(ADD_ANIME_STEPS):
        set_session(chat_id, step="add_anime_{}".format(next_step), data=data)
        api.send_message(chat_id, ADD_ANIME_STEPS[next_step][1],
                         reply_markup=kb.reply([["❌ Bekor qilish"]]))
        return True
    else:
        # Save to DB — all required fields
        try:
            anime_id = db.create_anime(
                title=data.get("title", ""),
                original_title=data.get("original_title", ""),
                description=data.get("description", ""),
                genre=data.get("genre", ""),
                year=safe_int(data.get("year", 0)),
                country=data.get("country", ""),
                language=data.get("language", ""),
                poster=data.get("poster", ""),
                premium=data.get("premium", 0),
                status=data.get("status", "ongoing"),
                featured=0,
            )
            clear_session(chat_id)
            logger.info("Admin {} created anime id={} title={}".format(
                chat_id, anime_id, data.get("title")))
            api.send_message(
                chat_id,
                "✅ <b>Anime muvaffaqiyatli qo'shildi!</b>\n\n"
                "🎬 Nomi: <b>{}</b>\n"
                "🆔 ID: <code>{}</code>".format(
                    escape(data.get("title", "")), anime_id),
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as exc:
            logger.error("Failed to create anime: {}".format(exc))
            api.send_message(
                chat_id,
                "❌ Xatolik yuz berdi: {}".format(escape(str(exc))),
                reply_markup=kb.admin_menu_keyboard(),
            )
        return False


# ─── ADD EPISODE FLOW ─────────────────────────────────────────────────────────

def start_add_episode(chat_id: int):
    set_session(chat_id, step="add_episode_anime_id", data={})
    api.send_message(
        chat_id,
        "➕ <b>Qism qo'shish</b>\n\nAnime ID sini kiriting:",
        reply_markup=kb.reply([["❌ Bekor qilish"]]),
    )


def handle_add_episode_step(chat_id: int, text: str,
                             video_file_id: Optional[str] = None) -> bool:
    sess = get_session(chat_id)
    step = sess.get("step", "")
    data = sess.get("data", {})

    if step == "add_episode_anime_id":
        anime_id = safe_int(text.strip())
        anime = db.get_anime(anime_id)
        if not anime:
            api.send_message(chat_id, "❌ Anime topilmadi. ID ni qayta kiriting:")
            return True
        data["anime_id"] = anime_id
        set_session(chat_id, step="add_episode_number", data=data)
        api.send_message(
            chat_id,
            "🎬 Anime: <b>{}</b>\n\nQism raqamini kiriting:".format(
                escape(anime["title"])))
        return True

    elif step == "add_episode_number":
        ep_num = safe_int(text.strip())
        if ep_num <= 0:
            api.send_message(chat_id, "❌ Noto'g'ri qism raqami. Qaytadan kiriting:")
            return True
        # Check duplicate
        existing = db.get_episode_by_number(data.get("anime_id", 0), ep_num)
        if existing:
            api.send_message(
                chat_id,
                "⚠️ Bu raqamdagi qism allaqachon mavjud ({}-qism).\n"
                "Boshqa raqam kiriting:".format(ep_num))
            return True
        data["episode_number"] = ep_num
        set_session(chat_id, step="add_episode_title", data=data)
        api.send_message(
            chat_id,
            "Qism sarlavhasini kiriting (yo'q bo'lsa — 'yo'q' yozing):")
        return True

    elif step == "add_episode_title":
        val = text.strip()
        data["title"] = "" if val.lower() in ("yo'q", "yoq", "no", "-") else val
        set_session(chat_id, step="add_episode_video", data=data)
        api.send_message(
            chat_id,
            "📹 Endi videoni yuboring (Telegram video xabari sifatida):\n"
            "<i>Video faylni document sifatida emas, video sifatida yuboring.</i>")
        return True

    elif step == "add_episode_video":
        if not video_file_id:
            api.send_message(
                chat_id,
                "❌ Iltimos, video faylni yuboring (document emas, to'g'ridan-to'g'ri video):")
            return True

        try:
            ep_id = db.create_episode(
                anime_id=data["anime_id"],
                episode_number=data["episode_number"],
                title=data.get("title", ""),
                video_file_id=video_file_id,
            )
            clear_session(chat_id)
            logger.info(
                "Admin {} added episode {} to anime {}, ep_id={}".format(
                    chat_id, data["episode_number"], data["anime_id"], ep_id))

            # Queue notifications for followers
            _notify_followers(data["anime_id"], ep_id,
                               data["episode_number"], data.get("title", ""))

            api.send_message(
                chat_id,
                "✅ <b>Qism muvaffaqiyatli qo'shildi!</b>\n\n"
                "📺 Qism: <b>{}-qism</b>\n"
                "🎬 Anime ID: <code>{}</code>".format(
                    data["episode_number"], data["anime_id"]),
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as exc:
            logger.error("Failed to create episode: {}".format(exc))
            api.send_message(
                chat_id,
                "❌ Xatolik yuz berdi: {}".format(escape(str(exc))),
                reply_markup=kb.admin_menu_keyboard(),
            )
        return False

    return False


def _notify_followers(anime_id: int, episode_id: int,
                       episode_number: int, episode_title: str):
    """Queue new episode notifications for all followers of this anime."""
    try:
        anime = db.get_anime(anime_id)
        if not anime:
            return
        followers = db.get_anime_followers(anime_id)
        if not followers:
            return

        from config import BOT_USERNAME
        deep_link = "https://t.me/{}?start=episode_{}_{}" .format(
            BOT_USERNAME, anime_id, episode_number)

        title_suffix = ""
        if episode_title:
            title_suffix = ": {}".format(escape(episode_title))

        message = (
            "🔔 <b>Yangi qism!</b>\n\n"
            "🎬 <b>{}</b>\n"
            "📺 <b>{}-qism</b>{}\n\n"
            "<a href='{}'>▶️ Ko'rish</a>"
        ).format(
            escape(anime["title"]),
            episode_number,
            title_suffix,
            deep_link,
        )

        for follower in followers:
            db.queue_notification(
                user_id=follower["telegram_id"],
                message=message,
                anime_id=anime_id,
                episode_id=episode_id,
            )

        logger.info("Queued {} notifications for anime {} episode {}".format(
            len(followers), anime_id, episode_number))

    except Exception as exc:
        logger.error("_notify_followers error: {}".format(exc))


# ─── EDIT ANIME FLOW ──────────────────────────────────────────────────────────

def start_edit_anime(chat_id: int):
    set_session(chat_id, step="edit_anime_id", data={})
    api.send_message(
        chat_id,
        "✏️ <b>Anime tahrirlash</b>\n\nAnime ID sini kiriting:",
        reply_markup=kb.reply([["❌ Bekor qilish"]]),
    )


def handle_edit_anime_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    step = sess.get("step", "")
    data = sess.get("data", {})

    if step == "edit_anime_id":
        anime_id = safe_int(text.strip())
        anime = db.get_anime(anime_id)
        if not anime:
            api.send_message(chat_id, "❌ Anime topilmadi. Qayta kiriting:")
            return True
        data["anime_id"] = anime_id
        set_session(chat_id, step="edit_anime_field", data=data)
        valid_fields = "title, original_title, description, genre, year, country, language, premium, status, featured"
        api.send_message(
            chat_id,
            "🎬 <b>{}</b>\n\n"
            "Qaysi maydonni tahrirlashni xohlaysiz?\n"
            "Kiriting: <code>{}</code>".format(
                escape(anime["title"]), valid_fields),
        )
        return True

    elif step == "edit_anime_field":
        valid = {"title", "original_title", "description", "genre", "year",
                 "country", "language", "premium", "status", "featured"}
        field = text.strip().lower()
        if field not in valid:
            api.send_message(
                chat_id,
                "❌ Noto'g'ri maydon. Quyidagilardan birini kiriting:\n"
                "<code>title, original_title, description, genre, year, "
                "country, language, premium, status, featured</code>")
            return True
        data["field"] = field
        set_session(chat_id, step="edit_anime_value", data=data)
        api.send_message(chat_id,
                         "✏️ Yangi qiymatni kiriting (<b>{}</b>):".format(field))
        return True

    elif step == "edit_anime_value":
        field = data.get("field")
        value = text.strip()
        update = {}
        if field == "year":
            update[field] = safe_int(value, 0)
        elif field in ("premium", "featured"):
            update[field] = 1 if value.lower() in ("ha", "yes", "1", "true") else 0
        else:
            update[field] = value

        try:
            db.update_anime(data["anime_id"], **update)
            clear_session(chat_id)
            logger.info("Admin {} edited anime {} field={}".format(
                chat_id, data["anime_id"], field))
            api.send_message(
                chat_id,
                "✅ Anime muvaffaqiyatli yangilandi!\n"
                "🆔 ID: <code>{}</code>".format(data["anime_id"]),
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as exc:
            logger.error("Failed to edit anime: {}".format(exc))
            api.send_message(chat_id,
                             "❌ Xatolik: {}".format(escape(str(exc))))
        return False

    return False


# ─── DELETE ANIME ─────────────────────────────────────────────────────────────

def start_delete_anime(chat_id: int):
    set_session(chat_id, step="delete_anime_id", data={})
    api.send_message(
        chat_id,
        "🗑 <b>Anime o'chirish</b>\n\nAnime ID sini kiriting:",
        reply_markup=kb.reply([["❌ Bekor qilish"]]),
    )


def handle_delete_anime_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    step = sess.get("step", "")

    if step == "delete_anime_id":
        anime_id = safe_int(text.strip())
        anime = db.get_anime(anime_id)
        if not anime:
            api.send_message(chat_id, "❌ Anime topilmadi. Qayta kiriting:")
            return True
        set_session(chat_id, step="delete_anime_confirm",
                    data={"anime_id": anime_id})
        api.send_message(
            chat_id,
            "⚠️ <b>Rostdan ham o'chirmoqchimisiz?</b>\n\n"
            "🎬 <b>{}</b>\n"
            "🆔 ID: <code>{}</code>\n\n"
            "Bu amal barcha qismlar va sevimlilarni ham o'chiradi!".format(
                escape(anime["title"]), anime_id),
            reply_markup=kb.admin_delete_confirm_keyboard(anime_id),
        )
        return True

    return False


def confirm_delete_anime(chat_id: int, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, "❌ Anime allaqachon o'chirilgan.",
                         reply_markup=kb.admin_menu_keyboard())
        clear_session(chat_id)
        return

    title = anime["title"]
    db.delete_anime(anime_id)
    clear_session(chat_id)
    logger.info("Admin {} deleted anime id={} title={}".format(
        chat_id, anime_id, title))
    api.send_message(
        chat_id,
        "✅ <b>{}</b> muvaffaqiyatli o'chirildi.".format(escape(title)),
        reply_markup=kb.admin_menu_keyboard(),
    )


# ─── DELETE EPISODE FLOW ──────────────────────────────────────────────────────

def start_delete_episode(chat_id: int):
    set_session(chat_id, step="delete_episode_anime_id", data={})
    api.send_message(
        chat_id,
        "🗑 <b>Qism o'chirish</b>\n\nAnime ID sini kiriting:",
        reply_markup=kb.reply([["❌ Bekor qilish"]]),
    )


def handle_delete_episode_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    step = sess.get("step", "")
    data = sess.get("data", {})

    if step == "delete_episode_anime_id":
        anime_id = safe_int(text.strip())
        anime = db.get_anime(anime_id)
        if not anime:
            api.send_message(chat_id, "❌ Anime topilmadi. Qayta kiriting:")
            return True
        episodes = db.get_episodes(anime_id)
        if not episodes:
            api.send_message(
                chat_id,
                "❌ Bu animeda qism yo'q.",
                reply_markup=kb.admin_menu_keyboard())
            clear_session(chat_id)
            return False
        data["anime_id"] = anime_id
        set_session(chat_id, step="delete_episode_number", data=data)

        ep_list = ", ".join(str(e["episode_number"]) for e in episodes[:20])
        api.send_message(
            chat_id,
            "🎬 Anime: <b>{}</b>\n\n"
            "Mavjud qismlar: {}\n\n"
            "O'chirmoqchi bo'lgan qism raqamini kiriting:".format(
                escape(anime["title"]), ep_list))
        return True

    elif step == "delete_episode_number":
        ep_num = safe_int(text.strip())
        anime_id = data.get("anime_id", 0)
        episode = db.get_episode_by_number(anime_id, ep_num)
        if not episode:
            api.send_message(chat_id,
                             "❌ {} raqamli qism topilmadi. Qayta kiriting:".format(
                                 ep_num))
            return True
        db.delete_episode(episode["id"])
        clear_session(chat_id)
        logger.info("Admin {} deleted episode {} from anime {}".format(
            chat_id, ep_num, anime_id))
        api.send_message(
            chat_id,
            "✅ <b>{}-qism</b> muvaffaqiyatli o'chirildi.".format(ep_num),
            reply_markup=kb.admin_menu_keyboard(),
        )
        return False

    return False


# ─── USER MANAGEMENT ──────────────────────────────────────────────────────────

def start_user_search(chat_id: int):
    set_session(chat_id, step="search_user_id", data={})
    api.send_message(
        chat_id,
        "👥 <b>Foydalanuvchi qidirish</b>\n\nTelegram ID sini kiriting:",
        reply_markup=kb.reply([["❌ Bekor qilish"]]),
    )


def handle_user_search_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    if sess.get("step") != "search_user_id":
        return False

    target_id = safe_int(text.strip())
    user = db.get_user(target_id)
    if not user:
        api.send_message(chat_id, "❌ Foydalanuvchi topilmadi. Qayta kiriting:")
        return True

    premium_status = "✅ Aktiv" if is_premium_active(user["premium_until"]) else "❌ Yo'q"
    uname_display = ("@" + escape(user["username"])) if user["username"] else "Yo'q"
    fname_display = escape(user["first_name"] or "Noma'lum")
    blocked_status = "🚫 Ha" if user["is_blocked"] else "✅ Yo'q"

    text_msg = (
        "👤 <b>Foydalanuvchi ma'lumotlari</b>\n\n"
        "🆔 ID: <code>{}</code>\n"
        "👤 Username: {}\n"
        "📛 Ism: {}\n"
        "💰 Balans: <b>{}</b>\n"
        "⭐ XP: <b>{}</b> | Daraja: <b>{}</b>\n"
        "💎 Premium: {}\n"
        "📅 Premium tugash: {}\n"
        "👥 Referallar: <b>{}</b>\n"
        "🚫 Bloklangan: {}\n"
        "📆 Ro'yxatdan: {}"
    ).format(
        user["telegram_id"],
        uname_display,
        fname_display,
        format_currency(user["balance"]),
        user["xp"] or 0,
        user["level"] or 1,
        premium_status,
        format_premium_until(user["premium_until"]),
        user["referral_count"] or 0,   # ← FIXED: was user["referrals"]
        blocked_status,
        (user["created_at"] or "")[:10],
    )
    clear_session(chat_id)
    api.send_message(
        chat_id, text_msg,
        reply_markup=kb.admin_user_keyboard(user["telegram_id"]),
    )
    return False


# ─── ADMIN BALANCE FLOW ───────────────────────────────────────────────────────

def start_admin_balance(chat_id: int, action: str, target_id: int):
    """action: 'add' or 'remove'"""
    set_session(chat_id, step="admin_balance_{}".format(action),
                data={"target_id": target_id})
    verb = "qo'shish" if action == "add" else "ayirish"
    api.send_message(
        chat_id,
        "💰 Foydalanuvchi {} uchun balans {}.\n\nSummani kiriting (UZS):".format(
            target_id, verb))


def handle_admin_balance_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    step = sess.get("step", "")
    data = sess.get("data", {})

    if step in ("admin_balance_add", "admin_balance_remove"):
        amount = safe_int(text.strip())
        if amount <= 0:
            api.send_message(chat_id, "❌ Noto'g'ri summa. Musbat son kiriting:")
            return True

        target_id = data["target_id"]
        import payments as pmt
        if step == "admin_balance_add":
            result = pmt.admin_add_balance(target_id, amount, chat_id)
        else:
            result = pmt.admin_remove_balance(target_id, amount, chat_id)

        clear_session(chat_id)
        api.send_message(chat_id, result["message"],
                         reply_markup=kb.admin_menu_keyboard())
        return False

    return False


# ─── ADMIN PREMIUM FLOW ───────────────────────────────────────────────────────

def start_admin_give_premium(chat_id: int, target_id: int,
                              days: Optional[str] = None):
    if days:
        # Direct call with days already known — process immediately
        import payments as pmt
        result = pmt.admin_give_premium(target_id, days, chat_id)
        api.send_message(chat_id, result["message"],
                         reply_markup=kb.admin_menu_keyboard())
        return

    # Ask which plan
    api.send_message(
        chat_id,
        "💎 Foydalanuvchi <code>{}</code> uchun premium rejasini tanlang:".format(
            target_id),
        reply_markup=kb.admin_premium_plans_keyboard(target_id),
    )


def handle_admin_give_premium_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    if sess.get("step") != "admin_give_premium_days":
        return False

    days = text.strip()
    if days not in ("7", "30", "90", "365"):
        api.send_message(chat_id, "❌ 7, 30, 90 yoki 365 kiriting:")
        return True

    target_id = sess["data"]["target_id"]
    import payments as pmt
    result = pmt.admin_give_premium(target_id, days, chat_id)
    clear_session(chat_id)
    api.send_message(chat_id, result["message"],
                     reply_markup=kb.admin_menu_keyboard())
    return False


def admin_remove_premium(chat_id: int, target_id: int):
    """Remove premium from a user immediately."""
    user = db.get_user(target_id)
    if not user:
        api.send_message(chat_id, "❌ Foydalanuvchi topilmadi.",
                         reply_markup=kb.admin_menu_keyboard())
        return
    db.set_premium(target_id, "")
    logger.info("Admin {} removed premium from user {}".format(chat_id, target_id))
    api.send_message(
        chat_id,
        "✅ Foydalanuvchi <code>{}</code> premiumı o'chirildi.".format(target_id),
        reply_markup=kb.admin_menu_keyboard(),
    )


# ─── CHANNELS ─────────────────────────────────────────────────────────────────

def show_channels_admin(chat_id: int):
    channels = db.get_all_channels()
    if not channels:
        api.send_message(
            chat_id,
            "📢 <b>Kanallar</b>\n\nHali kanal qo'shilmagan.",
            reply_markup=kb.inline([
                [("➕ Kanal qo'shish", "admin_add_channel")],
                [("⬅️ Orqaga", "admin:menu")],
            ]),
        )
        return
    api.send_message(
        chat_id,
        "📢 <b>Kanallar ro'yxati</b>\n\nO'chirish uchun bosing:",
        reply_markup=kb.admin_channels_keyboard(channels),
    )


def start_add_channel(chat_id: int):
    set_session(chat_id, step="add_channel_id", data={})
    api.send_message(
        chat_id,
        "📢 <b>Kanal qo'shish</b>\n\n"
        "Kanal ID sini kiriting:\n"
        "Masalan: <code>@kanalUsername</code> yoki <code>-1001234567890</code>",
        reply_markup=kb.reply([["❌ Bekor qilish"]]),
    )


def handle_add_channel_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    step = sess.get("step", "")
    data = sess.get("data", {})

    if step == "add_channel_id":
        channel_id = text.strip()
        data["channel_id"] = channel_id
        set_session(chat_id, step="add_channel_title", data=data)
        api.send_message(chat_id, "Kanal nomini kiriting:")
        return True

    elif step == "add_channel_title":
        data["title"] = text.strip()
        set_session(chat_id, step="add_channel_username", data=data)
        api.send_message(
            chat_id,
            "Kanal @username ni kiriting (yo'q bo'lsa — 'yo'q' yozing):")
        return True

    elif step == "add_channel_username":
        val = text.strip().lower()
        username = "" if val in ("yo'q", "yoq", "no", "-") else text.strip().lstrip("@")
        try:
            db.add_channel(
                telegram_channel_id=data["channel_id"],
                username=username,
                title=data["title"],
                required=1,
            )
            clear_session(chat_id)
            logger.info("Admin {} added channel {}".format(chat_id, data["channel_id"]))
            api.send_message(
                chat_id,
                "✅ Kanal muvaffaqiyatli qo'shildi!\n📢 {}".format(
                    escape(data["title"])),
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as exc:
            logger.error("Failed to add channel: {}".format(exc))
            api.send_message(
                chat_id,
                "❌ Xatolik: {}".format(escape(str(exc))),
                reply_markup=kb.admin_menu_keyboard(),
            )
        return False

    return False


# ─── BROADCAST ────────────────────────────────────────────────────────────────

def start_broadcast(chat_id: int):
    set_session(chat_id, step="broadcast_text", data={})
    api.send_message(
        chat_id,
        "📢 <b>Xabar yuborish</b>\n\n"
        "Barcha foydalanuvchilarga yuboriladigan xabarni kiriting\n"
        "(HTML formatlanish qo'llab-quvvatlanadi):",
        reply_markup=kb.reply([["❌ Bekor qilish"]]),
    )


def handle_broadcast_step(chat_id: int, text: str, msg: dict = None) -> bool:
    sess = get_session(chat_id)
    if sess.get("step") != "broadcast_text":
        return False

    set_session(chat_id, step="broadcast_confirm", data={"text": text})
    preview = text[:500] + ("..." if len(text) > 500 else "")
    api.send_message(
        chat_id,
        "📢 <b>Xabar ko'rinishi:</b>\n\n{}\n\n"
        "Yuborishni tasdiqlaysizmi?".format(preview),
        reply_markup=kb.yes_no_keyboard("broadcast_send", "admin:menu"),
    )
    return True


def execute_broadcast_from_session(admin_id: int, chat_id: int):
    """Execute broadcast using text stored in session."""
    sess = get_session(admin_id)
    text = sess.get("data", {}).get("text", "")
    if not text:
        api.send_message(chat_id, "❌ Broadcast matni topilmadi.",
                         reply_markup=kb.admin_menu_keyboard())
        clear_session(admin_id)
        return
    # Run in background thread to not block the polling loop
    t = threading.Thread(
        target=_run_broadcast,
        args=(admin_id, chat_id, text),
        daemon=True,
    )
    t.start()
    api.send_message(
        chat_id,
        "📢 Broadcast boshlandi. Yakunlanganda xabar olasiz.",
        reply_markup=kb.admin_menu_keyboard(),
    )


def _run_broadcast(admin_id: int, chat_id: int, text: str):
    users = db.get_all_users()
    sent = 0
    failed = 0

    logger.info("Broadcast started by admin {} to {} users".format(
        admin_id, len(users)))

    for user in users:
        try:
            result = api.send_message(user["telegram_id"], text)
            if result:
                sent += 1
            else:
                failed += 1
        except Exception as exc:
            logger.warning("Broadcast failed for user {}: {}".format(
                user["telegram_id"], exc))
            failed += 1
        time.sleep(BROADCAST_DELAY)

    clear_session(admin_id)
    logger.info("Broadcast finished: sent={} failed={}".format(sent, failed))
    api.send_message(
        chat_id,
        "📢 <b>Broadcast yakunlandi</b>\n\n"
        "✅ Yuborildi: <b>{}</b>\n"
        "❌ Yuborilmadi: <b>{}</b>".format(sent, failed),
        reply_markup=kb.admin_menu_keyboard(),
    )


def execute_broadcast(admin_id: int, text: str):
    """Legacy direct broadcast — still functional."""
    users = db.get_all_users()
    sent = 0
    failed = 0

    for user in users:
        try:
            result = api.send_message(user["telegram_id"], text)
            if result:
                sent += 1
            else:
                failed += 1
        except Exception as exc:
            logger.warning("Broadcast failed for {}: {}".format(
                user["telegram_id"], exc))
            failed += 1
        time.sleep(BROADCAST_DELAY)

    clear_session(admin_id)
    api.send_message(
        admin_id,
        "📢 <b>Broadcast yakunlandi</b>\n\n"
        "✅ Yuborildi: <b>{}</b>\n"
        "❌ Yuborilmadi: <b>{}</b>".format(sent, failed),
        reply_markup=kb.admin_menu_keyboard(),
    )


# ─── SETTINGS ─────────────────────────────────────────────────────────────────

def show_settings(chat_id: int):
    from config import PREMIUM_PRICES
    prices_text = "\n".join(
        "  💎 {} kun: <b>{} UZS</b>".format(
            days, db.get_setting("premium_price_{}".format(days)) or price)
        for days, price in PREMIUM_PRICES.items()
    )
    text = (
        "⚙️ <b>Sozlamalar</b>\n\n"
        "💎 Premium narxlari:\n{}\n\n"
        "Narxni o'zgartirish uchun kiriting:\n"
        "<code>price:7:5000</code>\n"
        "(format: price:kun:narx)"
    ).format(prices_text)
    set_session(chat_id, step="settings_input", data={})
    api.send_message(chat_id, text, reply_markup=kb.back_to_admin())


def handle_settings_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    if sess.get("step") != "settings_input":
        return False

    if text.startswith("price:"):
        parts = text.split(":")
        if len(parts) == 3:
            _, days, price_str = parts
            days = days.strip()
            price_val = safe_int(price_str.strip())
            if days in ("7", "30", "90", "365") and price_val > 0:
                db.set_setting("premium_price_{}".format(days), str(price_val))
                clear_session(chat_id)
                api.send_message(
                    chat_id,
                    "✅ Premium narxi yangilandi!\n💎 {} kun: <b>{:,} UZS</b>".format(
                        days, price_val).replace(",", " "),
                    reply_markup=kb.admin_menu_keyboard(),
                )
                return False

    api.send_message(
        chat_id,
        "❌ Noto'g'ri format. Masalan: <code>price:30:15000</code>")
    return True
