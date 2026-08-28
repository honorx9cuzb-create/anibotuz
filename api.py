"""
api.py — Telegram Bot API client using ONLY Python standard library (urllib).
Implements all required Telegram methods with retry/backoff logic.
Python 3.9 compatible — no union type hints (X | Y syntax).
"""

import json
import logging
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, List

from config import BOT_TOKEN, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telegram.org/bot{}".format(BOT_TOKEN)


class TelegramError(Exception):
    """Raised when Telegram API returns an error."""
    def __init__(self, description: str, error_code: int = 0):
        self.description = description
        self.error_code = error_code
        super().__init__("[{}] {}".format(error_code, description))


def _call(method: str, data: Optional[dict] = None, retry: bool = True) -> object:
    """
    Call a Telegram Bot API method via HTTPS POST with JSON body.
    Returns the 'result' field on success.
    Raises TelegramError on API errors.
    Never retries on 4xx client errors.
    """
    url = "{}/{}".format(BASE_URL, method)
    data = data or {}
    attempts = MAX_RETRIES if retry else 1
    last_exception = None

    for attempt in range(1, attempts + 1):
        try:
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()

            result = json.loads(raw.decode("utf-8"))

            if not result.get("ok"):
                err_desc = result.get("description", "Unknown error")
                err_code = result.get("error_code", 0)
                # Do not retry client errors
                if err_code in (400, 401, 403, 404):
                    raise TelegramError(err_desc, err_code)
                raise TelegramError(err_desc, err_code)

            return result.get("result")

        except TelegramError:
            raise
        except urllib.error.HTTPError as exc:
            last_exception = exc
            logger.warning("HTTP error on {} (attempt {}): {} {}".format(
                method, attempt, exc.code, exc.reason))
        except urllib.error.URLError as exc:
            last_exception = exc
            logger.warning("URL error on {} (attempt {}): {}".format(
                method, attempt, exc.reason))
        except json.JSONDecodeError as exc:
            last_exception = exc
            logger.warning("JSON decode error on {} (attempt {}): {}".format(
                method, attempt, exc))
        except Exception as exc:
            last_exception = exc
            logger.warning("Unexpected error on {} (attempt {}): {}".format(
                method, attempt, exc))

        if attempt < attempts:
            wait = min(RETRY_DELAY * attempt, 30)
            logger.info("Retrying {} in {}s...".format(method, wait))
            time.sleep(wait)

    logger.error("All {} attempts failed for {}: {}".format(attempts, method, last_exception))
    raise TelegramError(str(last_exception))


# ─── GETME ────────────────────────────────────────────────────────────────────

def get_me() -> dict:
    return _call("getMe")


# ─── GETUPDATES ───────────────────────────────────────────────────────────────

def get_updates(offset: Optional[int] = None, timeout: int = 30,
                allowed_updates: Optional[List[str]] = None) -> list:
    """Long-polling. Returns list of updates (never raises, returns [] on error)."""
    data = {"timeout": timeout}
    if offset is not None:
        data["offset"] = offset
    if allowed_updates is not None:
        data["allowed_updates"] = allowed_updates
    try:
        result = _call("getUpdates", data, retry=False)
        return result or []
    except Exception as exc:
        logger.warning("getUpdates error: {}".format(exc))
        return []


# ─── SEND MESSAGE ─────────────────────────────────────────────────────────────

def send_message(chat_id: int, text: str, parse_mode: str = "HTML",
                 reply_markup: Optional[dict] = None,
                 disable_web_page_preview: bool = True) -> Optional[dict]:
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        return _call("sendMessage", data)
    except TelegramError as exc:
        logger.warning("sendMessage to {} failed: {}".format(chat_id, exc))
        return None


# ─── SEND PHOTO ───────────────────────────────────────────────────────────────

def send_photo(chat_id: int, photo: str, caption: str = "",
               parse_mode: str = "HTML",
               reply_markup: Optional[dict] = None) -> Optional[dict]:
    data = {
        "chat_id": chat_id,
        "photo": photo,
        "parse_mode": parse_mode,
    }
    if caption:
        data["caption"] = caption
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        return _call("sendPhoto", data)
    except TelegramError as exc:
        logger.warning("sendPhoto to {} failed: {}".format(chat_id, exc))
        return None


