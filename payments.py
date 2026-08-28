"""
payments.py — Premium purchase and balance management for ANIME BOT PRO v4.
All purchases deduct from internal balance. No external payment gateway.
Python 3.9 compatible. Standard library only.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import database as db
from utils import make_transaction_id, format_currency
from config import PREMIUM_PRICES

logger = logging.getLogger(__name__)


def get_premium_price(days: str) -> Optional[int]:
    """Return price for a premium plan in UZS, or None if invalid."""
    prices = _get_current_prices()
    return prices.get(str(days))


def _get_current_prices() -> dict:
    """Get current premium prices (from DB settings if overridden, else config)."""
    prices = {}
    for days, price in PREMIUM_PRICES.items():
        db_price = db.get_setting(f"premium_price_{days}")
        if db_price:
            try:
                prices[days] = int(db_price)
            except ValueError:
                prices[days] = price
        else:
            prices[days] = price
    return prices


def purchase_premium(telegram_id: int, days: str) -> dict:
    """
    Attempt to purchase premium for `days` using internal balance.
    Returns:
        {
            'success': bool,
            'message': str,
            'new_balance': int,
            'premium_until': str
        }
    """
    days = str(days)
    price = get_premium_price(days)
    if price is None:
        return {"success": False, "message": "Noto'g'ri premium reja.", "new_balance": 0, "premium_until": None}

    user = db.get_user(telegram_id)
    if not user:
        return {"success": False, "message": "Foydalanuvchi topilmadi.", "new_balance": 0, "premium_until": None}

    if user["balance"] < price:
        shortage = price - user["balance"]
        return {
            "success": False,
            "message": (
                "❌ Balans yetarli emas.\n\n"
                "💰 Sizning balansingiz: <b>{}</b>\n"
                "💎 Kerakli summa: <b>{}</b>\n"
                "📉 Yetishmayapti: <b>{}</b>"
            ).format(
                format_currency(user["balance"]),
                format_currency(price),
                format_currency(shortage),
            ),
            "new_balance": user["balance"],
            "premium_until": user["premium_until"],
        }

    # Determine new expiry: extend existing premium if still active
    now = datetime.utcnow()
    current_expiry = None
    if user["premium_until"]:
        try:
            current_expiry = datetime.strptime(user["premium_until"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            current_expiry = None

    if current_expiry and current_expiry > now:
        new_expiry = current_expiry + timedelta(days=int(days))
    else:
        new_expiry = now + timedelta(days=int(days))

    new_expiry_str = new_expiry.strftime("%Y-%m-%d %H:%M:%S")

    # Deduct balance
    deducted = db.remove_balance(telegram_id, price)
    if not deducted:
        return {
            "success": False,
            "message": "❌ Balans yetarli emas.",
            "new_balance": user["balance"],
            "premium_until": user["premium_until"],
        }

    # Set premium
    db.set_premium(telegram_id, new_expiry_str)

    # Record payment
    txid = make_transaction_id()
    db.create_payment(
        user_id=user["id"],
        amount=price,
        provider="balance",
        transaction_id=txid,
        status="completed",
    )

    updated_user = db.get_user(telegram_id)

    logger.info(
        "Premium purchased: user={} days={} price={} until={} txid={}".format(
            telegram_id, days, price, new_expiry_str, txid)
    )

    plan_labels = {"7": "7 kun", "30": "30 kun", "90": "90 kun", "365": "1 yil"}
    plan_label = plan_labels.get(days, "{} kun".format(days))

    return {
        "success": True,
        "message": (
            "✅ <b>Premium muvaffaqiyatli faollashtirildi!</b>\n\n"
            "💎 Reja: <b>{}</b>\n"
            "📅 Tugash sanasi: <b>{}</b>\n"
            "💰 Hisobdan yechildi: <b>{}</b>\n"
            "💳 Qoldiq balans: <b>{}</b>"
        ).format(
            plan_label,
            new_expiry.strftime("%d.%m.%Y"),
            format_currency(price),
            format_currency(updated_user["balance"]),
        ),
        "new_balance": updated_user["balance"],
        "premium_until": new_expiry_str,
    }


def admin_add_balance(telegram_id: int, amount: int, admin_id: int) -> dict:
    """Admin adds balance to a user."""
    user = db.get_user(telegram_id)
    if not user:
        return {"success": False, "message": "Foydalanuvchi topilmadi."}

    db.add_balance(telegram_id, amount)
    updated = db.get_user(telegram_id)

    txid = make_transaction_id()
    db.create_payment(
        user_id=user["id"],
        amount=amount,
        provider="admin:{}".format(admin_id),
        transaction_id=txid,
        status="completed",
    )

    logger.info("Admin {} added {} UZS to user {}".format(admin_id, amount, telegram_id))
    return {
        "success": True,
        "message": (
            "✅ Balans muvaffaqiyatli qo'shildi!\n\n"
            "👤 Foydalanuvchi: {}\n"
            "💰 Qo'shildi: <b>{}</b>\n"
            "💳 Yangi balans: <b>{}</b>"
        ).format(telegram_id, format_currency(amount), format_currency(updated["balance"])),
    }


def admin_remove_balance(telegram_id: int, amount: int, admin_id: int) -> dict:
    """Admin removes balance from a user."""
    user = db.get_user(telegram_id)
    if not user:
        return {"success": False, "message": "Foydalanuvchi topilmadi."}

    if user["balance"] < amount:
        return {
            "success": False,
            "message": "❌ Foydalanuvchi balansi yetarli emas.\nMavjud: {}".format(
                format_currency(user["balance"])),
        }

    db.remove_balance(telegram_id, amount)
    updated = db.get_user(telegram_id)

    logger.info("Admin {} removed {} UZS from user {}".format(admin_id, amount, telegram_id))
    return {
        "success": True,
        "message": (
            "✅ Balans muvaffaqiyatli ayirildi!\n\n"
            "👤 Foydalanuvchi: {}\n"
            "💸 Ayirildi: <b>{}</b>\n"
            "💳 Yangi balans: <b>{}</b>"
        ).format(telegram_id, format_currency(amount), format_currency(updated["balance"])),
    }


def admin_give_premium(telegram_id: int, days: str, admin_id: int) -> dict:
    """Admin grants premium to a user for free."""
    user = db.get_user(telegram_id)
    if not user:
        return {"success": False, "message": "Foydalanuvchi topilmadi."}

    now = datetime.utcnow()
    current_expiry = None
    if user["premium_until"]:
        try:
            current_expiry = datetime.strptime(user["premium_until"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            current_expiry = None

    if current_expiry and current_expiry > now:
        new_expiry = current_expiry + timedelta(days=int(days))
    else:
        new_expiry = now + timedelta(days=int(days))

    new_expiry_str = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
    db.set_premium(telegram_id, new_expiry_str)

    logger.info("Admin {} gave premium to user {} for {} days".format(
        admin_id, telegram_id, days))
    return {
        "success": True,
        "message": (
            "✅ Premium berildi!\n\n"
            "👤 Foydalanuvchi: {}\n"
            "💎 Davomiyligi: <b>{} kun</b>\n"
            "📅 Tugash sanasi: <b>{}</b>"
        ).format(telegram_id, days, new_expiry.strftime("%d.%m.%Y")),
    }
