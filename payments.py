"""
payments.py — Premium purchase and balance management for Ani Telegram Bot.
All purchases deduct from internal balance. No external payment gateway.
"""

import logging
from datetime import datetime, timedelta

import database as db
from utils import make_transaction_id, premium_until_str, format_currency
from config import PREMIUM_PRICES

logger = logging.getLogger(__name__)


def get_premium_price(days: str) -> int | None:
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
            "message": f"❌ Balans yetarli emas.\n\n"
                       f"💰 Sizning balansingiz: <b>{format_currency(user['balance'])}</b>\n"
                       f"💎 Kerakli summa: <b>{format_currency(price)}</b>\n"
                       f"📉 Yetishmayapti: <b>{format_currency(shortage)}</b>",
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
        f"Premium purchased: user={telegram_id} days={days} "
        f"price={price} until={new_expiry_str} txid={txid}"
    )

    plan_labels = {"7": "7 kun", "30": "30 kun", "365": "1 yil"}
    plan_label = plan_labels.get(days, f"{days} kun")

    return {
        "success": True,
        "message": (
            f"✅ <b>Premium muvaffaqiyatli faollashtirildi!</b>\n\n"
            f"💎 Reja: <b>{plan_label}</b>\n"
            f"📅 Tugash sanasi: <b>{new_expiry.strftime('%d.%m.%Y')}</b>\n"
            f"💰 Hisobdan yechildi: <b>{format_currency(price)}</b>\n"
            f"💳 Qoldiq balans: <b>{format_currency(updated_user['balance'])}</b>"
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
        provider=f"admin:{admin_id}",
        transaction_id=txid,
        status="completed",
    )

    logger.info(f"Admin {admin_id} added {amount} UZS to user {telegram_id}")
    return {
        "success": True,
        "message": (
            f"✅ Balans muvaffaqiyatli qo'shildi!\n\n"
            f"👤 Foydalanuvchi: {telegram_id}\n"
            f"💰 Qo'shildi: <b>{format_currency(amount)}</b>\n"
            f"💳 Yangi balans: <b>{format_currency(updated['balance'])}</b>"
        ),
    }


def admin_remove_balance(telegram_id: int, amount: int, admin_id: int) -> dict:
    """Admin removes balance from a user."""
    user = db.get_user(telegram_id)
    if not user:
        return {"success": False, "message": "Foydalanuvchi topilmadi."}

    if user["balance"] < amount:
        return {
            "success": False,
            "message": f"❌ Foydalanuvchi balansi yetarli emas.\nMavjud: {format_currency(user['balance'])}",
        }

    db.remove_balance(telegram_id, amount)
    updated = db.get_user(telegram_id)

    logger.info(f"Admin {admin_id} removed {amount} UZS from user {telegram_id}")
    return {
        "success": True,
        "message": (
            f"✅ Balans muvaffaqiyatli ayirildi!\n\n"
            f"👤 Foydalanuvchi: {telegram_id}\n"
            f"💸 Ayirildi: <b>{format_currency(amount)}</b>\n"
            f"💳 Yangi balans: <b>{format_currency(updated['balance'])}</b>"
        ),
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

    logger.info(f"Admin {admin_id} gave premium to user {telegram_id} for {days} days")
    return {
        "success": True,
        "message": (
            f"✅ Premium berildi!\n\n"
            f"👤 Foydalanuvchi: {telegram_id}\n"
            f"💎 Davomiyligi: <b>{days} kun</b>\n"
            f"📅 Tugash sanasi: <b>{new_expiry.strftime('%d.%m.%Y')}</b>"
        ),
    }
