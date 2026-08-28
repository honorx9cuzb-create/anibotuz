"""
handlers.py — Main update dispatcher for Ani Telegram Bot.
Routes all messages and callback queries to the correct handler.
"""

import logging
from config import (ADMIN_IDS, REFERRAL_BONUS, WELCOME_BONUS,
                    BOT_USERNAME, PAGINATION_SIZE)
import database as db
import api
import keyboards as kb
import admin as adm
import payments as pmt
from utils import (escape, format_currency, format_premium_until,
                   is_premium_active, safe_int, validate_referral_code,
                   truncate)

logger = logging.getLogger(__name__)

# In-memory user session state: {telegram_id: {step, data}}
user_sessions: dict = {}


def get_user_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {}
    return user_sessions[uid]


def set_user_session(uid: int, **kwargs):
    sess = get_user_session(uid)
    sess.update(kwargs)


def clear_user_session(uid: int):
    user_sessions[uid] = {}


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

def handle_update(update: dict):
    """Main dispatcher for all Telegram updates."""
    try:
        if "message" in update:
            handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback(update["callback_query"])
    except Exception as e:
        logger.error(f"Unhandled error in handle_update: {e}", exc_info=True)


# ─── MESSAGE HANDLER ─────────────────────────────────────────────────────────

def handle_message(msg: dict):
    chat_id = msg["chat"]["id"]
    user_tg = msg.get("from", {})
    telegram_id = user_tg.get("id")
    text = msg.get("text", "").strip()
    video = msg.get("video")
    document = msg.get("document")

    if not telegram_id:
        return

    # ── Register / get user ──────────────────────────────────────────────────
    user = db.get_user(telegram_id)
    is_new = user is None

    if is_new:
        user = _register_user(msg, telegram_id, user_tg)
        if not user:
            return

    # ── Admin flows ──────────────────────────────────────────────────────────
    if adm.is_admin(telegram_id):
        sess = adm.get_session(telegram_id)
        step = sess.get("step", "")

        # Video upload for episode
        if step == "add_episode_video":
            file_id = None
            if video:
                file_id = video.get("file_id")
            elif document:
                file_id = document.get("file_id")
            adm.handle_add_episode_step(chat_id, text or "", video_file_id=file_id)
            return

        if step.startswith("add_anime_"):
            if text:
                adm.handle_add_anime_step(chat_id, text)
            return

        if step.startswith("add_episode_"):
            if text:
                adm.handle_add_episode_step(chat_id, text)
            return

        if step.startswith("edit_anime_"):
            if text:
                adm.handle_edit_anime_step(chat_id, text)
            return

        if step.startswith("delete_anime_"):
            if text:
                adm.handle_delete_anime_step(chat_id, text)
            return

        if step == "search_user_id":
            if text:
                adm.handle_user_search_step(chat_id, text)
            return

        if step in ("admin_balance_add", "admin_balance_remove"):
            if text:
                adm.handle_admin_balance_step(chat_id, text)
            return

        if step == "admin_give_premium_days":
            if text:
                adm.handle_admin_give_premium_step(chat_id, text)
            return

        if step == "broadcast_text":
            if text:
                if adm.handle_broadcast_step(chat_id, text):
                    return

        if step == "add_channel_id" or step == "add_channel_title" or step == "add_channel_username":
            if text:
                adm.handle_add_channel_step(chat_id, text)
            return

        if step == "settings_input":
            if text:
                adm.handle_settings_step(chat_id, text)
            return

    # ── User flows ────────────────────────────────────────────────────────────
    sess = get_user_session(telegram_id)
    step = sess.get("step", "")

    # ── Commands ──────────────────────────────────────────────────────────────
    if text.startswith("/start"):
        _handle_start(chat_id, telegram_id, text, is_new, user)
        return

    if text == "/admin" and adm.is_admin(telegram_id):
        adm.show_admin_menu(chat_id)
        return

    if text == "/stats" and adm.is_admin(telegram_id):
        adm.show_stats(chat_id)
        return

    if text == "/users" and adm.is_admin(telegram_id):
        adm.start_user_search(chat_id)
        return

    if text == "/anime" and adm.is_admin(telegram_id):
        _show_catalog(chat_id, 0)
        return

    if text == "/broadcast" and adm.is_admin(telegram_id):
        adm.start_broadcast(chat_id)
        return

    # ── Channel check for all non-command messages ────────────────────────────
    if not _check_subscriptions(chat_id, telegram_id):
        return

    # ── User session steps ────────────────────────────────────────────────────
    if step == "searching":
        if text:
            _handle_search_query(chat_id, telegram_id, text)
            return

    if step == "search_by_id":
        if text:
            _handle_search_by_id(chat_id, telegram_id, text)
            return

    # ── Menu buttons ──────────────────────────────────────────────────────────
    if text == "🔎 Anime qidirish":
        set_user_session(telegram_id, step="searching")
        api.send_message(chat_id,
                         "🔎 <b>Anime qidirish</b>\n\nAnime nomini kiriting:",
                         reply_markup=kb.reply([["❌ Bekor qilish"]]))
        return

    if text == "🔢 ID orqali qidirish":
        set_user_session(telegram_id, step="search_by_id")
        api.send_message(chat_id,
                         "🔢 <b>ID orqali qidirish</b>\n\nAnime ID sini kiriting:",
                         reply_markup=kb.reply([["❌ Bekor qilish"]]))
        return

    if text == "📚 Katalog":
        clear_user_session(telegram_id)
        _show_catalog(chat_id, 0)
        return

    if text == "⭐ Sevimlilar":
        clear_user_session(telegram_id)
        _show_favorites(chat_id, telegram_id)
        return

    if text == "👤 Profil":
        clear_user_session(telegram_id)
        _show_profile(chat_id, telegram_id)
        return

    if text == "💰 Balans":
        clear_user_session(telegram_id)
        _show_balance(chat_id, telegram_id)
        return

    if text == "💎 Premium":
        clear_user_session(telegram_id)
        _show_premium_menu(chat_id, telegram_id)
        return

    if text == "🎁 Referal":
        clear_user_session(telegram_id)
        _show_referral(chat_id, telegram_id)
        return

    if text == "❌ Bekor qilish":
        clear_user_session(telegram_id)
        api.send_message(chat_id, "✅ Bekor qilindi.", reply_markup=kb.main_menu())
        return

    # Unknown message — show main menu
    api.send_message(chat_id, "Quyidagi menyudan tanlang:", reply_markup=kb.main_menu())


