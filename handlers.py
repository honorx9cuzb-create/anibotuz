"""
handlers.py — Main update dispatcher for ANIME BOT PRO v4.
Routes all messages and callback queries to the correct handler.
Python 3.9 compatible.
"""

import logging
import time
from typing import Optional

from config import (ADMIN_IDS, REFERRAL_BONUS, WELCOME_BONUS,
                    BOT_USERNAME, PAGINATION_SIZE)
import database as db
import api
import keyboards as kb
import admin as adm
import payments as pmt
from utils import (escape, format_currency, format_premium_until,
                   is_premium_active, safe_int, validate_referral_code,
                   truncate, build_star_rating, format_time_remaining,
                   message_rate_limiter, callback_rate_limiter)

logger = logging.getLogger(__name__)

# In-memory user session state: {telegram_id: {step, data, ts}}
user_sessions: dict = {}
SESSION_TIMEOUT = 600  # 10 minutes


def get_user_session(uid: int) -> dict:
    sess = user_sessions.get(uid, {})
    # Expire stale sessions
    if sess and time.time() - sess.get("ts", 0) > SESSION_TIMEOUT:
        user_sessions[uid] = {}
        return {}
    return sess


def set_user_session(uid: int, **kwargs):
    sess = get_user_session(uid)
    sess.update(kwargs)
    sess["ts"] = time.time()
    user_sessions[uid] = sess


def clear_user_session(uid: int):
    user_sessions[uid] = {}


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def handle_update(update: dict):
    """Main dispatcher for all Telegram updates."""
    try:
        if "message" in update:
            handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback(update["callback_query"])
    except Exception as exc:
        logger.error("Unhandled error in handle_update: {}".format(exc), exc_info=True)


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGE HANDLER
# ══════════════════════════════════════════════════════════════════════════════

def handle_message(msg: dict):
    chat_id = msg["chat"]["id"]
    user_tg = msg.get("from", {})
    telegram_id = user_tg.get("id")
    text = msg.get("text", "").strip()
    video = msg.get("video")
    document = msg.get("document")

    if not telegram_id:
        return

    # ── Rate limiting ──────────────────────────────────────────────────────
    if not adm.is_admin(telegram_id):
        if not message_rate_limiter.is_allowed(telegram_id):
            return

    # ── Register / get user ───────────────────────────────────────────────
    user = db.get_user(telegram_id)
    is_new = user is None

    if is_new:
        user = _register_user(msg, telegram_id, user_tg)
        if not user:
            return
    else:
        # Update username/first_name if changed
        _update_user_info(telegram_id, user_tg, user)

    # ── Maintenance mode (non-admins only) ────────────────────────────────
    if not adm.is_admin(telegram_id) and db.is_maintenance_mode():
        api.send_message(chat_id,
                         "🔧 <b>Texnik ishlar</b>\n\nBotda texnik ishlar olib borilmoqda.\n"
                         "Tez orada qaytamiz. ⏳")
        return

    # ── Blocked users ──────────────────────────────────────────────────────
    if user["is_blocked"] and not adm.is_admin(telegram_id):
        return

    # ── Admin flows ───────────────────────────────────────────────────────
    if adm.is_admin(telegram_id):
        sess = adm.get_session(telegram_id)
        step = sess.get("step", "")

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

        if step == "delete_episode_anime_id":
            if text:
                adm.handle_delete_episode_step(chat_id, text)
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
                adm.handle_broadcast_step(chat_id, text, msg)
            return

        if step.startswith("add_channel_"):
            if text:
                adm.handle_add_channel_step(chat_id, text)
            return

        if step == "settings_input":
            if text:
                adm.handle_settings_step(chat_id, text)
            return

        if step.startswith("add_ad_"):
            if text:
                adm.handle_add_ad_step(chat_id, text)
            return

    # ── Commands ───────────────────────────────────────────────────────────
    if text.startswith("/start"):
        _handle_start(chat_id, telegram_id, text, is_new, user)
        return

    if text == "/admin" and adm.is_admin(telegram_id):
        adm.show_admin_menu(chat_id)
        return

    if text == "/stats" and adm.is_admin(telegram_id):
        adm.show_analytics(chat_id)
        return

    if text == "/broadcast" and adm.is_admin(telegram_id):
        adm.start_broadcast(chat_id)
        return

    # ── Channel check (non-commands) ───────────────────────────────────────
    if not _check_subscriptions(chat_id, telegram_id):
        return

    # ── User session steps ─────────────────────────────────────────────────
    sess = get_user_session(telegram_id)
    step = sess.get("step", "")

    if step == "searching":
        if text:
            _handle_search_query(chat_id, telegram_id, text)
        return

    if step == "search_by_id":
        if text:
            _handle_search_by_id(chat_id, telegram_id, text)
        return

    if step == "writing_review":
        if text:
            _submit_review(chat_id, telegram_id, text, sess)
        return

    # ── Main menu buttons ──────────────────────────────────────────────────
    handlers_map = {
        "🔎 Qidirish": lambda: _start_search(chat_id, telegram_id),
        "🔢 ID qidirish": lambda: _start_id_search(chat_id, telegram_id),
        "📚 Katalog": lambda: _show_catalog_menu(chat_id, telegram_id),
        "⭐ Sevimlilar": lambda: _show_favorites(chat_id, telegram_id),
        "▶️ Davom ettirish": lambda: _show_continue_watching(chat_id, telegram_id),
        "📌 Kuzatmoqda": lambda: _show_watchlist(chat_id, telegram_id),
        "👤 Profil": lambda: _show_profile(chat_id, telegram_id),
        "🎁 Kunlik bonus": lambda: _claim_daily(chat_id, telegram_id),
        "💎 Premium": lambda: _show_premium_menu(chat_id, telegram_id),
        "🏆 Top Otaku": lambda: _show_leaderboard(chat_id, 0),
        "💰 Balans": lambda: _show_balance(chat_id, telegram_id),
        "🎁 Referal": lambda: _show_referral(chat_id, telegram_id),
        "❌ Bekor qilish": lambda: _cancel(chat_id, telegram_id),
    }

    handler = handlers_map.get(text)
    if handler:
        clear_user_session(telegram_id)
        handler()
        return

    # Unknown message
    api.send_message(chat_id, "Quyidagi menyudan tanlang:",
                     reply_markup=kb.main_menu())


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════════════════════

