"""
/start command handler — onboarding wizard and passphrase setup.
First interaction point for new and returning users.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import main_dashboard_keyboard
from bot.middlewares import auth_check
from core.logger import get_logger

logger = get_logger(__name__)

WELCOME_MESSAGE = (
    "🚀 <b>WHALE SNIPER PRO</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Welcome to the ultimate on-chain sniper and copy-trading bot!\n"
    "🔹 <b>Multi-Chain</b>: ETH, BSC & Solana natively\n"
    "🔹 <b>Speed</b>: Sub-second copy execution engine\n"
    "🔹 <b>Security</b>: 100% self-hosted, local encryption\n"
    "🔹 <b>Advanced</b>: Auto-trailing stops & MEV protection\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🔐 <b>Master Configuration</b>\n"
    "To begin, set your Global Encryption Passphrase.\n"
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
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "<i>Tip: Switch chains to view different active wallets and configurations.</i>"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle the /start command. If user is new, begin onboarding wizard.
    If returning, show the dashboard.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        ConversationHandler state.
    """
    if not await auth_check(update, context):
        return -1  # ConversationHandler.END

    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name or str(user_id)

    db = context.bot_data.get("db")
    auth = context.bot_data.get("auth")

    # Ensure user exists in DB
    is_admin = auth.is_admin(user_id) if auth else False
    await db.ensure_user(user_id, username, is_admin)

    # Check if session already active
    if auth and not auth.is_session_locked(user_id):
        # Already unlocked → go to dashboard
        return await show_dashboard(update, context)

    # New session → ask for passphrase
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="HTML",
    )
    return 200  # AUTH_PASSPHRASE state


async def handle_passphrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle passphrase input from user during onboarding or session unlock.

    Args:
        update: Telegram update with passphrase text.
        context: Bot context.

    Returns:
        ConversationHandler state.
    """
    passphrase = update.message.text.strip()

    # Delete the passphrase message immediately for security
    try:
        await update.message.delete()
    except Exception:
        pass

    if len(passphrase) < 6:
        await update.effective_chat.send_message(
            "⚠️ Passphrase must be at least 6 characters. Try again:"
        )
        return 200

    user_id = update.effective_user.id
    auth = context.bot_data.get("auth")

    if auth:
        auth.set_session_passphrase(user_id, passphrase)

    await update.effective_chat.send_message(
        "🔓 Session unlocked! Your passphrase is stored only in memory.\n\n"
        "Loading dashboard..."
    )

    return await show_dashboard(update, context)


async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Display the main dashboard with current status.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        ConversationHandler DASHBOARD state.
    """
    user_id = update.effective_user.id
    db = context.bot_data.get("db")

    # Get current chain (default ETH)
    chain = context.user_data.get("chain", "ETH")

    # Check copy trading status
    config = await db.get_copy_config(user_id, chain)
    is_copy_active = bool(config and config.get("is_enabled", 0))

    # Count whales and open positions
    whales = await db.list_whales(user_id)
    whale_count = len(whales)
    open_positions = await db.count_open_trades(user_id, chain)

    from config.constants import CHAIN_INFO
    chain_info = CHAIN_INFO.get(chain, {})
    copy_status = "🟢 Active" if is_copy_active else "🔴 Stopped"

    text = DASHBOARD_MESSAGE.format(
        chain_emoji=chain_info.get("emoji", ""),
        chain_name=chain_info.get("name", chain),
        copy_status=copy_status,
        whale_count=whale_count,
        open_positions=open_positions,
    )

    keyboard = main_dashboard_keyboard(is_copy_active, chain)

    # Try to edit existing message, else send new
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=keyboard, parse_mode="HTML"
            )
        except Exception:
            await update.effective_chat.send_message(
                text, reply_markup=keyboard, parse_mode="HTML"
            )
    else:
        await update.effective_chat.send_message(
            text, reply_markup=keyboard, parse_mode="HTML"
        )

    return 1  # DASHBOARD state
