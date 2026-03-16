"""
/start command handler — public onboarding with license gate.

Flow:
  1. /start → check if user is known
  2. New user → register, start FREE trial, ask passphrase
  3. Trial expired → ask for license key
  4. Licensed/Admin → unlock session, show dashboard
  5. Banned → show banned message
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import main_dashboard_keyboard
from core.auth_manager import AuthManager, TIERS, TRIAL_DAYS
from core.logger import get_logger

logger = get_logger(__name__)

from bot.menus import ACCOUNT_LICENSE_KEY, DASHBOARD
# States
AUTH_PASSPHRASE  = 200
DASHBOARD_STATE  = 1


LOCKED_MESSAGE = (
    "🔐 <b>SESSION EXPIRED</b>\n\n"
    "Your session has been locked for security.\n"
    "Please re-enter your wallet passphrase to continue:"
)

BANNED_MESSAGE = (
    "⛔ <b>ACCESS DENIED</b>\n\n"
    "Your account has been suspended.\n"
    "Contact support if you believe this is an error."
)

TRIAL_EXPIRED_MESSAGE = (
    "⏳ <b>FREE TRIAL EXPIRED</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Your {days}-day free trial has ended.\n\n"
    "🚀 <b>Upgrade to continue:</b>\n"
    "⭐ <b>PRO</b>  — 10 whales, DCA, alerts, limit orders\n"
    "💎 <b>ELITE</b> — 50 whales, ALL features + sniper\n\n"
    "✉️ Contact the admin to purchase a license key,\n"
    "then tap <b>🔑 Redeem Key</b> to activate."
)

WELCOME_NEW_MESSAGE = (
    "🚀 <b>WHALE SNIPER PRO</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Welcome to the ultimate on-chain sniper and copy-trading bot!\n\n"
    "🔹 <b>Multi-Chain</b>: ETH, BSC &amp; Solana natively\n"
    "🔹 <b>Speed</b>: Sub-second copy execution engine\n"
    "🔹 <b>Security</b>: 100% self-hosted, local encryption\n"
    "🔹 <b>Advanced</b>: Auto-trailing stops &amp; MEV protection\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"🆓 <b>Free Trial:</b> {TRIAL_DAYS} days included!\n\n"
    "🔐 <b>Set your wallet Passphrase</b>\n"
    "<i>This passphrase locally encrypts your private keys. It is never saved.</i>\n\n"
    "⌨️ Type your passphrase below:"
)

DASHBOARD_MESSAGE = (
    "👑 <b>MAIN DASHBOARD</b> 👑\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🌐 <b>Active Network</b>    :: {chain_emoji} <b>{chain_name}</b>\n"
    "⚡ <b>Sniper Engine</b>     :: {copy_status}\n"
    "🎯 <b>Tracking Whales</b>  :: <b>{whale_count}</b>\n"
    "💼 <b>Open Trades</b>       :: <b>{open_positions}</b>\n"
    "🎯 <b>Tier</b>               :: {tier_label}\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "<i>Tip: Switch chains to view different active wallets and configurations.</i>"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: routes user based on auth/subscription state."""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name or str(user_id)

    db   = context.bot_data.get("db")
    auth: AuthManager = context.bot_data.get("auth")

    # Ensure user is registered
    is_admin = auth.is_admin(user_id) if auth else False
    await db.ensure_user(user_id, username, is_admin)

    # Admin always has access
    if is_admin:
        if auth.is_session_locked(user_id):
            await update.message.reply_text(LOCKED_MESSAGE, parse_mode="HTML")
            return AUTH_PASSPHRASE
        return await show_dashboard(update, context)

    # Load subscription from DB if not in memory
    sub = auth.get_subscription(user_id)
    db_sub = await db.get_subscription(user_id)
    if db_sub and sub.trial_started_at is not None:
        _restore_sub(auth, db_sub)
        sub = auth.get_subscription(user_id)

    # Check ban
    if sub.is_banned:
        await update.message.reply_text(BANNED_MESSAGE, parse_mode="HTML")
        return -1

    # Check if trial/subscription active
    if not sub.is_active:
        # Trial expired, no valid sub
        await update.message.reply_text(
            TRIAL_EXPIRED_MESSAGE.format(days=TRIAL_DAYS),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔑 Redeem License Key", callback_data="redeem_key")
            ]]),
            parse_mode="HTML",
        )
        return ACCOUNT_LICENSE_KEY

    # Active user — check session
    if auth.is_session_locked(user_id):
        # New user on their first start
        db_sub_row = await db.get_subscription(user_id)
        if db_sub_row is None:
            # Brand new user
            await update.message.reply_text(WELCOME_NEW_MESSAGE, parse_mode="HTML")
        else:
            await update.message.reply_text(LOCKED_MESSAGE, parse_mode="HTML")
        return AUTH_PASSPHRASE

    return await show_dashboard(update, context)