# ─── CALLBACK HANDLER ────────────────────────────────────────────────────────

def handle_callback(cb: dict):
    query_id = cb["id"]
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    telegram_id = cb["from"]["id"]
    data = cb.get("data", "")

    user = db.get_user(telegram_id)
    if not user:
        api.answer_callback_query(query_id, "❌ Avval /start bosing.", show_alert=True)
        return

    try:
        _dispatch_callback(query_id, chat_id, message_id, telegram_id, user, data)
    except Exception as e:
        logger.error(f"Callback error data={data}: {e}", exc_info=True)
        api.answer_callback_query(query_id, "❌ Xatolik yuz berdi.", show_alert=True)


def _dispatch_callback(query_id, chat_id, message_id, telegram_id, user, data):
    parts = data.split(":")
    action = parts[0]
    args = parts[1:]

    # ── Noop ─────────────────────────────────────────────────────────────────
    if action == "noop":
        api.answer_callback_query(query_id)
        return

    # ── Main menu ─────────────────────────────────────────────────────────────
    if action == "main_menu":
        api.answer_callback_query(query_id)
        api.send_message(chat_id, "🏠 Asosiy menyu", reply_markup=kb.main_menu())
        return

    # ── Channel check ─────────────────────────────────────────────────────────
    if action == "check_subscription":
        api.answer_callback_query(query_id)
        if _check_subscriptions(chat_id, telegram_id):
            api.send_message(chat_id,
                             "✅ Barcha kanallarga obuna bo'ldingiz!\nBotdan foydalanishingiz mumkin.",
                             reply_markup=kb.main_menu())
        return

    # ── Subscription gate for user actions ────────────────────────────────────
    if not _check_subscriptions(chat_id, telegram_id):
        api.answer_callback_query(query_id)
        return

    # ── Anime page ────────────────────────────────────────────────────────────
    if action == "anime" and args:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        _show_anime_page(chat_id, message_id, telegram_id, user, anime_id)
        return

    # ── Catalog page ─────────────────────────────────────────────────────────
    if action == "catalog" and args:
        api.answer_callback_query(query_id)
        page = safe_int(args[0])
        _show_catalog_inline(chat_id, message_id, page)
        return

    # ── Watch (episodes) ─────────────────────────────────────────────────────
    if action == "watch" and args:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        _show_episodes(chat_id, message_id, telegram_id, user, anime_id)
        return

    # ── Episode play ─────────────────────────────────────────────────────────
    if action == "episode" and len(args) >= 2:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        ep_num = safe_int(args[1])
        _play_episode(chat_id, telegram_id, user, anime_id, ep_num)
        return

    # ── Favorite toggle ──────────────────────────────────────────────────────
    if action == "favorite" and args:
        anime_id = safe_int(args[0])
        _toggle_favorite(query_id, chat_id, message_id, telegram_id, user, anime_id)
        return

    # ── Premium menu ─────────────────────────────────────────────────────────
    if action == "premium_menu":
        api.answer_callback_query(query_id)
        _show_premium_inline(chat_id, message_id, telegram_id)
        return

    # ── Premium plan select ───────────────────────────────────────────────────
    if action == "premium" and args:
        api.answer_callback_query(query_id)
        days = args[0]
        _show_premium_confirm(chat_id, message_id, telegram_id, user, days)
        return

    # ── Premium buy ──────────────────────────────────────────────────────────
    if action == "premium_buy" and args:
        api.answer_callback_query(query_id)
        days = args[0]
        _buy_premium(chat_id, message_id, telegram_id, days)
        return

    # ── Admin callbacks ───────────────────────────────────────────────────────
    if action == "admin" and adm.is_admin(telegram_id):
        api.answer_callback_query(query_id)
        _handle_admin_callback(chat_id, message_id, telegram_id, args)
        return

    if action == "admin_delete_confirm" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        adm.confirm_delete_anime(chat_id, safe_int(args[0]))
        return

    if action == "admin_del_channel" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        db.delete_channel(safe_int(args[0]))
        logger.info(f"Admin {telegram_id} deleted channel {args[0]}")
        api.send_message(chat_id, "✅ Kanal o'chirildi.", reply_markup=kb.admin_menu_keyboard())
        return

    if action == "admin_add_channel" and adm.is_admin(telegram_id):
        api.answer_callback_query(query_id)
        adm.start_add_channel(chat_id)
        return

    if action == "admin_balance" and adm.is_admin(telegram_id) and len(args) >= 2:
        api.answer_callback_query(query_id)
        balance_action, target_id = args[0], safe_int(args[1])
        adm.start_admin_balance(chat_id, balance_action, target_id)
        return

    if action == "admin_premium_give" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        adm.start_admin_give_premium(chat_id, safe_int(args[0]))
        return

    if action == "admin_block" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id, "🚫 Block funksiyasi keyingi versiyada.", show_alert=True)
        return

    if action == "admin_premium_plan" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        adm.start_admin_give_premium(chat_id, safe_int(args[0]))
        return

    if action == "broadcast_send" and adm.is_admin(telegram_id):
        api.answer_callback_query(query_id)
        sess = adm.get_session(telegram_id)
        text = sess.get("data", {}).get("text", "")
        if text:
            api.send_message(chat_id, "📢 Broadcast boshlandi...")
            adm.execute_broadcast(telegram_id, text)
        return

    # Unknown callback
    api.answer_callback_query(query_id, "❓ Noma'lum buyruq.", show_alert=False)


