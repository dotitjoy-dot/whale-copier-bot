"""
Chain handler — handles switching the active blockchain in the dashboard.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import chain_selector_keyboard
from bot.menus import CHAIN_SELECT
from config.constants import CHAIN_INFO
from core.logger import get_logger

logger = get_logger(__name__)


async def chain_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show chain selection menu from the dashboard."""
    query = update.callback_query
    await query.answer()

    chain = context.user_data.get("chain", "ETH")
    await query.edit_message_text(
        "⛓️ <b>SELECT CHAIN</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        "All settings, wallets, and whales apply per-chain:\n"
        "Select a network to switch your dashboard context:",
        reply_markup=chain_selector_keyboard(chain),
        parse_mode="HTML",
    )
    return CHAIN_SELECT


async def chain_switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the actual switching of the active chain."""
    from bot.handlers.start import show_dashboard

    query = update.callback_query
    await query.answer()

    # Callback data is like "chain_select_BSC"
    new_chain = query.data.replace("chain_select_", "")
    
    if new_chain in CHAIN_INFO:
        context.user_data["chain"] = new_chain
        chain_name = CHAIN_INFO[new_chain].get("name", new_chain)
        emoji = CHAIN_INFO[new_chain].get("emoji", "⛓️")
        await query.answer(f"Switched context to {emoji} {chain_name}")
    
    # Send user back to dashboard with the new chain context
    return await show_dashboard(update, context)
