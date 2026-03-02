"""
Kill switch handler — emergency panic sell ALL positions across all chains.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import DASHBOARD, KILL_SWITCH_CONFIRM, COPY_MENU
from core.logger import get_logger

logger = get_logger(__name__)


async def kill_switch_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show kill switch confirmation with position summary."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    trades = await db.list_all_open_trades_for_user(user_id)

    if not trades:
        await query.edit_message_text(
            "✅ No open positions to close.",
            reply_markup=back_button("menu_dashboard"),
        )
        return DASHBOARD

    total_invested = sum(float(t.get("amount_in_usd", 0)) for t in trades)
    chains = set(t["chain"] for t in trades)

    text = (
        "🚨 <b>EMERGENCY KILL SWITCH</b> 🚨\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ This will SELL ALL {len(trades)} positions\n"
        f"   across {len(chains)} chain(s)!\n\n"
        f"💰 Total at risk: ${total_invested:,.2f}\n"
        f"⛓️ Chains: {', '.join(chains)}\n\n"
        "<b>This action cannot be undone!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [InlineKeyboardButton("🚨 YES — SELL EVERYTHING", callback_data="kill_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="menu_dashboard")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return KILL_SWITCH_CONFIRM


async def kill_switch_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Execute emergency sell of ALL positions."""
    query = update.callback_query
    await query.answer("🚨 Executing kill switch...", show_alert=True)

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    copy_engine = context.bot_data.get("copy_engine")

    trades = await db.list_all_open_trades_for_user(user_id)

    closed = 0
    failed = 0
    for trade in trades:
        try:
            if copy_engine:
                await copy_engine.close_trade(trade["id"], "KILL_SWITCH")
            else:
                await db.update_trade(trade["id"], status="CLOSED", skip_reason="KILL_SWITCH")
            closed += 1
        except Exception as e:
            logger.error("Kill switch failed for trade %d: %s", trade["id"], e)
            failed += 1

    # Disable copy trading on all chains
    configs = ["ETH", "BSC", "SOL"]
    for chain in configs:
        try:
            await db.upsert_copy_config(user_id, chain, {"is_enabled": 0})
        except Exception:
            pass

    text = (
        "🚨 <b>KILL SWITCH COMPLETE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Closed: {closed} position(s)\n"
        f"❌ Failed: {failed}\n"
        f"⏹️ Copy trading: STOPPED\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    await query.edit_message_text(
        text, reply_markup=back_button("menu_dashboard"), parse_mode="HTML"
    )
    return DASHBOARD