# ─── USER REGISTRATION ────────────────────────────────────────────────────────

def _register_user(msg: dict, telegram_id: int, user_tg: dict):
    username = user_tg.get("username", "")
    first_name = user_tg.get("first_name", "")
    text = msg.get("text", "")
    referred_by = None

    # Parse referral from /start
    if text.startswith("/start "):
        ref_code = text[7:].strip()
        ref_id = validate_referral_code(ref_code)
        if ref_id and ref_id != telegram_id:
            referrer = db.get_user(ref_id)
            if referrer:
                referred_by = ref_id

    user = db.create_user(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        referred_by=referred_by,
        welcome_bonus=WELCOME_BONUS,
    )

    logger.info(f"New user registered: {telegram_id} (@{username}) referred_by={referred_by}")

    # Reward referrer
    if referred_by:
        # Check not already rewarded by checking referrals count vs actual
        db.add_referral(referred_by, REFERRAL_BONUS)
        logger.info(f"Referral bonus {REFERRAL_BONUS} added to user {referred_by}")

    return user


# ─── START HANDLER ────────────────────────────────────────────────────────────

def _handle_start(chat_id: int, telegram_id: int, text: str, is_new: bool, user):
    clear_user_session(telegram_id)

    fname = escape(user['first_name'] or "Do'st")
    if is_new:
        welcome_text = (
            f"👋 Xush kelibsiz, <b>{fname}</b>!\n\n"
            f"🎌 <b>Ani Bot</b> — sizning anime do'stingiz!\n\n"
            f"🎁 Ro'yxatdan o'tganingiz uchun: <b>{format_currency(WELCOME_BONUS)}</b> bonus!\n\n"
            "📚 Minglab anime va qismlar sizni kutmoqda."
        )
        api.send_message(chat_id, welcome_text, reply_markup=kb.main_menu())
    else:
        api.send_message(
            chat_id,
            f"👋 Salom, <b>{fname}</b>!\n\nQuyidagi menyudan tanlang:",
            reply_markup=kb.main_menu(),
        )