def handle_callback(cb: dict):
    query_id = cb["id"]
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    telegram_id = cb["from"]["id"]
    data = cb.get("data", "")

    # Rate limit callbacks
    if not adm.is_admin(telegram_id):
        if not callback_rate_limiter.is_allowed(telegram_id):
            api.answer_callback_query(query_id, "⏳ Biroz kuting...", show_alert=False)
            return

    user = db.get_user(telegram_id)
    if not user:
        api.answer_callback_query(query_id, "❌ Avval /start bosing.", show_alert=True)
        return

    # Maintenance check
    if not adm.is_admin(telegram_id) and db.is_maintenance_mode():
        api.answer_callback_query(
            query_id, "🔧 Texnik ishlar davom etmoqda.", show_alert=True)
        return

    # Blocked check
    if user["is_blocked"] and not adm.is_admin(telegram_id):
        api.answer_callback_query(query_id, "🚫 Sizning hisobingiz bloklangan.",
                                  show_alert=True)
        return

    try:
        _dispatch_callback(query_id, chat_id, message_id, telegram_id, user, data)
    except Exception as exc:
        logger.error("Callback error data={}: {}".format(data, exc), exc_info=True)
        api.answer_callback_query(query_id, "❌ Xatolik yuz berdi.", show_alert=True)


def _dispatch_callback(query_id, chat_id, message_id, telegram_id, user, data):
    parts = data.split(":")
    action = parts[0]
    args = parts[1:]

    # ── Noop ─────────────────────────────────────────────────────────────
    if action == "noop":
        api.answer_callback_query(query_id)
        return

    # ── Main menu ─────────────────────────────────────────────────────────
    if action == "main_menu":
        api.answer_callback_query(query_id)
        api.send_message(chat_id, "🏠 Asosiy menyu", reply_markup=kb.main_menu())
        return

    # ── Channel check ─────────────────────────────────────────────────────
    if action == "check_subscription":
        api.answer_callback_query(query_id)
        if _check_subscriptions(chat_id, telegram_id):
            api.send_message(chat_id,
                             "✅ Barcha kanallarga obuna bo'ldingiz!\nBotdan foydalanishingiz mumkin.",
                             reply_markup=kb.main_menu())
        return

    # ── Subscription gate ─────────────────────────────────────────────────
    if not _check_subscriptions(chat_id, telegram_id):
        api.answer_callback_query(query_id)
        return

    # ── Catalog ───────────────────────────────────────────────────────────
    if action == "catalog":
        api.answer_callback_query(query_id)
        _show_catalog_menu_inline(chat_id, message_id)
        return

    if action == "cat" and len(args) >= 2:
        api.answer_callback_query(query_id)
        sort = args[0]
        page = safe_int(args[1])
        _show_catalog_inline(chat_id, message_id, page, sort)
        return

    if action == "genres":
        api.answer_callback_query(query_id)
        api.edit_message_text(chat_id, message_id,
                              "🎭 <b>Janrlar</b>\n\nJanrni tanlang:",
                              reply_markup=kb.genres_keyboard())
        return

    if action == "genre" and len(args) >= 2:
        api.answer_callback_query(query_id)
        genre = args[0]
        page = safe_int(args[1])
        _show_genre_inline(chat_id, message_id, genre, page)
        return

    # ── Anime page ─────────────────────────────────────────────────────────
    if action == "anime" and args:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        _show_anime_page(chat_id, message_id, telegram_id, user, anime_id)
        return

    # ── Watch ──────────────────────────────────────────────────────────────
    if action == "watch" and args:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        _show_episodes(chat_id, message_id, telegram_id, user, anime_id, page=0)
        return

    if action == "ep_page" and len(args) >= 2:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        page = safe_int(args[1])
        _show_episodes(chat_id, message_id, telegram_id, user, anime_id, page=page)
        return

    # ── Episode play ───────────────────────────────────────────────────────
    if action == "episode" and len(args) >= 2:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        ep_num = safe_int(args[1])
        _play_episode(chat_id, telegram_id, user, anime_id, ep_num)
        return

    # ── Favorite toggle ────────────────────────────────────────────────────
    if action == "favorite" and args:
        anime_id = safe_int(args[0])
        _toggle_favorite(query_id, chat_id, message_id, telegram_id, user, anime_id)
        return

    # ── Follow toggle ──────────────────────────────────────────────────────
    if action == "follow" and args:
        anime_id = safe_int(args[0])
        _toggle_watchlist(query_id, chat_id, message_id, telegram_id, user, anime_id)
        return

    # ── Rate menu ──────────────────────────────────────────────────────────
    if action == "rate_menu" and args:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        api.edit_message_text(
            chat_id, message_id,
            "⭐ <b>Baholash</b>\n\nBaho qo'ying (1–5 yulduz):",
            reply_markup=kb.rating_keyboard(anime_id)
        )
        return

    # ── Submit rating ──────────────────────────────────────────────────────
    if action == "rate" and len(args) >= 2:
        anime_id = safe_int(args[0])
        score = safe_int(args[1])
        _submit_rating(query_id, chat_id, message_id, telegram_id, user, anime_id, score)
        return

    # ── Review prompt ──────────────────────────────────────────────────────
    if action == "review" and args:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        set_user_session(telegram_id, step="writing_review",
                         data={"anime_id": anime_id})
        api.send_message(
            chat_id,
            "💬 <b>Fikr qoldiring</b>\n\nAnime haqida fikringizni yozing:",
            reply_markup=kb.reply([["❌ Bekor qilish"]])
        )
        return

    # ── Share ──────────────────────────────────────────────────────────────
    if action == "share" and args:
        api.answer_callback_query(query_id)
        anime_id = safe_int(args[0])
        _show_share(chat_id, message_id, anime_id)
        return

    # ── Premium ────────────────────────────────────────────────────────────
    if action == "premium_menu":
        api.answer_callback_query(query_id)
        _show_premium_inline(chat_id, message_id, telegram_id)
        return

    if action == "premium" and args:
        api.answer_callback_query(query_id)
        days = args[0]
        _show_premium_confirm(chat_id, message_id, telegram_id, user, days)
        return

    if action == "premium_buy" and args:
        api.answer_callback_query(query_id)
        days = args[0]
        _buy_premium(chat_id, message_id, telegram_id, days)
        return

    # ── Leaderboard ────────────────────────────────────────────────────────
    if action == "leaderboard" and args:
        api.answer_callback_query(query_id)
        page = safe_int(args[0])
        _show_leaderboard_inline(chat_id, message_id, page)
        return

    # ── Admin callbacks ────────────────────────────────────────────────────
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
        logger.info("Admin {} deleted channel {}".format(telegram_id, args[0]))
        api.send_message(chat_id, "✅ Kanal o'chirildi.",
                         reply_markup=kb.admin_menu_keyboard())
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

    if action == "admin_premium_remove" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        adm.admin_remove_premium(chat_id, safe_int(args[0]))
        return

    if action == "admin_premium_plan" and adm.is_admin(telegram_id) and len(args) >= 2:
        api.answer_callback_query(query_id)
        adm.start_admin_give_premium(chat_id, safe_int(args[0]), days=args[1])
        return

    if action == "admin_block" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        target_id = safe_int(args[0])
        db.block_user(target_id)
        logger.info("Admin {} blocked user {}".format(telegram_id, target_id))
        api.send_message(chat_id, "🚫 Foydalanuvchi bloklandi: {}".format(target_id),
                         reply_markup=kb.admin_menu_keyboard())
        return

    if action == "admin_unblock" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        target_id = safe_int(args[0])
        db.unblock_user(target_id)
        logger.info("Admin {} unblocked user {}".format(telegram_id, target_id))
        api.send_message(chat_id, "✅ Foydalanuvchi blokdan chiqarildi: {}".format(target_id),
                         reply_markup=kb.admin_menu_keyboard())
        return

    if action == "broadcast_send" and adm.is_admin(telegram_id):
        api.answer_callback_query(query_id)
        adm.execute_broadcast_from_session(telegram_id, chat_id)
        return

    if action == "admin_ad" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        adm.show_ad_detail(chat_id, safe_int(args[0]))
        return

    if action == "admin_ad_toggle" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        db.toggle_ad(safe_int(args[0]))
        adm.show_ads_list(chat_id)
        return

    if action == "admin_ad_delete" and adm.is_admin(telegram_id) and args:
        api.answer_callback_query(query_id)
        db.delete_ad(safe_int(args[0]))
        api.send_message(chat_id, "✅ Reklama o'chirildi.",
                         reply_markup=kb.admin_menu_keyboard())
        return

    if action == "admin_review" and adm.is_admin(telegram_id) and len(args) >= 2:
        api.answer_callback_query(query_id)
        review_status = args[0]
        review_id = safe_int(args[1])
        db.update_review_status(review_id, review_status)
        api.send_message(chat_id,
                         "✅ Sharh {} qilindi.".format(
                             "tasdiqlandi" if review_status == "approve" else "rad etildi"),
                         reply_markup=kb.admin_menu_keyboard())
        return

    # Unknown callback
    api.answer_callback_query(query_id, "❓ Noma'lum buyruq.", show_alert=False)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN CALLBACK ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def _handle_admin_callback(chat_id, message_id, telegram_id, args):
    if not args:
        adm.show_admin_menu(chat_id)
        return

    cmd = args[0]
    routes = {
        "menu":          lambda: adm.show_admin_menu(chat_id),
        "anime_menu":    lambda: adm.show_anime_menu(chat_id),
        "episode_menu":  lambda: adm.show_episode_menu(chat_id),
        "add_anime":     lambda: adm.start_add_anime(chat_id),
        "edit_anime":    lambda: adm.start_edit_anime(chat_id),
        "delete_anime":  lambda: adm.start_delete_anime(chat_id),
        "list_anime":    lambda: adm.list_anime(chat_id),
        "add_episode":   lambda: adm.start_add_episode(chat_id),
        "delete_episode":lambda: adm.start_delete_episode(chat_id),
        "users":         lambda: adm.start_user_search(chat_id),
        "premium_menu":  lambda: adm.show_premium_menu(chat_id),
        "payments":      lambda: adm.show_payments(chat_id),
        "channels":      lambda: adm.show_channels_admin(chat_id),
        "broadcast":     lambda: adm.start_broadcast(chat_id),
        "ads_menu":      lambda: adm.show_ads_list(chat_id),
        "add_ad":        lambda: adm.start_add_ad(chat_id),
        "analytics":     lambda: adm.show_analytics(chat_id),
        "reviews":       lambda: adm.show_pending_reviews(chat_id),
        "backup":        lambda: adm.do_backup(chat_id),
        "export":        lambda: adm.do_export(chat_id),
        "settings":      lambda: adm.show_settings(chat_id),
        "maintenance":   lambda: adm.toggle_maintenance(chat_id),
        "close":         lambda: api.send_message(chat_id, "👋 Admin panel yopildi.",
                                                   reply_markup=kb.main_menu()),
    }
    fn = routes.get(cmd)
    if fn:
        fn()
    else:
        adm.show_admin_menu(chat_id)


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

