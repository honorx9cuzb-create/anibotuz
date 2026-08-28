"""
api.py — Telegram Bot API client using only Python standard library (urllib).
Implements all required Telegram methods with retry/backoff logic.
"""

import json
import logging
import time
import urllib.request
import urllib.parse
import urllib.error
from config import BOT_TOKEN, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


class TelegramError(Exception):
    """Raised when Telegram API returns an error."""
    def __init__(self, description: str, error_code: int = 0):
        self.description = description
        self.error_code = error_code
        super().__init__(f"[{error_code}] {description}")


def telegram(method: str, data: dict = None, files: dict = None,
             retry: bool = True) -> dict:
    """
    Call a Telegram Bot API method.
    Returns the 'result' field on success.
    Raises TelegramError on Telegram API errors.
    """
    url = f"{BASE_URL}/{method}"
    data = data or {}

    last_exception = None
    attempts = MAX_RETRIES if retry else 1

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
                # Don't retry for client errors (4xx-like codes)
                if err_code in (400, 401, 403, 404):
                    raise TelegramError(err_desc, err_code)
                raise TelegramError(err_desc, err_code)

            return result.get("result")

        except TelegramError:
            raise
        except urllib.error.HTTPError as e:
            last_exception = e
            logger.warning(f"HTTP error on {method} (attempt {attempt}): {e.code} {e.reason}")
        except urllib.error.URLError as e:
            last_exception = e
            logger.warning(f"URL error on {method} (attempt {attempt}): {e.reason}")
        except json.JSONDecodeError as e:
            last_exception = e
            logger.warning(f"JSON decode error on {method} (attempt {attempt}): {e}")
        except Exception as e:
            last_exception = e
            logger.warning(f"Unexpected error on {method} (attempt {attempt}): {e}")

        if attempt < attempts:
            wait = RETRY_DELAY * attempt
            logger.info(f"Retrying {method} in {wait}s...")
            time.sleep(wait)

    logger.error(f"All {attempts} attempts failed for {method}: {last_exception}")
    raise TelegramError(str(last_exception))


# ─── GETME ───────────────────────────────────────────────────────────────────

def get_me() -> dict:
    return telegram("getMe")


# ─── GETUPDATES ──────────────────────────────────────────────────────────────

def get_updates(offset: int = None, timeout: int = 30,
                allowed_updates: list = None) -> list:
    data = {"timeout": timeout}
    if offset is not None:
        data["offset"] = offset
    if allowed_updates is not None:
        data["allowed_updates"] = allowed_updates
    try:
        result = telegram("getUpdates", data, retry=False)
        return result or []
    except TelegramError as e:
        logger.warning(f"getUpdates error: {e}")
        return []
    except Exception as e:
        logger.warning(f"getUpdates unexpected error: {e}")
        return []


# ─── SEND MESSAGE ─────────────────────────────────────────────────────────────

def send_message(chat_id: int, text: str, parse_mode: str = "HTML",
                 reply_markup: dict = None, disable_web_page_preview: bool = True) -> dict | None:
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        return telegram("sendMessage", data)
    except TelegramError as e:
        logger.warning(f"sendMessage to {chat_id} failed: {e}")
        return None


# ─── SEND VIDEO ───────────────────────────────────────────────────────────────

def send_video(chat_id: int, video: str, caption: str = "",
               parse_mode: str = "HTML", reply_markup: dict = None) -> dict | None:
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
        return telegram("sendVideo", data)
    except TelegramError as e:
        logger.warning(f"sendVideo to {chat_id} failed: {e}")
        return None


# ─── SEND PHOTO ───────────────────────────────────────────────────────────────

def send_photo(chat_id: int, photo: str, caption: str = "",
               parse_mode: str = "HTML", reply_markup: dict = None) -> dict | None:
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
        return telegram("sendPhoto", data)
    except TelegramError as e:
        logger.warning(f"sendPhoto to {chat_id} failed: {e}")
        return None


# ─── EDIT MESSAGE TEXT ────────────────────────────────────────────────────────

def edit_message_text(chat_id: int, message_id: int, text: str,
                      parse_mode: str = "HTML",
                      reply_markup: dict = None,
                      disable_web_page_preview: bool = True) -> dict | None:
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
        return telegram("editMessageText", data)
    except TelegramError as e:
        if "message is not modified" not in str(e).lower():
            logger.warning(f"editMessageText failed: {e}")
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
        telegram("answerCallbackQuery", data)
        return True
    except TelegramError as e:
        logger.warning(f"answerCallbackQuery failed: {e}")
        return False


# ─── GET CHAT MEMBER ─────────────────────────────────────────────────────────

def get_chat_member(chat_id: str, user_id: int) -> dict | None:
    data = {"chat_id": chat_id, "user_id": user_id}
    try:
        return telegram("getChatMember", data)
    except TelegramError as e:
        logger.warning(f"getChatMember failed for chat={chat_id} user={user_id}: {e}")
        return None


# ─── DELETE MESSAGE ──────────────────────────────────────────────────────────

def delete_message(chat_id: int, message_id: int) -> bool:
    data = {"chat_id": chat_id, "message_id": message_id}
    try:
        telegram("deleteMessage", data)
        return True
    except TelegramError as e:
        logger.warning(f"deleteMessage failed: {e}")
        return False


# ─── SUBSCRIPTION CHECK ──────────────────────────────────────────────────────

def is_subscribed(chat_id: str, user_id: int) -> bool:
    """Check if a user is subscribed to a channel."""
    member = get_chat_member(chat_id, user_id)
    if not member:
        return False
    status = member.get("status", "")
    return status in ("creator", "administrator", "member")