# ─── SUBSCRIPTION CHECK ───────────────────────────────────────────────────────

def _check_subscriptions(chat_id: int, telegram_id: int) -> bool:
    """Returns True if user passes all channel subscription checks."""
    channels = db.get_required_channels()
    if not channels:
        return True

    not_subscribed = []
    for ch in channels:
        channel_id = ch["telegram_channel_id"]
        if not api.is_subscribed(channel_id, telegram_id):
            not_subscribed.append(ch)

    if not not_subscribed:
        return True

    channel_list = "\n".join(
        f"• {escape(ch['title'] or ch['username'] or ch['telegram_channel_id'])}"
        for ch in not_subscribed
    )
    text = (
        "📢 <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>\n\n"
        f"{channel_list}"
    )
    api.send_message(chat_id, text, reply_markup=kb.channels_keyboard(channels))
    return False


# ─── ANIME SEARCH ─────────────────────────────────────────────────────────────

def _handle_search_query(chat_id: int, telegram_id: int, query: str):
    clear_user_session(telegram_id)
    results = db.search_anime(query)
    if not results:
        api.send_message(
            chat_id,
            f"🔍 <b>Qidiruv natijalari:</b> <i>{escape(query)}</i>\n\n"
            "❌ Hech narsa topilmadi.",
            reply_markup=kb.main_menu(),
        )
        return

    api.send_message(
        chat_id,
        f"🔎 <b>Qidiruv natijalari:</b> <i>{escape(query)}</i>\n\n"
        f"📋 Topildi: <b>{len(results)}</b> ta",
        reply_markup=kb.anime_list_keyboard(results, back_callback="main_menu"),
    )