# ─── SEND VIDEO ───────────────────────────────────────────────────────────────

def send_video(chat_id: int, video: str, caption: str = "",
               parse_mode: str = "HTML",
               reply_markup: Optional[dict] = None) -> Optional[dict]:
    """Send video using Telegram file_id. Never downloads the video file."""
    data = {
        "chat_id": chat_id,
        "video": video,
        "parse_mode": parse_mode,
    }
    if caption:
        data["caption"] = caption
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        return _call("sendVideo", data)
    except TelegramError as exc:
        logger.warning("sendVideo to {} failed: {}".format(chat_id, exc))
        return None


# ─── EDIT MESSAGE TEXT ────────────────────────────────────────────────────────

def edit_message_text(chat_id: int, message_id: int, text: str,
                      parse_mode: str = "HTML",
                      reply_markup: Optional[dict] = None,
                      disable_web_page_preview: bool = True) -> Optional[dict]:
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        return _call("editMessageText", data)
    except TelegramError as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("editMessageText failed: {}".format(exc))
        return None


# ─── EDIT MESSAGE REPLY MARKUP ────────────────────────────────────────────────

def edit_message_reply_markup(chat_id: int, message_id: int,
                               reply_markup: Optional[dict] = None) -> Optional[dict]:
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup or {},
    }
    try:
        return _call("editMessageReplyMarkup", data)
    except TelegramError as exc:
        logger.warning("editMessageReplyMarkup failed: {}".format(exc))
        return None


# ─── ANSWER CALLBACK QUERY ────────────────────────────────────────────────────

def answer_callback_query(callback_query_id: str, text: str = "",
                          show_alert: bool = False) -> bool:
    data = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert,
    }
    try:
        _call("answerCallbackQuery", data)
        return True
    except TelegramError as exc:
        logger.warning("answerCallbackQuery failed: {}".format(exc))
        return False


# ─── GET CHAT MEMBER ──────────────────────────────────────────────────────────

def get_chat_member(chat_id: str, user_id: int) -> Optional[dict]:
    data = {"chat_id": chat_id, "user_id": user_id}
    try:
        return _call("getChatMember", data)
    except TelegramError as exc:
        logger.warning("getChatMember failed chat={} user={}: {}".format(
            chat_id, user_id, exc))
        return None


# ─── DELETE MESSAGE ───────────────────────────────────────────────────────────

def delete_message(chat_id: int, message_id: int) -> bool:
    data = {"chat_id": chat_id, "message_id": message_id}
    try:
        _call("deleteMessage", data)
        return True
    except TelegramError as exc:
        logger.warning("deleteMessage failed: {}".format(exc))
        return False


# ─── FORWARD MESSAGE ──────────────────────────────────────────────────────────

def forward_message(chat_id: int, from_chat_id: int,
                    message_id: int) -> Optional[dict]:
    data = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }
    try:
        return _call("forwardMessage", data)
    except TelegramError as exc:
        logger.warning("forwardMessage failed: {}".format(exc))
        return None


# ─── SEND CHAT ACTION ─────────────────────────────────────────────────────────

def send_chat_action(chat_id: int, action: str = "typing") -> bool:
    """action: typing, upload_video, upload_photo, etc."""
    data = {"chat_id": chat_id, "action": action}
    try:
        _call("sendChatAction", data)
        return True
    except TelegramError as exc:
        logger.warning("sendChatAction failed: {}".format(exc))
        return False


# ─── SUBSCRIPTION CHECK ───────────────────────────────────────────────────────

def is_subscribed(chat_id: str, user_id: int) -> bool:
    """Check if a user is a member/admin/creator of a channel."""
    member = get_chat_member(chat_id, user_id)
    if not member:
        return False
    status = member.get("status", "")
    return status in ("creator", "administrator", "member")