def _register_user(msg: dict, telegram_id: int, user_tg: dict):
    username = user_tg.get("username", "") or ""
    first_name = user_tg.get("first_name", "") or ""
    last_name = user_tg.get("last_name", "") or ""
    text = msg.get("text", "")
    referred_by = None

    if text.startswith("/start "):
        ref_code = text[7:].strip()
        # Deep link: anime_123 or episode_123_5
        if ref_code.startswith("anime_"):
            pass  # handled in _handle_start
        elif ref_code.startswith("episode_"):
            pass
        else:
            ref_id = validate_referral_code(ref_code)
            if ref_id and ref_id != telegram_id:
                referrer = db.get_user(ref_id)
                if referrer:
                    referred_by = ref_id

    user = db.create_user(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        referred_by=referred_by,
        welcome_bonus=WELCOME_BONUS,
    )

    logger.info("New user: {} (@{}) referred_by={}".format(
        telegram_id, username, referred_by))

    if referred_by:
        referrer = db.get_user(referred_by)
        # Prevent re-rewarding (referral_count check)
        if referrer:
            db.add_referral(referred_by, REFERRAL_BONUS)
            db.add_xp(referred_by, 50)
            logger.info("Referral bonus {} -> user {}".format(REFERRAL_BONUS, referred_by))

    return user


def _update_user_info(telegram_id: int, user_tg: dict, existing_user):
    """Update username/first_name if they changed."""
    new_username = user_tg.get("username", "") or ""
    new_first = user_tg.get("first_name", "") or ""
    changes = {}
    if new_username and new_username != (existing_user["username"] or ""):
        changes["username"] = new_username
    if new_first and new_first != (existing_user["first_name"] or ""):
        changes["first_name"] = new_first
    if changes:
        db.update_user(telegram_id, **changes)


# ══════════════════════════════════════════════════════════════════════════════
# START
# ══════════════════════════════════════════════════════════════════════════════