def _handle_search_by_id(chat_id: int, telegram_id: int, text: str):
    clear_user_session(telegram_id)
    anime_id = safe_int(text.strip())
    if anime_id <= 0:
        api.send_message(chat_id, "❌ Noto'g'ri ID. Raqam kiriting:", reply_markup=kb.main_menu())
        return
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, f"❌ ID <code>{anime_id}</code> topilmadi.",
                         reply_markup=kb.main_menu())
        return

    user = db.get_user(telegram_id)
    _show_anime_page_text(chat_id, None, telegram_id, user, anime)


# ─── ANIME PAGE ───────────────────────────────────────────────────────────────

def _show_anime_page(chat_id: int, message_id: int, telegram_id: int, user, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, "❌ Anime topilmadi.", reply_markup=kb.main_menu())
        return
    _show_anime_page_text(chat_id, message_id, telegram_id, user, anime)


def _show_anime_page_text(chat_id, message_id, telegram_id, user, anime):
    anime_id = anime["id"]
    is_fav = db.is_favorite(user["id"], anime_id)

    unknown = "Noma'lum"
    premium_badge = "💎 <b>PREMIUM</b>\n" if anime["premium"] else ""
    text = (
        f"{premium_badge}"
        f"🎬 <b>{escape(anime['title'])}</b>\n"
        f"🆔 ID: <code>{anime_id}</code>\n"
        f"🎭 Janr: {escape(anime['genre'] or unknown)}\n"
        f"📅 Yil: {anime['year'] or unknown}\n"
        f"🌍 Mamlakat: {escape(anime['country'] or unknown)}\n"
        f"🌐 Til: {escape(anime['language'] or unknown)}\n"
        f"📌 Status: {escape(anime['status'] or 'ongoing')}\n\n"
        f"<b>Tavsif:</b>\n{escape(truncate(anime['description'] or '', 500))}"
    )
    markup = kb.anime_page_keyboard(anime_id, is_fav=is_fav, back_callback="catalog:0")

    if anime.get("poster"):
        api.send_photo(chat_id, anime["poster"], caption=text, reply_markup=markup)
    else:
        if message_id:
            api.edit_message_text(chat_id, message_id, text, reply_markup=markup)
        else:
            api.send_message(chat_id, text, reply_markup=markup)


# ─── CATALOG ─────────────────────────────────────────────────────────────────