async def handle_passphrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle passphrase input during onboarding or session unlock."""
    passphrase = update.message.text.strip()

    try:
        await update.message.delete()
    except Exception:
        pass

    if len(passphrase) < 6:
        await update.effective_chat.send_message(
            "⚠️ Passphrase must be at least 6 characters. Try again:"
        )
        return AUTH_PASSPHRASE

    user_id = update.effective_user.id
    auth: AuthManager = context.bot_data.get("auth")
    db = context.bot_data.get("db")

    if auth:
        auth.set_session_passphrase(user_id, passphrase)

    # Save subscription to DB for new users
    sub = auth.get_subscription(user_id)
    db_sub = await db.get_subscription(user_id)
    if db_sub is None:
        from bot.handlers.admin import _save_sub_to_db
        await _save_sub_to_db(db, sub)

    await update.effective_chat.send_message(
        "🔓 <b>Session unlocked!</b>\nYour passphrase is stored in memory only "
        "(never saved to disk). Loading dashboard...",
        parse_mode="HTML",
    )
    return await show_dashboard(update, context)


async def handle_license_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle license key text input from user."""
    key_str = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    user_id = update.effective_user.id
    auth: AuthManager = context.bot_data.get("auth")
    db = context.bot_data.get("db")

    success, msg = auth.redeem_key(user_id, key_str)
    if success:
        # Persist to DB
        await db.mark_key_redeemed(key_str, user_id)
        sub = auth.get_subscription(user_id)
        from bot.handlers.admin import _save_sub_to_db
        await _save_sub_to_db(db, sub)

        await update.effective_chat.send_message(
            f"🎉 {msg}\n\nNow set your wallet passphrase to continue:",
            parse_mode="HTML",
        )
        return AUTH_PASSPHRASE
    else:
        await update.effective_chat.send_message(
            f"{msg}\n\nTry again or tap the button below:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔑 Enter Key", callback_data="redeem_key")
            ]]),
            parse_mode="HTML",
        )
        return ACCOUNT_LICENSE_KEY


async def prompt_license_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to type their license key."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔑 <b>ENTER LICENSE KEY</b>\n\n"
        "Type your license key below.\n"
        "Format: <code>PRO-XXXX-XXXX-XXXX</code> or <code>ELITE-XXXX-XXXX-XXXX</code>",
        parse_mode="HTML",
    )
    return ACCOUNT_LICENSE_KEY


async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the main dashboard with current status."""
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    auth: AuthManager = context.bot_data.get("auth")

    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain)
    is_copy_active = bool(config and config.get("is_enabled", 0))

    whales = await db.list_whales(user_id)
    whale_count = len(whales)
    open_positions = await db.count_open_trades(user_id, chain)

    sub = auth.get_subscription(user_id) if auth else None
    tier_label = TIERS.get(sub.tier, {}).get("label", "🆓 Free") if sub else "🆓 Free"

    from config.constants import CHAIN_INFO
    chain_info = CHAIN_INFO.get(chain, {})
    copy_status = "🟢 Active" if is_copy_active else "🔴 Stopped"

    is_admin = auth.is_admin(user_id) if auth else False

    text = DASHBOARD_MESSAGE.format(
        chain_emoji=chain_info.get("emoji", ""),
        chain_name=chain_info.get("name", chain),
        copy_status=copy_status,
        whale_count=whale_count,
        open_positions=open_positions,
        tier_label=tier_label,
    )

    keyboard = main_dashboard_keyboard(is_copy_active, chain, is_admin=is_admin)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")

    return DASHBOARD_STATE


def _restore_sub(auth: AuthManager, row: dict) -> None:
    """Restore a UserSubscription from a database row."""
    from datetime import datetime
    from core.auth_manager import UserSubscription

    expires_at = None
    if row.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(row["expires_at"])
        except ValueError:
            pass

    trial_started = datetime.utcnow()
    if row.get("trial_started_at"):
        try:
            trial_started = datetime.fromisoformat(row["trial_started_at"])
        except ValueError:
            pass

    sub = UserSubscription(
        telegram_id=row["telegram_id"],
        tier=row.get("tier", "FREE"),
        expires_at=expires_at,
        is_banned=bool(row.get("is_banned", 0)),
        trial_started_at=trial_started,
        notes=row.get("notes", ""),
    )
    auth.load_subscription(sub)