def _handle_start(chat_id: int, telegram_id: int, text: str, is_new: bool, user):
    clear_user_session(telegram_id)

    # Deep link parsing
    if text.startswith("/start "):
        param = text[7:].strip()

        if param.startswith("anime_"):
            anime_id = safe_int(param[6:])
            if anime_id > 0:
                _show_anime_page_text(chat_id, None, telegram_id, user,
                                      db.get_anime(anime_id))
                return

        elif param.startswith("episode_"):
            parts = param[8:].split("_")
            if len(parts) >= 2:
                anime_id = safe_int(parts[0])
                ep_num = safe_int(parts[1])
                if anime_id > 0 and ep_num > 0:
                    _play_episode(chat_id, telegram_id, user, anime_id, ep_num)
                    return

    fname = escape(user["first_name"] or "Do'st")
    if is_new:
        welcome = (
            "👋 Xush kelibsiz, <b>{}</b>!\n\n"
            "🎌 <b>ANIME BOT PRO v4</b> — Sizning anime dunyangiz!\n\n"
            "🎁 Ro'yxatdan o'tganingiz uchun: <b>{}</b> bonus!\n\n"
            "📚 Minglab anime va qismlar sizni kutmoqda.\n"
            "💎 Premium obuna bilan premium kontentga kirish!\n"
            "🏆 XP to'plab darajangizni oshiring!"
        ).format(fname, format_currency(WELCOME_BONUS))
        api.send_message(chat_id, welcome, reply_markup=kb.main_menu())
    else:
        api.send_message(
            chat_id,
            "👋 Salom, <b>{}</b>!\n\nQuyidagi menyudan tanlang:".format(fname),
            reply_markup=kb.main_menu(),
        )


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION CHECK
# ══════════════════════════════════════════════════════════════════════════════

def _check_subscriptions(chat_id: int, telegram_id: int) -> bool:
    channels = db.get_required_channels()
    if not channels:
        return True

    not_subscribed = []
    for ch in channels:
        if not api.is_subscribed(ch["telegram_channel_id"], telegram_id):
            not_subscribed.append(ch)

    if not not_subscribed:
        return True

    lines = []
    for ch in not_subscribed:
        lines.append("• {}".format(escape(
            ch["title"] or ch["username"] or ch["telegram_channel_id"])))

    text = (
        "📢 <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>\n\n"
        + "\n".join(lines)
    )
    api.send_message(chat_id, text, reply_markup=kb.channels_keyboard(channels))
    return False


# ══════════════════════════════════════════════════════════════════════════════
# SEARCH
# ══════════════════════════════════════════════════════════════════════════════

def _start_search(chat_id: int, telegram_id: int):
    set_user_session(telegram_id, step="searching")
    api.send_message(chat_id,
                     "🔎 <b>Anime qidirish</b>\n\nAnime nomini kiriting:",
                     reply_markup=kb.reply([["❌ Bekor qilish"]]))


def _start_id_search(chat_id: int, telegram_id: int):
    set_user_session(telegram_id, step="search_by_id")
    api.send_message(chat_id,
                     "🔢 <b>ID orqali qidirish</b>\n\nAnime ID sini kiriting:",
                     reply_markup=kb.reply([["❌ Bekor qilish"]]))


def _handle_search_query(chat_id: int, telegram_id: int, query: str):
    clear_user_session(telegram_id)
    results = db.search_anime(query)
    if not results:
        api.send_message(
            chat_id,
            "🔎 <b>Qidiruv:</b> <i>{}</i>\n\n❌ Hech narsa topilmadi.".format(
                escape(query)),
            reply_markup=kb.main_menu(),
        )
        return
    api.send_message(
        chat_id,
        "🔎 <b>Qidiruv:</b> <i>{}</i>\n\n📋 Topildi: <b>{}</b> ta".format(
            escape(query), len(results)),
        reply_markup=kb.anime_list_keyboard(results, back_callback="main_menu"),
    )


def _handle_search_by_id(chat_id: int, telegram_id: int, text: str):
    clear_user_session(telegram_id)
    anime_id = safe_int(text.strip())
    if anime_id <= 0:
        api.send_message(chat_id, "❌ Noto'g'ri ID. Raqam kiriting:",
                         reply_markup=kb.main_menu())
        return
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id,
                         "❌ ID <code>{}</code> topilmadi.".format(anime_id),
                         reply_markup=kb.main_menu())
        return
    user = db.get_user(telegram_id)
    _show_anime_page_text(chat_id, None, telegram_id, user, anime)


def _cancel(chat_id: int, telegram_id: int):
    clear_user_session(telegram_id)
    api.send_message(chat_id, "✅ Bekor qilindi.", reply_markup=kb.main_menu())


# ══════════════════════════════════════════════════════════════════════════════
# CATALOG
# ══════════════════════════════════════════════════════════════════════════════

def _show_catalog_menu(chat_id: int, telegram_id: int):
    api.send_message(chat_id,
                     "📚 <b>Katalog</b>\n\nKatalog turini tanlang:",
                     reply_markup=kb.catalog_filter_keyboard())


def _show_catalog_menu_inline(chat_id: int, message_id: int):
    api.edit_message_text(chat_id, message_id,
                          "📚 <b>Katalog</b>\n\nKatalog turini tanlang:",
                          reply_markup=kb.catalog_filter_keyboard())


def _show_catalog_inline(chat_id: int, message_id: int, page: int,
                         sort: str = "new"):
    if sort == "premium":
        total = db.get_anime_count()
        anime_list = db.get_premium_anime(
            limit=PAGINATION_SIZE, offset=page * PAGINATION_SIZE)
    elif sort == "featured":
        anime_list = db.get_featured_anime(limit=PAGINATION_SIZE)
        total = len(anime_list)
    else:
        total = db.get_anime_count()
        anime_list = db.get_anime_catalog(
            offset=page * PAGINATION_SIZE, limit=PAGINATION_SIZE, sort=sort)

    total_pages = max(1, (total + PAGINATION_SIZE - 1) // PAGINATION_SIZE)
    page = max(0, min(page, total_pages - 1))

    sort_labels = {
        "new": "🆕 Yangi", "trending": "🔥 Trending",
        "rating": "⭐ Reyting", "views": "👁 Ko'p ko'rilgan",
        "favorites": "❤️ Ko'p saqlangan", "premium": "💎 Premium",
        "featured": "🎯 Featured",
    }
    label = sort_labels.get(sort, "Katalog")

    if not anime_list:
        api.edit_message_text(chat_id, message_id,
                              "📚 Hali anime qo'shilmagan.",
                              reply_markup=kb.catalog_filter_keyboard())
        return

    text = "📚 <b>{}</b>\n\n📋 Jami: <b>{}</b> ta anime".format(label, total)
    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.catalog_keyboard(
                              anime_list, page, total_pages, sort))


