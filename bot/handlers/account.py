"""
Account handler — allows users to view their subscription and redeem license keys.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import account_menu_keyboard
from bot.menus import ACCOUNT_MENU, ACCOUNT_LICENSE_KEY, DASHBOARD
from core.auth_manager import AuthManager, TIERS, TRIAL_DAYS
from core.logger import get_logger

logger = get_logger(__name__)

ACCOUNT_MESSAGE = (
    "💎 <b>MY ACCOUNT</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "👤 <b>User ID</b>    :: <code>{user_id}</code>\n"
    "🎯 <b>Current Tier</b> :: {tier_label}\n"
    "📅 <b>Expires at</b>   :: {expires_at}\n"
    "⏳ <b>Days Left</b>    :: <b>{days_left}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "<i>{status_note}</i>"
)


async def account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the user's account and subscription status."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    auth: AuthManager = context.bot_data.get("auth")
    
    sub = auth.get_subscription(user_id)
    tier_info = TIERS.get(sub.tier, TIERS["FREE"])
    tier_label = tier_info.get("label", sub.tier)
    
    expires_at = sub.expires_at.strftime("%Y-%m-%d") if sub.expires_at else "N/A"
    days_left = sub.days_remaining
    
    if sub.tier == "FREE":
        from datetime import timedelta
        trial_end = sub.trial_started_at + timedelta(days=TRIAL_DAYS)
        expires_at = trial_end.strftime("%Y-%m-%d")
        status_note = "Your free trial is active. Upgrade for more whales and features."
    else:
        status_note = "Thank you for being a premium member!"

    text = ACCOUNT_MESSAGE.format(
        user_id=user_id,
        tier_label=tier_label,
        expires_at=expires_at,
        days_left=days_left,
        status_note=status_note,
    )

    keyboard = account_menu_keyboard()
    
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")
        
    return ACCOUNT_MENU


async def redeem_key_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to type their license key."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🔑 <b>REDEEM LICENSE KEY</b>\n\n"
            "Please paste or type your license key below.\n"
            "Format: <code>PRO-XXXX-XXXX-XXXX</code> or <code>ELITE-XXXX-XXXX-XXXX</code>",
            parse_mode="HTML",
        )
    else:
        await update.effective_chat.send_message(
            "🔑 <b>REDEEM LICENSE KEY</b>\n\n"
            "Please paste or type your license key below.",
            parse_mode="HTML",
        )
    return ACCOUNT_LICENSE_KEY


async def redeem_key_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the license key text input."""
    key_str = update.message.text.strip()
    user_id = update.effective_user.id
    auth: AuthManager = context.bot_data.get("auth")
    db = context.bot_data.get("db")

    try:
        await update.message.delete()
    except Exception:
        pass

    success, msg = auth.redeem_key(user_id, key_str)
    if success:
        # Persist to DB
        await db.mark_key_redeemed(key_str, user_id)
        sub = auth.get_subscription(user_id)
        from bot.handlers.admin import _save_sub_to_db
        await _save_sub_to_db(db, sub)

        await update.effective_chat.send_message(
            f"🎉 <b>Success!</b>\n\n{msg}",
            parse_mode="HTML",
        )
        return await account_menu(update, context)
    else:
        await update.effective_chat.send_message(
            f"❌ <b>Error!</b>\n\n{msg}\n\nPlease try again:",
            parse_mode="HTML",
        )
        return ACCOUNT_LICENSE_KEY
