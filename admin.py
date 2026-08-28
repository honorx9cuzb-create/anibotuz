"""
admin.py — Admin panel logic for Ani Telegram Bot.
All admin state is stored in a simple in-memory dict per admin user.
"""

import logging
import time
from config import ADMIN_IDS, BROADCAST_DELAY, PAGINATION_SIZE
import database as db
import api
import keyboards as kb
from utils import escape, format_currency, format_premium_until, is_premium_active, safe_int

logger = logging.getLogger(__name__)

# In-memory admin session state: {telegram_id: {step, data, ...}}
admin_sessions: dict = {}


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


def get_session(telegram_id: int) -> dict:
    if telegram_id not in admin_sessions:
        admin_sessions[telegram_id] = {}
    return admin_sessions[telegram_id]


def clear_session(telegram_id: int):
    admin_sessions[telegram_id] = {}


def set_session(telegram_id: int, **kwargs):
    sess = get_session(telegram_id)
    sess.update(kwargs)


# ─── ADMIN MENU ───────────────────────────────────────────────────────────────

def show_admin_menu(chat_id: int):
    api.send_message(chat_id,
                     "👑 <b>ADMIN PANEL</b>\n\nQuyidagi bo'limlardan birini tanlang:",
                     reply_markup=kb.admin_menu_keyboard())


# ─── STATISTICS ───────────────────────────────────────────────────────────────

def show_stats(chat_id: int):
    users = db.get_users_count()
    anime_count = db.get_anime_count()
    episodes = db.get_episodes_count()
    premium = db.get_premium_users_count()
    total_bal = db.get_total_balance()

    text = (
        "📊 <b>STATISTIKA</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users:,}</b>\n"
        f"🎬 Anime: <b>{anime_count:,}</b>\n"
        f"📺 Qismlar: <b>{episodes:,}</b>\n"
        f"💎 Premium foydalanuvchilar: <b>{premium:,}</b>\n"
        f"💰 Jami balans: <b>{format_currency(total_bal)}</b>"
    )
    api.send_message(chat_id, text, reply_markup=kb.back_to_admin())


# ─── ADD ANIME FLOW ───────────────────────────────────────────────────────────

ADD_ANIME_STEPS = [
    ("title",       "Anime nomini kiriting:"),
    ("description", "Anime tavsifini kiriting:"),
    ("genre",       "Janrini kiriting (masalan: Action, Romance):"),
    ("year",        "Yilini kiriting (masalan: 2002):"),
    ("country",     "Mamlakatini kiriting (masalan: Japan):"),
    ("language",    "Tilini kiriting (masalan: O'zbek):"),
    ("poster",      "Poster URL yoki file_id kiriting (yo'q bo'lsa — kiritmang):"),
    ("premium",     "Premium animemi? (ha / yo'q):"),
    ("status",      "Status: ongoing yoki completed?"),
]


def start_add_anime(chat_id: int):
    set_session(chat_id, step="add_anime_0", data={})
    api.send_message(chat_id,
                     f"➕ <b>Anime qo'shish</b>\n\n{ADD_ANIME_STEPS[0][1]}",
                     reply_markup=kb.back_to_admin())