def _show_catalog(chat_id: int, page: int):
    total = db.get_anime_count()
    total_pages = max(1, (total + PAGINATION_SIZE - 1) // PAGINATION_SIZE)
    page = max(0, min(page, total_pages - 1))
    anime_list = db.get_anime_catalog(offset=page * PAGINATION_SIZE, limit=PAGINATION_SIZE)

    if not anime_list:
        api.send_message(chat_id, "📚 Hali anime qo'shilmagan.", reply_markup=kb.main_menu())
        return

    text = f"📚 <b>Anime Katalogi</b>\n\n📋 Jami: <b>{total}</b> ta anime"
    api.send_message(chat_id, text,
                     reply_markup=kb.catalog_keyboard(anime_list, page, total_pages))


def _show_catalog_inline(chat_id: int, message_id: int, page: int):
    total = db.get_anime_count()
    total_pages = max(1, (total + PAGINATION_SIZE - 1) // PAGINATION_SIZE)
    page = max(0, min(page, total_pages - 1))
    anime_list = db.get_anime_catalog(offset=page * PAGINATION_SIZE, limit=PAGINATION_SIZE)

    if not anime_list:
        api.edit_message_text(chat_id, message_id, "📚 Hali anime qo'shilmagan.")
        return

    text = f"📚 <b>Anime Katalogi</b>\n\n📋 Jami: <b>{total}</b> ta anime"
    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.catalog_keyboard(anime_list, page, total_pages))


# ─── EPISODES ────────────────────────────────────────────────────────────────

def _show_episodes(chat_id, message_id, telegram_id, user, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, "❌ Anime topilmadi.")
        return

    # Premium check
    if anime["premium"] and not is_premium_active(user["premium_until"]):
        text = (
            f"🔒 <b>Bu anime Premium uchun</b>\n\n"
            f"💎 <b>{escape(anime['title'])}</b> faqat premium foydalanuvchilar uchun.\n\n"
            "Premium xarid qilish uchun tugmani bosing:"
        )
        api.edit_message_text(
            chat_id, message_id, text,
            reply_markup=kb.inline([
                [("💎 Premium olish", "premium_menu")],
                [("⬅️ Orqaga", f"anime:{anime_id}")],
            ]),
        )
        return

    episodes = db.get_episodes(anime_id)
    if not episodes:
        api.edit_message_text(
            chat_id, message_id,
            f"📺 <b>{escape(anime['title'])}</b>\n\n❌ Hali qismlar qo'shilmagan.",
            reply_markup=kb.inline([[("⬅️ Orqaga", f"anime:{anime_id}")]]),
        )
        return

    text = (
        f"📺 <b>{escape(anime['title'])}</b>\n\n"
        f"📋 Jami: <b>{len(episodes)}</b> qism\n\n"
        "Qismni tanlang:"
    )
    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.episodes_keyboard(episodes, anime_id))


def _play_episode(chat_id, telegram_id, user, anime_id: int, episode_number: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, "❌ Anime topilmadi.")
        return

    # Premium check
    if anime["premium"] and not is_premium_active(user["premium_until"]):
        api.send_message(
            chat_id,
            "🔒 Bu qism Premium uchun. Premium olish uchun:\n/start",
            reply_markup=kb.inline([[("💎 Premium olish", "premium_menu")]]),
        )
        return

    episode = db.get_episode_by_number(anime_id, episode_number)
    if not episode:
        api.send_message(chat_id, "❌ Qism topilmadi.")
        return

    caption = (
        f"🎬 <b>{escape(anime['title'])}</b>\n"
        f"📺 <b>{episode_number}-qism</b>"
    )
    if episode["title"]:
        caption += f": {escape(episode['title'])}"

    result = api.send_video(
        chat_id,
        video=episode["video_file_id"],
        caption=caption,
        reply_markup=kb.inline([[("⬅️ Qismlar", f"watch:{anime_id}")]]),
    )
    if not result:
        api.send_message(chat_id,
                         "❌ Video yuborishda xatolik yuz berdi. Keyinroq urinib ko'ring.")


# ─── FAVORITES ────────────────────────────────────────────────────────────────