def _show_genre_inline(chat_id: int, message_id: int,
                       genre: str, page: int):
    anime_list = db.get_anime_by_genre(genre, offset=page * PAGINATION_SIZE,
                                       limit=PAGINATION_SIZE)
    total_count = len(db.get_anime_by_genre(genre, offset=0, limit=9999))
    total_pages = max(1, (total_count + PAGINATION_SIZE - 1) // PAGINATION_SIZE)

    if not anime_list:
        api.edit_message_text(chat_id, message_id,
                              "🎭 <b>{}</b>\n\n❌ Bu janrda anime topilmadi.".format(
                                  escape(genre)),
                              reply_markup=kb.genres_keyboard())
        return

    text = "🎭 <b>{}</b>\n\n📋 Topildi: <b>{}</b> ta".format(
        escape(genre), total_count)
    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.catalog_keyboard(
                              anime_list, page, total_pages,
                              sort="genre:{}".format(genre)))


# ══════════════════════════════════════════════════════════════════════════════
# ANIME PAGE
# ══════════════════════════════════════════════════════════════════════════════

def _show_anime_page(chat_id: int, message_id: int, telegram_id: int,
                     user, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, "❌ Anime topilmadi.", reply_markup=kb.main_menu())
        return
    _show_anime_page_text(chat_id, message_id, telegram_id, user, anime)


def _show_anime_page_text(chat_id: int, message_id: Optional[int],
                           telegram_id: int, user, anime):
    if not anime:
        api.send_message(chat_id, "❌ Anime topilmadi.", reply_markup=kb.main_menu())
        return

    anime_id = anime["id"]
    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0
    is_fav = db.is_favorite(user_id, anime_id) if user_id else False
    is_following = db.is_in_watchlist(user_id, anime_id) if user_id else False
    user_rating = db.get_user_rating(user_id, anime_id) if user_id else 0

    unknown = "Noma'lum"
    eps = db.get_episodes(anime_id)
    ep_count = len(eps)
    rating_str = "{:.1f} ⭐ ({})".format(
        anime["rating"] or 0.0, anime["rating_count"] or 0)
    premium_badge = "💎 <b>PREMIUM</b>\n" if anime["premium"] else ""
    featured_badge = "🎯 <b>FEATURED</b>\n" if anime["featured"] else ""

    text = (
        "{}{}"
        "🎬 <b>{}</b>\n"
        "{}"
        "🆔 ID: <code>{}</code>\n"
        "⭐ Reyting: {}\n"
        "👁 Ko'rishlar: <b>{}</b>\n"
        "📅 Yil: {}\n"
        "🎭 Janr: {}\n"
        "🌍 Mamlakat: {}\n"
        "🌐 Til: {}\n"
        "📌 Status: {}\n"
        "📺 Qismlar: <b>{}</b>\n\n"
        "<b>Tavsif:</b>\n{}"
    ).format(
        premium_badge, featured_badge,
        escape(anime["title"]),
        ("📝 <i>{}</i>\n".format(escape(anime["original_title"]))
         if anime["original_title"] else ""),
        anime_id,
        rating_str,
        anime["views"] or 0,
        anime["year"] or unknown,
        escape(anime["genre"] or unknown),
        escape(anime["country"] or unknown),
        escape(anime["language"] or unknown),
        escape(anime["status"] or "ongoing"),
        ep_count,
        escape(truncate(anime["description"] or "", 600)),
    )

    markup = kb.anime_page_keyboard(
        anime_id, is_fav=is_fav, is_following=is_following,
        user_rating=user_rating, back_callback="cat:new:0"
    )

    if anime.get("poster"):
        if message_id:
            api.send_photo(chat_id, anime["poster"], caption=text, reply_markup=markup)
        else:
            api.send_photo(chat_id, anime["poster"], caption=text, reply_markup=markup)
    else:
        if message_id:
            api.edit_message_text(chat_id, message_id, text, reply_markup=markup)
        else:
            api.send_message(chat_id, text, reply_markup=markup)

    # Increment view count
    db.increment_anime_views(anime_id)


# ══════════════════════════════════════════════════════════════════════════════
# EPISODES
# ══════════════════════════════════════════════════════════════════════════════

def _show_episodes(chat_id, message_id, telegram_id, user,
                   anime_id: int, page: int = 0):
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, "❌ Anime topilmadi.")
        return

    # Premium gate
    if anime["premium"] and not is_premium_active(user["premium_until"]):
        text = (
            "🔒 <b>Bu anime Premium uchun</b>\n\n"
            "💎 <b>{}</b> faqat premium foydalanuvchilar uchun.\n\n"
            "Premium xarid qilish uchun:"
        ).format(escape(anime["title"]))
        api.edit_message_text(
            chat_id, message_id, text,
            reply_markup=kb.inline([
                [("💎 Premium olish", "premium_menu")],
                [("⬅️ Orqaga", "anime:{}".format(anime_id))],
            ]),
        )
        return

    episodes = db.get_episodes(anime_id)
    if not episodes:
        api.edit_message_text(
            chat_id, message_id,
            "📺 <b>{}</b>\n\n❌ Hali qismlar qo'shilmagan.".format(
                escape(anime["title"])),
            reply_markup=kb.inline([[("⬅️ Orqaga", "anime:{}".format(anime_id))]]),
        )
        return

    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0
    last_watched = db.get_last_watched(user_id, anime_id) if user_id else None

    continue_text = ""
    if last_watched:
        continue_text = "\n▶️ Oxirgi ko'rilgan: <b>{}-qism</b>".format(
            last_watched["episode_number"])

    text = (
        "📺 <b>{}</b>\n\n"
        "📋 Jami: <b>{}</b> qism{}\n\n"
        "Qismni tanlang:"
    ).format(escape(anime["title"]), len(episodes), continue_text)

    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.episodes_keyboard(episodes, anime_id, page))


def _play_episode(chat_id, telegram_id, user, anime_id: int, episode_number: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, "❌ Anime topilmadi.")
        return

    # Premium gate
    if anime["premium"] and not is_premium_active(user["premium_until"]):
        api.send_message(
            chat_id,
            "🔒 Bu qism Premium uchun.\n💎 Premium olish uchun menyudan tanlang.",
            reply_markup=kb.inline([[("💎 Premium olish", "premium_menu")]]),
        )
        return

    episode = db.get_episode_by_number(anime_id, episode_number)
    if not episode:
        api.send_message(chat_id, "❌ Qism topilmadi.")
        return

    caption = "🎬 <b>{}</b>\n📺 <b>{}-qism</b>".format(
        escape(anime["title"]), episode_number)
    if episode["title"]:
        caption += ": {}".format(escape(episode["title"]))

    result = api.send_video(
        chat_id,
        video=episode["video_file_id"],
        caption=caption,
        reply_markup=kb.inline([
            [("⬅️ Qismlar", "watch:{}".format(anime_id))],
            [("⭐ Sevimlilarga", "favorite:{}".format(anime_id))],
        ]),
    )

    if result:
        # Track watch history and XP
        db_user = db.get_user(telegram_id)
        if db_user:
            db.add_watch_history(db_user["id"], anime_id, episode["id"])
            db.increment_episode_views(episode["id"])
            db.add_xp(telegram_id, 5)
    else:
        api.send_message(chat_id,
                         "❌ Video yuborishda xatolik. Keyinroq urinib ko'ring.")