def handle_add_anime_step(chat_id: int, text: str) -> bool:
    """Process one step of add_anime flow. Returns True while still in flow."""
    sess = get_session(chat_id)
    step_key = sess.get("step", "")
    if not step_key.startswith("add_anime_"):
        return False

    step_index = safe_int(step_key.split("_")[-1])
    field_name, _ = ADD_ANIME_STEPS[step_index]
    data = sess.get("data", {})

    # Validate/transform specific fields
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
    elif field_name == "poster":
        data[field_name] = text.strip() if text.strip().lower() != "yo'q" else ""
    else:
        data[field_name] = text.strip()

    sess["data"] = data
    next_step = step_index + 1

    if next_step < len(ADD_ANIME_STEPS):
        set_session(chat_id, step=f"add_anime_{next_step}", data=data)
        api.send_message(chat_id, ADD_ANIME_STEPS[next_step][1],
                         reply_markup=kb.back_to_admin())
        return True
    else:
        # Save to DB
        try:
            anime_id = db.create_anime(
                title=data.get("title", ""),
                description=data.get("description", ""),
                genre=data.get("genre", ""),
                year=safe_int(data.get("year", 0)),
                country=data.get("country", ""),
                language=data.get("language", ""),
                poster=data.get("poster", ""),
                premium=data.get("premium", 0),
                status=data.get("status", "ongoing"),
            )
            clear_session(chat_id)
            logger.info(f"Admin {chat_id} created anime id={anime_id} title={data.get('title')}")
            api.send_message(
                chat_id,
                f"✅ <b>Anime muvaffaqiyatli qo'shildi!</b>\n\n"
                f"🎬 Nomi: <b>{escape(data.get('title',''))}</b>\n"
                f"🆔 ID: <code>{anime_id}</code>",
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as e:
            logger.error(f"Failed to create anime: {e}")
            api.send_message(chat_id, f"❌ Xatolik yuz berdi: {escape(str(e))}",
                             reply_markup=kb.admin_menu_keyboard())
        return False


# ─── ADD EPISODE FLOW ─────────────────────────────────────────────────────────

def start_add_episode(chat_id: int):
    set_session(chat_id, step="add_episode_anime_id", data={})
    api.send_message(chat_id,
                     "➕ <b>Qism qo'shish</b>\n\nAnime ID sini kiriting:",
                     reply_markup=kb.back_to_admin())


def handle_add_episode_step(chat_id: int, text: str, video_file_id: str = None) -> bool:
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
        api.send_message(chat_id,
                         f"🎬 Anime: <b>{escape(anime['title'])}</b>\n\nQism raqamini kiriting:")
        return True

    elif step == "add_episode_number":
        ep_num = safe_int(text.strip())
        if ep_num <= 0:
            api.send_message(chat_id, "❌ Noto'g'ri qism raqami. Qaytadan kiriting:")
            return True
        data["episode_number"] = ep_num
        set_session(chat_id, step="add_episode_title", data=data)
        api.send_message(chat_id, "Qism sarlavhasini kiriting (yo'q bo'lsa — kiritmang):")
        return True

    elif step == "add_episode_title":
        data["title"] = text.strip()
        set_session(chat_id, step="add_episode_video", data=data)
        api.send_message(chat_id,
                         "📹 Endi videoni yuboring (Telegram video xabari sifatida):")
        return True

    elif step == "add_episode_video":
        if not video_file_id:
            api.send_message(chat_id, "❌ Iltimos, video faylni yuboring (document emas, video):")
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
                f"Admin {chat_id} added episode {data['episode_number']} "
                f"to anime {data['anime_id']}, ep_id={ep_id}"
            )
            api.send_message(
                chat_id,
                f"✅ <b>Qism muvaffaqiyatli qo'shildi!</b>\n\n"
                f"📺 Qism: <b>{data['episode_number']}-qism</b>\n"
                f"🎬 Anime ID: <code>{data['anime_id']}</code>",
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as e:
            logger.error(f"Failed to create episode: {e}")
            api.send_message(chat_id, f"❌ Xatolik yuz berdi: {escape(str(e))}",
                             reply_markup=kb.admin_menu_keyboard())
        return False

    return False


# ─── EDIT ANIME FLOW ──────────────────────────────────────────────────────────

def start_edit_anime(chat_id: int):
    set_session(chat_id, step="edit_anime_id", data={})
    api.send_message(chat_id, "✏️ <b>Anime tahrirlash</b>\n\nAnime ID sini kiriting:",
                     reply_markup=kb.back_to_admin())


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
        api.send_message(
            chat_id,
            f"🎬 <b>{escape(anime['title'])}</b>\n\n"
            "Qaysi maydonni tahrirlashni xohlaysiz?\n"
            "Kiriting: title / description / genre / year / country / language / premium / status",
        )
        return True

    elif step == "edit_anime_field":
        valid = {"title", "description", "genre", "year", "country", "language", "premium", "status"}
        field = text.strip().lower()
        if field not in valid:
            api.send_message(chat_id, f"❌ Noto'g'ri maydon. Quyidagilardan birini kiriting:\n{', '.join(valid)}")
            return True
        data["field"] = field
        set_session(chat_id, step="edit_anime_value", data=data)
        api.send_message(chat_id, f"✏️ Yangi qiymatni kiriting (<b>{field}</b>):")
        return True

    elif step == "edit_anime_value":
        field = data.get("field")
        value = text.strip()
        update = {}
        if field == "year":
            update[field] = safe_int(value, 0)
        elif field == "premium":
            update[field] = 1 if value.lower() in ("ha", "yes", "1", "true") else 0
        else:
            update[field] = value

        try:
            db.update_anime(data["anime_id"], **update)
            clear_session(chat_id)
            logger.info(f"Admin {chat_id} edited anime {data['anime_id']} field={field}")
            api.send_message(
                chat_id,
                f"✅ Anime muvaffaqiyatli yangilandi!\n🆔 ID: <code>{data['anime_id']}</code>",
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as e:
            logger.error(f"Failed to edit anime: {e}")
            api.send_message(chat_id, f"❌ Xatolik: {escape(str(e))}")
        return False

    return False


# ─── DELETE ANIME ─────────────────────────────────────────────────────────────

def start_delete_anime(chat_id: int):
    set_session(chat_id, step="delete_anime_id", data={})
    api.send_message(chat_id, "🗑 <b>Anime o'chirish</b>\n\nAnime ID sini kiriting:",
                     reply_markup=kb.back_to_admin())


def handle_delete_anime_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    step = sess.get("step", "")

    if step == "delete_anime_id":
        anime_id = safe_int(text.strip())
        anime = db.get_anime(anime_id)
        if not anime:
            api.send_message(chat_id, "❌ Anime topilmadi. Qayta kiriting:")
            return True
        set_session(chat_id, step="delete_anime_confirm", data={"anime_id": anime_id})
        api.send_message(
            chat_id,
            f"⚠️ <b>Rostdan ham o'chirmoqchimisiz?</b>\n\n"
            f"🎬 <b>{escape(anime['title'])}</b>\n"
            f"🆔 ID: <code>{anime_id}</code>\n\n"
            "Bu amal barcha qismlar va sevimlilarni ham o'chiradi!",
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
    logger.info(f"Admin {chat_id} deleted anime id={anime_id} title={title}")
    api.send_message(
        chat_id,
        f"✅ <b>{escape(title)}</b> muvaffaqiyatli o'chirildi.",
        reply_markup=kb.admin_menu_keyboard(),
    )


# ─── USER MANAGEMENT ──────────────────────────────────────────────────────────

def start_user_search(chat_id: int):
    set_session(chat_id, step="search_user_id", data={})
    api.send_message(chat_id,
                     "👥 <b>Foydalanuvchi qidirish</b>\n\nTelegram ID sini kiriting:",
                     reply_markup=kb.back_to_admin())


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
    uname_display = ('@' + escape(user['username'])) if user['username'] else "Yo'q"
    fname_display = escape(user['first_name'] or "Noma'lum")
    text_msg = (
        f"👤 <b>Foydalanuvchi ma'lumotlari</b>\n\n"
        f"🆔 ID: <code>{user['telegram_id']}</code>\n"
        f"👤 Username: {uname_display}\n"
        f"📛 Ism: {fname_display}\n"
        f"💰 Balans: <b>{format_currency(user['balance'])}</b>\n"
        f"💎 Premium: {premium_status}\n"
        f"📅 Premium tugash: {format_premium_until(user['premium_until'])}\n"
        f"👥 Referallar: <b>{user['referrals']}</b>\n"
        f"📆 Ro'yxatdan o'tgan: {user['created_at'][:10]}"
    )
    clear_session(chat_id)
    api.send_message(chat_id, text_msg, reply_markup=kb.admin_user_keyboard(target_id))
    return False


# ─── ADMIN BALANCE FLOW ───────────────────────────────────────────────────────

def start_admin_balance(chat_id: int, action: str, target_id: int):
    """action: 'add' or 'remove'"""
    set_session(chat_id, step=f"admin_balance_{action}", data={"target_id": target_id})
    verb = "qo'shish" if action == "add" else "ayirish"
    api.send_message(chat_id,
                     f"💰 Foydalanuvchi {target_id} uchun balansi {verb}.\n\n"
                     "Summani kiriting (UZS):")


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
        api.send_message(chat_id, result["message"], reply_markup=kb.admin_menu_keyboard())
        return False

    return False


# ─── ADMIN PREMIUM FLOW ───────────────────────────────────────────────────────

def start_admin_give_premium(chat_id: int, target_id: int):
    set_session(chat_id, step="admin_give_premium_days", data={"target_id": target_id})
    api.send_message(
        chat_id,
        f"💎 Foydalanuvchi {target_id} uchun premium berish.\n\nKunlar sonini kiriting (7, 30, 365):",
    )


def handle_admin_give_premium_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    if sess.get("step") != "admin_give_premium_days":
        return False

    days = text.strip()
    if days not in ("7", "30", "365"):
        api.send_message(chat_id, "❌ 7, 30 yoki 365 kiriting:")
        return True

    target_id = sess["data"]["target_id"]
    import payments as pmt
    result = pmt.admin_give_premium(target_id, days, chat_id)
    clear_session(chat_id)
    api.send_message(chat_id, result["message"], reply_markup=kb.admin_menu_keyboard())
    return False


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
    api.send_message(chat_id, "📢 <b>Kanallar ro'yxati</b>\n\nO'chirish uchun bosing:",
                     reply_markup=kb.admin_channels_keyboard(channels))


def start_add_channel(chat_id: int):
    set_session(chat_id, step="add_channel_id", data={})
    api.send_message(
        chat_id,
        "📢 <b>Kanal qo'shish</b>\n\n"
        "Kanal ID sini kiriting (masalan: @kanalUsername yoki -1001234567890):",
        reply_markup=kb.back_to_admin(),
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
        api.send_message(chat_id, "Kanal @username ni kiriting (yo'q bo'lsa — kiritmang):")
        return True

    elif step == "add_channel_username":
        username = text.strip().lstrip("@") if text.strip().lower() != "yo'q" else ""
        try:
            db.add_channel(
                telegram_channel_id=data["channel_id"],
                username=username,
                title=data["title"],
                required=1,
            )
            clear_session(chat_id)
            logger.info(f"Admin {chat_id} added channel {data['channel_id']}")
            api.send_message(
                chat_id,
                f"✅ Kanal muvaffaqiyatli qo'shildi!\n📢 {escape(data['title'])}",
                reply_markup=kb.admin_menu_keyboard(),
            )
        except Exception as e:
            logger.error(f"Failed to add channel: {e}")
            api.send_message(chat_id, f"❌ Xatolik: {escape(str(e))}",
                             reply_markup=kb.admin_menu_keyboard())
        return False

    return False


# ─── BROADCAST ────────────────────────────────────────────────────────────────

def start_broadcast(chat_id: int):
    set_session(chat_id, step="broadcast_text", data={})
    api.send_message(
        chat_id,
        "📢 <b>Xabar yuborish</b>\n\nBarcha foydalanuvchilarga yuboriladigan xabarni kiriting:",
        reply_markup=kb.back_to_admin(),
    )


def handle_broadcast_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    if sess.get("step") != "broadcast_text":
        return False

    set_session(chat_id, step="broadcast_confirm", data={"text": text})
    api.send_message(
        chat_id,
        f"📢 <b>Xabar ko'rinishi:</b>\n\n{text}\n\n"
        "Yuborishni tasdiqlaysizmi?",
        reply_markup=kb.yes_no_keyboard("broadcast_send", "admin:menu"),
    )
    return True


def execute_broadcast(admin_id: int, text: str):
    """Send broadcast to all users with rate limiting."""
    users = db.get_all_users()
    sent = 0
    failed = 0

    logger.info(f"Broadcast started by admin {admin_id} to {len(users)} users")

    for user in users:
        try:
            result = api.send_message(user["telegram_id"], text)
            if result:
                sent += 1
            else:
                failed += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for user {user['telegram_id']}: {e}")
            failed += 1
        time.sleep(BROADCAST_DELAY)

    clear_session(admin_id)
    logger.info(f"Broadcast finished: sent={sent} failed={failed}")
    api.send_message(
        admin_id,
        f"📢 <b>Broadcast yakunlandi</b>\n\n"
        f"✅ Yuborildi: <b>{sent}</b>\n"
        f"❌ Yuborilmadi: <b>{failed}</b>",
        reply_markup=kb.admin_menu_keyboard(),
    )


# ─── SETTINGS ─────────────────────────────────────────────────────────────────

def show_settings(chat_id: int):
    from config import PREMIUM_PRICES
    prices_text = "\n".join(
        f"  💎 {days} kun: <b>{db.get_setting(f'premium_price_{days}') or price} UZS</b>"
        for days, price in PREMIUM_PRICES.items()
    )
    text = (
        "⚙️ <b>Sozlamalar</b>\n\n"
        "💎 Premium narxlari:\n" + prices_text + "\n\n"
        "Narxni o'zgartirish uchun kiriting:\n"
        "<code>price:7:5000</code> (format: price:kun:narx)"
    )
    set_session(chat_id, step="settings_input", data={})
    api.send_message(chat_id, text, reply_markup=kb.back_to_admin())


def handle_settings_step(chat_id: int, text: str) -> bool:
    sess = get_session(chat_id)
    if sess.get("step") != "settings_input":
        return False

    if text.startswith("price:"):
        parts = text.split(":")
        if len(parts) == 3:
            _, days, price = parts
            days = days.strip()
            price_val = safe_int(price.strip())
            if days in ("7", "30", "365") and price_val > 0:
                db.set_setting(f"premium_price_{days}", str(price_val))
                clear_session(chat_id)
                api.send_message(
                    chat_id,
                    f"✅ Premium narxi yangilandi!\n💎 {days} kun: <b>{price_val:,} UZS</b>",
                    reply_markup=kb.admin_menu_keyboard(),
                )
                return False

    api.send_message(chat_id, "❌ Noto'g'ri format. Masalan: <code>price:30:15000</code>")
    return True
