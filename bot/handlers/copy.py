"""
Copy trading handler — start/stop copy trading, view positions, force close.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import copy_control_keyboard, open_positions_keyboard, back_button
from bot.middlewares import auth_check
from bot.menus import COPY_MENU, COPY_POSITIONS, COPY_FORCE_CLOSE
from core.logger import get_logger

logger = get_logger(__name__)


async def copy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display copy trading control panel."""
    if not await auth_check(update, context):
        return -1

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain)
    is_active = bool(config and config.get("is_enabled", 0))

    text = (
        "🚦 <b>COPY TRADING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Status: {'🟢 Active' if is_active else '🔴 Stopped'}\n"
        f"Chain: {chain}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )
    keyboard = copy_control_keyboard(is_active)

    query = update.callback_query
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")

    return COPY_MENU


async def copy_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start copy trading for the current chain."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")

    # Verify user has at least one wallet and one whale on this chain
    wallets = await db.list_wallets_by_chain(user_id, chain)
    whales = await db.list_whales(user_id)
    chain_whales = [w for w in whales if w["chain"] == chain]

    if not wallets:
        await query.edit_message_text(
            f"⚠️ No {chain} wallet found. Create one first!",
            reply_markup=back_button("menu_copy"),
        )
        return COPY_MENU

    if not chain_whales:
        await query.edit_message_text(
            f"⚠️ No whale wallets added for {chain}. Add one first!",
            reply_markup=back_button("menu_copy"),
        )
        return COPY_MENU

    # Enable copy trading
    await db.upsert_copy_config(user_id, chain, {"is_enabled": 1})

    await query.edit_message_text(
        f"✅ Copy trading <b>STARTED</b> on {chain}!\n\n"
        f"🐋 Tracking {len(chain_whales)} whale(s)\n"
        f"💰 Using wallet: <code>{wallets[0]['address'][:10]}...</code>",
        reply_markup=back_button("menu_copy"),
        parse_mode="HTML",
    )
    return COPY_MENU


async def copy_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stop copy trading for the current chain."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")

    await db.upsert_copy_config(user_id, chain, {"is_enabled": 0})

    await query.edit_message_text(
        f"⏹️ Copy trading <b>STOPPED</b> on {chain}.",
        reply_markup=back_button("menu_copy"),
        parse_mode="HTML",
    )
    return COPY_MENU


async def copy_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show open positions."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")

    trades = await db.list_open_trades(user_id, chain)
    total_pnl = sum(float(t.get("pnl_usd", 0)) for t in trades)

    text = (
        "📈 <b>OPEN POSITIONS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Chain: {chain} | Positions: {len(trades)}\n"
        f"Total PnL: {'🟢' if total_pnl >= 0 else '🔴'} ${total_pnl:+,.2f}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = open_positions_keyboard(trades)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    return COPY_POSITIONS


async def copy_force_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt to select a position to force close."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    trades = await db.list_open_trades(user_id, chain)

    if not trades:
        await query.edit_message_text(
            "No open positions to close.",
            reply_markup=back_button("menu_copy"),
        )
        return COPY_MENU

    buttons = []
    for t in trades[:10]:
        symbol = t.get("token_symbol", "?")
        amount = t.get("amount_in_usd", 0)
        buttons.append([InlineKeyboardButton(
            f"⚡ Close {symbol} (${amount:.2f})",
            callback_data=f"force_close_{t['id']}"
        )])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_copy")])

    await query.edit_message_text(
        "⚡ Select position to force close:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return COPY_FORCE_CLOSE


async def force_close_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Execute force close for a trade."""
    query = update.callback_query
    await query.answer()

    trade_id = int(query.data.replace("force_close_", ""))
    copy_engine = context.bot_data.get("copy_engine")

    if copy_engine:
        await copy_engine.close_trade(trade_id, "MANUAL")
        await query.edit_message_text(
            "✅ Position force-closed.",
            reply_markup=back_button("menu_copy"),
        )
    else:
        await query.edit_message_text(
            "⚠️ Copy engine not available.",
            reply_markup=back_button("menu_copy"),
        )

    return COPY_MENU