# ══════════════════════════════════════════════════════════════════════════════
# FAVORITES
# ══════════════════════════════════════════════════════════════════════════════

def _toggle_favorite(query_id, chat_id, message_id,
                     telegram_id, user, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.answer_callback_query(query_id, "❌ Anime topilmadi.", show_alert=True)
        return

    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0

    if db.is_favorite(user_id, anime_id):
        db.remove_favorite(user_id, anime_id)
        api.answer_callback_query(query_id, "❌ Sevimlilardan o'chirildi.")
    else:
        db.add_favorite(user_id, anime_id)
        api.answer_callback_query(query_id, "⭐ Sevimlilarga qo'shildi!")
        db.add_xp(telegram_id, 2)

    # Refresh anime page
    is_fav = db.is_favorite(user_id, anime_id)
    is_following = db.is_in_watchlist(user_id, anime_id)
    user_rating = db.get_user_rating(user_id, anime_id)

    unknown = "Noma'lum"
    eps_count = len(db.get_episodes(anime_id))
    rating_str = "{:.1f} ⭐ ({})".format(
        anime["rating"] or 0.0, anime["rating_count"] or 0)
    premium_badge = "💎 <b>PREMIUM</b>\n" if anime["premium"] else ""
    text = (
        "{}🎬 <b>{}</b>\n"
        "🆔 ID: <code>{}</code>\n"
        "⭐ Reyting: {}\n"
        "👁 Ko'rishlar: <b>{}</b>\n"
        "📅 Yil: {}\n"
        "🎭 Janr: {}\n"
        "📺 Qismlar: <b>{}</b>\n\n"
        "<b>Tavsif:</b>\n{}"
    ).format(
        premium_badge, escape(anime["title"]),
        anime_id, rating_str, anime["views"] or 0,
        anime["year"] or unknown,
        escape(anime["genre"] or unknown),
        eps_count,
        escape(truncate(anime["description"] or "", 400)),
    )
    api.edit_message_text(
        chat_id, message_id, text,
        reply_markup=kb.anime_page_keyboard(
            anime_id, is_fav=is_fav, is_following=is_following,
            user_rating=user_rating)
    )


def _show_favorites(chat_id: int, telegram_id: int):
    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0
    favs = db.get_favorites(user_id)
    if not favs:
        api.send_message(
            chat_id,
            "⭐ <b>Sevimlilar</b>\n\nHali sevimli anime qo'shmadingiz.",
            reply_markup=kb.main_menu(),
        )
        return
    api.send_message(
        chat_id,
        "⭐ <b>Sevimlilar</b>\n\n📋 Jami: <b>{}</b> ta".format(len(favs)),
        reply_markup=kb.favorites_keyboard(favs),
    )


# ══════════════════════════════════════════════════════════════════════════════
# WATCHLIST
# ══════════════════════════════════════════════════════════════════════════════

def _toggle_watchlist(query_id, chat_id, message_id,
                      telegram_id, user, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.answer_callback_query(query_id, "❌ Anime topilmadi.", show_alert=True)
        return

    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0

    if db.is_in_watchlist(user_id, anime_id):
        db.remove_watchlist(user_id, anime_id)
        api.answer_callback_query(query_id, "📌 Kuzatuvdan o'chirildi.")
    else:
        db.add_watchlist(user_id, anime_id)
        api.answer_callback_query(query_id, "📌 Kuzatishga qo'shildi!")

    # Refresh anime page
    is_fav = db.is_favorite(user_id, anime_id)
    is_following = db.is_in_watchlist(user_id, anime_id)
    user_rating = db.get_user_rating(user_id, anime_id)
    unknown = "Noma'lum"
    eps_count = len(db.get_episodes(anime_id))
    rating_str = "{:.1f} ⭐ ({})".format(
        anime["rating"] or 0.0, anime["rating_count"] or 0)
    premium_badge = "💎 <b>PREMIUM</b>\n" if anime["premium"] else ""
    text = (
        "{}🎬 <b>{}</b>\n"
        "🆔 ID: <code>{}</code>\n"
        "⭐ Reyting: {}\n"
        "📅 Yil: {}\n"
        "🎭 Janr: {}\n"
        "📺 Qismlar: <b>{}</b>\n\n"
        "<b>Tavsif:</b>\n{}"
    ).format(
        premium_badge, escape(anime["title"]),
        anime_id, rating_str,
        anime["year"] or unknown,
        escape(anime["genre"] or unknown),
        eps_count,
        escape(truncate(anime["description"] or "", 400)),
    )
    api.edit_message_text(
        chat_id, message_id, text,
        reply_markup=kb.anime_page_keyboard(
            anime_id, is_fav=is_fav, is_following=is_following,
            user_rating=user_rating)
    )


def _show_watchlist(chat_id: int, telegram_id: int):
    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0
    items = db.get_watchlist(user_id)
    if not items:
        api.send_message(
            chat_id,
            "📌 <b>Kuzatmoqda</b>\n\nHali kuzatayotgan anime yo'q.",
            reply_markup=kb.main_menu(),
        )
        return
    api.send_message(
        chat_id,
        "📌 <b>Kuzatmoqda</b>\n\n📋 Jami: <b>{}</b> ta".format(len(items)),
        reply_markup=kb.watchlist_keyboard(items),
    )


# ══════════════════════════════════════════════════════════════════════════════
# WATCH HISTORY (continue watching)
# ══════════════════════════════════════════════════════════════════════════════

def _show_continue_watching(chat_id: int, telegram_id: int):
    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0
    history = db.get_watch_history(user_id, limit=10)

    if not history:
        api.send_message(
            chat_id,
            "▶️ <b>Davom ettirish</b>\n\nHali ko'rilgan qism yo'q.",
            reply_markup=kb.main_menu(),
        )
        return

    rows = []
    seen_anime = set()
    for h in history:
        if h["anime_id"] in seen_anime:
            continue
        seen_anime.add(h["anime_id"])
        label = "▶️ {} — {}-qism".format(
            escape(h["anime_title"]), h["episode_number"])
        rows.append([(label, "watch:{}".format(h["anime_id"]))])

    rows.append([("⬅️ Orqaga", "main_menu")])
    api.send_message(
        chat_id,
        "▶️ <b>Davom ettirish</b>\n\nOxirgi ko'rilgan animeler:",
        reply_markup=kb.inline(rows),
    )


# ══════════════════════════════════════════════════════════════════════════════
# RATINGS
# ══════════════════════════════════════════════════════════════════════════════

def _submit_rating(query_id, chat_id, message_id,
                   telegram_id, user, anime_id: int, score: int):
    anime = db.get_anime(anime_id)
    if not anime:
        api.answer_callback_query(query_id, "❌ Anime topilmadi.", show_alert=True)
        return

    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0

    ok = db.rate_anime(user_id, anime_id, score)
    if ok:
        db.add_xp(telegram_id, 10)
        stars = build_star_rating(score)
        api.answer_callback_query(
            query_id, "{} Baho berildi: {}!".format(stars, score), show_alert=True)
        api.edit_message_text(
            chat_id, message_id,
            "⭐ <b>Baho berildi!</b>\n\n"
            "🎬 {}\n"
            "{}\n"
            "Bahongiz: <b>{}/5</b>".format(
                escape(anime["title"]), stars, score),
            reply_markup=kb.inline([
                [("⬅️ Anime sahifasiga", "anime:{}".format(anime_id))]
            ])
        )
    else:
        api.answer_callback_query(query_id, "❌ Xatolik yuz berdi.", show_alert=True)


# ══════════════════════════════════════════════════════════════════════════════
# REVIEWS
# ══════════════════════════════════════════════════════════════════════════════

def _submit_review(chat_id: int, telegram_id: int, text: str, sess: dict):
    clear_user_session(telegram_id)
    data = sess.get("data", {})
    anime_id = data.get("anime_id", 0)
    if not anime_id:
        api.send_message(chat_id, "❌ Xatolik. Qaytadan urinib ko'ring.",
                         reply_markup=kb.main_menu())
        return

    anime = db.get_anime(anime_id)
    if not anime:
        api.send_message(chat_id, "❌ Anime topilmadi.", reply_markup=kb.main_menu())
        return

    db_user = db.get_user(telegram_id)
    user_id = db_user["id"] if db_user else 0
    db.add_review(user_id, anime_id, text[:1000])
    db.add_xp(telegram_id, 15)

    api.send_message(
        chat_id,
        "💬 <b>Fikringiz qabul qilindi!</b>\n\n"
        "Moderatsiyadan o'tgandan so'ng nashr etiladi.\n"
        "🎬 Anime: <b>{}</b>".format(escape(anime["title"])),
        reply_markup=kb.main_menu(),
    )


# ══════════════════════════════════════════════════════════════════════════════
# SHARE
# ══════════════════════════════════════════════════════════════════════════════

def _show_share(chat_id: int, message_id: int, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        return
    deep_link = "https://t.me/{}?start=anime_{}".format(BOT_USERNAME, anime_id)
    text = (
        "📤 <b>Ulashish</b>\n\n"
        "🎬 <b>{}</b>\n\n"
        "Havola:\n<code>{}</code>"
    ).format(escape(anime["title"]), deep_link)
    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.inline([
                              [("⬅️ Orqaga", "anime:{}".format(anime_id))]
                          ]))


# ══════════════════════════════════════════════════════════════════════════════
# PROFILE
# ══════════════════════════════════════════════════════════════════════════════

def _show_profile(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    if not user:
        return
    premium_status = "✅ Aktiv" if is_premium_active(user["premium_until"]) else "❌ Yo'q"
    uname = "@{}".format(escape(user["username"])) if user["username"] else "Yo'q"
    fname = escape(user["first_name"] or "Noma'lum")
    level_name = db.get_level_name(user["level"] or 1)
    rank = db.get_user_rank(telegram_id)

    text = (
        "👤 <b>Profilingiz</b>\n\n"
        "🆔 ID: <code>{}</code>\n"
        "📛 Ism: {}\n"
        "👤 Username: {}\n"
        "🌐 Til: {}\n\n"
        "💰 Balans: <b>{}</b>\n"
        "⭐ XP: <b>{}</b>\n"
        "🎖 Daraja: <b>{} — {}</b>\n"
        "🏆 Reytingda o'rin: <b>{}</b>\n\n"
        "💎 Premium: {}\n"
        "📅 Premium tugash: {}\n"
        "👥 Referallar: <b>{}</b>\n"
        "🔥 Kunlik streak: <b>{}</b>\n"
        "📆 Ro'yxatdan o'tgan: {}"
    ).format(
        user["telegram_id"],
        fname, uname,
        user["language"] or "uz",
        format_currency(user["balance"]),
        user["xp"] or 0,
        user["level"] or 1, level_name,
        rank,
        premium_status,
        format_premium_until(user["premium_until"]),
        user["referral_count"] or 0,
        user["daily_streak"] or 0,
        (user["created_at"] or "")[:10],
    )
    api.send_message(chat_id, text, reply_markup=kb.main_menu())


# ══════════════════════════════════════════════════════════════════════════════
# DAILY BONUS
# ══════════════════════════════════════════════════════════════════════════════

def _claim_daily(chat_id: int, telegram_id: int):
    if not db.can_claim_daily(telegram_id):
        remaining = db.seconds_until_daily(telegram_id)
        api.send_message(
            chat_id,
            "⏳ <b>Kunlik bonus</b>\n\nKeyingi bonusni olish uchun:\n"
            "🕐 <b>{}</b> kuting".format(format_time_remaining(remaining)),
            reply_markup=kb.main_menu(),
        )
        return

    user = db.get_user(telegram_id)
    # Base bonus + streak multiplier
    streak = db.get_daily_streak(telegram_id)
    base_bonus = 100
    streak_bonus = min(streak * 50, 500)
    total_bonus = base_bonus + streak_bonus

    ok = db.claim_daily_reward(telegram_id, total_bonus)
    if ok:
        new_streak = db.get_daily_streak(telegram_id)
        streak_emojis = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
                         5: "5️⃣", 6: "6️⃣", 7: "7️⃣"}
        streak_emoji = streak_emojis.get(new_streak, "🔥")

        api.send_message(
            chat_id,
            "🎁 <b>Kunlik bonus!</b>\n\n"
            "{} Streak: <b>{} kun</b>\n"
            "💰 Bonus: <b>{}</b>\n"
            "✨ +10 XP\n\n"
            "Ertaga yana qayting!".format(
                streak_emoji, new_streak,
                format_currency(total_bonus)),
            reply_markup=kb.main_menu(),
        )
    else:
        api.send_message(chat_id, "❌ Xatolik yuz berdi.",
                         reply_markup=kb.main_menu())


# ══════════════════════════════════════════════════════════════════════════════
# LEADERBOARD
# ══════════════════════════════════════════════════════════════════════════════

def _show_leaderboard(chat_id: int, page: int):
    page_size = 10
    users = db.get_leaderboard(limit=page_size, offset=page * page_size)
    total = db.get_users_count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    if not users:
        api.send_message(chat_id, "🏆 Hali foydalanuvchilar yo'q.",
                         reply_markup=kb.main_menu())
        return

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    lines = []
    start_rank = page * page_size
    for i, u in enumerate(users):
        rank = start_rank + i + 1
        medal = medals.get(start_rank + i, "▪️")
        name = escape(u["first_name"] or "Foydalanuvchi")
        level_name = db.get_level_name(u["level"] or 1)
        lines.append("{} <b>{}.</b> {} — <b>{} XP</b> | {}".format(
            medal, rank, name, u["xp"] or 0, level_name))

    text = "🏆 <b>TOP OTAKU</b>\n\n" + "\n".join(lines)
    api.send_message(chat_id, text,
                     reply_markup=kb.leaderboard_keyboard(page, total_pages))


def _show_leaderboard_inline(chat_id: int, message_id: int, page: int):
    page_size = 10
    users = db.get_leaderboard(limit=page_size, offset=page * page_size)
    total = db.get_users_count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    if not users:
        api.edit_message_text(chat_id, message_id, "🏆 Hali foydalanuvchilar yo'q.")
        return

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    lines = []
    start_rank = page * page_size
    for i, u in enumerate(users):
        rank = start_rank + i + 1
        medal = medals.get(start_rank + i, "▪️")
        name = escape(u["first_name"] or "Foydalanuvchi")
        level_name = db.get_level_name(u["level"] or 1)
        lines.append("{} <b>{}.</b> {} — <b>{} XP</b> | {}".format(
            medal, rank, name, u["xp"] or 0, level_name))

    text = "🏆 <b>TOP OTAKU</b>\n\n" + "\n".join(lines)
    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.leaderboard_keyboard(page, total_pages))


# ══════════════════════════════════════════════════════════════════════════════
# BALANCE
# ══════════════════════════════════════════════════════════════════════════════

def _show_balance(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    if not user:
        return
    ref_link = "https://t.me/{}?start={}".format(BOT_USERNAME, telegram_id)
    text = (
        "💰 <b>Balansingiz</b>\n\n"
        "💳 Joriy balans: <b>{}</b>\n\n"
        "💡 Balansni ko'paytirish:\n"
        "  • Do'stlarni taklif qiling\n"
        "  • Kunlik bonus oling\n"
        "  • Anime baholang\n\n"
        "🎁 Referal bonus: <b>{}</b>\n\n"
        "🔗 Sizning havolangiz:\n<code>{}</code>"
    ).format(
        format_currency(user["balance"]),
        format_currency(REFERRAL_BONUS),
        ref_link,
    )
    api.send_message(chat_id, text, reply_markup=kb.main_menu())


# ══════════════════════════════════════════════════════════════════════════════
# PREMIUM
# ══════════════════════════════════════════════════════════════════════════════

def _show_premium_menu(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    if not user:
        return
    status = "✅ Aktiv" if is_premium_active(user["premium_until"]) else "❌ Aktiv emas"
    until = format_premium_until(user["premium_until"])
    text = (
        "💎 <b>Premium</b>\n\n"
        "📌 Holat: {}\n"
        "📅 Tugash sanasi: {}\n"
        "💰 Balansingiz: <b>{}</b>\n\n"
        "✨ Premium afzalliklari:\n"
        "  • Premium anime va qismlar\n"
        "  • Reklamasiz tajriba\n"
        "  • VIP kontent\n"
        "  • Yangi qismlarga erta kirish\n\n"
        "Premium rejasini tanlang:"
    ).format(status, until, format_currency(user["balance"]))
    api.send_message(chat_id, text, reply_markup=kb.premium_keyboard())


def _show_premium_inline(chat_id: int, message_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    if not user:
        return
    status = "✅ Aktiv" if is_premium_active(user["premium_until"]) else "❌ Aktiv emas"
    until = format_premium_until(user["premium_until"])
    text = (
        "💎 <b>Premium</b>\n\n"
        "📌 Holat: {}\n"
        "📅 Tugash sanasi: {}\n"
        "💰 Balansingiz: <b>{}</b>\n\n"
        "Premium rejasini tanlang:"
    ).format(status, until, format_currency(user["balance"]))
    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.premium_keyboard())


def _show_premium_confirm(chat_id, message_id, telegram_id, user, days: str):
    price = pmt.get_premium_price(days)
    if price is None:
        api.send_message(chat_id, "❌ Noto'g'ri reja.")
        return

    plan_labels = {"7": "7 kun", "30": "30 kun", "90": "90 kun", "365": "1 yil"}
    plan_label = plan_labels.get(days, "{} kun".format(days))

    text = (
        "💎 <b>Premium — {}</b>\n\n"
        "💰 Narx: <b>{}</b>\n"
        "💳 Sizning balansingiz: <b>{}</b>\n\n"
        "Sotib olishni tasdiqlaysizmi?"
    ).format(
        plan_label,
        format_currency(price),
        format_currency(user["balance"]),
    )
    api.edit_message_text(chat_id, message_id, text,
                          reply_markup=kb.premium_confirm_keyboard(days, price))


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
            reply_markup=kb.premium_confirm_keyboard(
                days, pmt.get_premium_price(days) or 0),
        )


# ══════════════════════════════════════════════════════════════════════════════
# REFERRAL
# ══════════════════════════════════════════════════════════════════════════════

def _show_referral(chat_id: int, telegram_id: int):
    user = db.get_user(telegram_id)
    if not user:
        return
    ref_link = "https://t.me/{}?start={}".format(BOT_USERNAME, telegram_id)
    text = (
        "🎁 <b>Referal tizimi</b>\n\n"
        "👥 Sizning referallaringiz: <b>{}</b>\n"
        "💰 Har bir referal uchun: <b>{}</b>\n"
        "⭐ Har bir referal uchun: <b>50 XP</b>\n\n"
        "🔗 Sizning referal havolangiz:\n"
        "<code>{}</code>\n\n"
        "Bu havolani do'stlaringizga yuboring!\n"
        "Ular ro'yxatdan o'tganda siz bonus olasiz."
    ).format(
        user["referral_count"] or 0,
        format_currency(REFERRAL_BONUS),
        ref_link,
    )
    api.send_message(chat_id, text, reply_markup=kb.main_menu())