def _toggle_favorite(query_id, chat_id, message_id, telegram_id, user, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.answer_callback_query(query_id, "❌ Anime topilmadi.", show_alert=True)
        return

    if db.is_favorite(user["id"], anime_id):
        db.remove_favorite(user["id"], anime_id)
        api.answer_callback_query(query_id, "❌ Sevimlilardan o'chirildi.", show_alert=False)
    else:
        db.add_favorite(user["id"], anime_id)
        api.answer_callback_query(query_id, "⭐ Sevimlilarga qo'shildi!", show_alert=False)

    # Refresh the anime page
    is_fav = db.is_favorite(user["id"], anime_id)
    unknown = "Noma'lum"
    premium_badge = "💎 <b>PREMIUM</b>\n" if anime["premium"] else ""
    text = (
        f"{premium_badge}"
        f"🎬 <b>{escape(anime['title'])}</b>\n"
        f"🆔 ID: <code>{anime_id}</code>\n"
        f"🎭 Janr: {escape(anime['genre'] or unknown)}\n"
        f"📅 Yil: {anime['year'] or unknown}\n"
        f"🌍 Mamlakat: {escape(anime['country'] or unknown)}\n"
        f"🌐 Til: {escape(anime['language'] or unknown)}\n\n"
        f"<b>Tavsif:</b>\n{escape(truncate(anime['description'] or '', 500))}"
    )
    api.edit_message_text(
        chat_id, message_id, text,
        reply_markup=kb.anime_page_keyboard(anime_id, is_fav=is_fav, back_callback="catalog:0"),
    )


def _show_favorites(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    favs = db.get_favorites(user["id"])
    if not favs:
        api.send_message(
            chat_id,
            "⭐ <b>Sevimlilar</b>\n\nHali sevimli anime qo'shmadingiz.",
            reply_markup=kb.main_menu(),
        )
        return
    api.send_message(
        chat_id,
        f"⭐ <b>Sevimlilar</b>\n\n📋 Jami: <b>{len(favs)}</b> ta",
        reply_markup=kb.favorites_keyboard(favs),
    )


# ─── PROFILE ─────────────────────────────────────────────────────────────────

def _show_profile(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    premium_status = "✅ Aktiv" if is_premium_active(user["premium_until"]) else "❌ Yo'q"
    uname = "@" + escape(user["username"]) if user["username"] else "Yo'q"
    fname = escape(user["first_name"] or "Noma'lum")
    text = (
        "👤 <b>Profilingiz</b>\n\n"
        f"🆔 ID: <code>{user['telegram_id']}</code>\n"
        f"📛 Ism: {fname}\n"
        f"👤 Username: {uname}\n"
        f"💰 Balans: <b>{format_currency(user['balance'])}</b>\n"
        f"💎 Premium: {premium_status}\n"
        f"📅 Premium tugash: {format_premium_until(user['premium_until'])}\n"
        f"👥 Referallar: <b>{user['referrals']}</b>\n"
        f"📆 Ro'yxatdan o'tgan: {user['created_at'][:10]}"
    )
    api.send_message(chat_id, text, reply_markup=kb.main_menu())


# ─── BALANCE ─────────────────────────────────────────────────────────────────

def _show_balance(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    ref_link = f"https://t.me/{BOT_USERNAME}?start={telegram_id}"
    text = (
        "💰 <b>Balansingiz</b>\n\n"
        f"💳 Joriy balans: <b>{format_currency(user['balance'])}</b>\n\n"
        "💡 Balansni ko'paytirish uchun do'stlarni taklif qiling!\n"
        f"🎁 Har bir referal uchun: <b>{format_currency(REFERRAL_BONUS)}</b>\n\n"
        f"🔗 Sizning havolangiz:\n<code>{ref_link}</code>"
    )
    api.send_message(chat_id, text, reply_markup=kb.main_menu())


# ─── PREMIUM ─────────────────────────────────────────────────────────────────

def _show_premium_menu(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    status = "✅ Aktiv" if is_premium_active(user["premium_until"]) else "❌ Aktiv emas"
    until = format_premium_until(user["premium_until"])

    text = (
        "💎 <b>Premium</b>\n\n"
        f"📌 Holat: {status}\n"
        f"📅 Tugash sanasi: {until}\n"
        f"💰 Balansingiz: <b>{format_currency(user['balance'])}</b>\n\n"
        "Premium rejasini tanlang:"
    )
    api.send_message(chat_id, text, reply_markup=kb.premium_keyboard())


def _show_premium_inline(chat_id: int, message_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    status = "✅ Aktiv" if is_premium_active(user["premium_until"]) else "❌ Aktiv emas"
    until = format_premium_until(user["premium_until"])

    text = (
        "💎 <b>Premium</b>\n\n"
        f"📌 Holat: {status}\n"
        f"📅 Tugash sanasi: {until}\n"
        f"💰 Balansingiz: <b>{format_currency(user['balance'])}</b>\n\n"
        "Premium rejasini tanlang:"
    )
    api.edit_message_text(chat_id, message_id, text, reply_markup=kb.premium_keyboard())


def _show_premium_confirm(chat_id, message_id, telegram_id, user, days: str):
    from config import PREMIUM_PRICES
    prices = PREMIUM_PRICES
    price = pmt.get_premium_price(days)
    if price is None:
        api.send_message(chat_id, "❌ Noto'g'ri reja.")
        return

    plan_labels = {"7": "7 kun", "30": "30 kun", "365": "1 yil"}
    plan_label = plan_labels.get(days, f"{days} kun")

    text = (
        f"💎 <b>Premium — {plan_label}</b>\n\n"
        f"💰 Narx: <b>{format_currency(price)}</b>\n"
        f"💳 Sizning balansingiz: <b>{format_currency(user['balance'])}</b>\n\n"
        "Sotib olishni tasdiqlaysizmi?"
    )
    api.edit_message_text(
        chat_id, message_id, text,
        reply_markup=kb.premium_confirm_keyboard(days, price),
    )


def _buy_premium(chat_id, message_id, telegram_id, days: str):
    result = pmt.purchase_premium(telegram_id, days)
    if result["success"]:
        api.edit_message_text(
            chat_id, message_id, result["message"],
            reply_markup=kb.inline([[("🏠 Asosiy menyu", "main_menu")]]),
        )
    else:
        api.edit_message_text(
            chat_id, message_id, result["message"],
            reply_markup=kb.inline([
                [("💎 Premium rejalar", "premium_menu")],
                [("🏠 Asosiy menyu", "main_menu")],
            ]),
        )


# ─── REFERRAL ─────────────────────────────────────────────────────────────────

def _show_referral(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    ref_link = f"https://t.me/{BOT_USERNAME}?start={telegram_id}"
    text = (
        "🎁 <b>Referal tizimi</b>\n\n"
        f"👥 Sizning referallaringiz: <b>{user['referrals']}</b>\n"
        f"💰 Har bir referal uchun bonus: <b>{format_currency(REFERRAL_BONUS)}</b>\n\n"
        "📤 Quyidagi havola orqali do'stlaringizni taklif qiling:\n\n"
        f"🔗 <code>{ref_link}</code>\n\n"
        "💡 Do'stingiz botga qo'shilganda sizga bonus yoziladi!"
    )
    api.send_message(chat_id, text, reply_markup=kb.main_menu())


# ─── ADMIN CALLBACK DISPATCHER ────────────────────────────────────────────────

def _handle_admin_callback(chat_id: int, message_id: int, telegram_id: int, args: list):
    if not args:
        adm.show_admin_menu(chat_id)
        return

    sub = args[0]

    if sub == "menu":
        adm.show_admin_menu(chat_id)
    elif sub == "add_anime":
        adm.start_add_anime(chat_id)
    elif sub == "add_episode":
        adm.start_add_episode(chat_id)
    elif sub == "edit_anime":
        adm.start_edit_anime(chat_id)
    elif sub == "delete_anime":
        adm.start_delete_anime(chat_id)
    elif sub == "users":
        adm.start_user_search(chat_id)
    elif sub == "stats":
        adm.show_stats(chat_id)
    elif sub == "channels":
        adm.show_channels_admin(chat_id)
    elif sub == "balance":
        adm.start_user_search(chat_id)
    elif sub == "premium":
        api.send_message(chat_id,
                         "💎 <b>Premium berish</b>\n\nFoydalanuvchi ID sini kiriting:",
                         reply_markup=kb.back_to_admin())
        adm.set_session(chat_id, step="search_user_id", data={})
    elif sub == "settings":
        adm.show_settings(chat_id)
    elif sub == "broadcast":
        adm.start_broadcast(chat_id)
    elif sub == "close":
        api.send_message(chat_id, "✅ Admin panel yopildi.", reply_markup=kb.main_menu())
    else:
        adm.show_admin_menu(chat_id)
