"""
Limit order handler — place simulated "limit buys" that execute when price dips.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import (
    LIMIT_ORDER_MENU, LIMIT_ORDER_TOKEN, LIMIT_ORDER_PRICE,
    LIMIT_ORDER_AMOUNT, DASHBOARD,
)
from core.logger import get_logger

logger = get_logger(__name__)


async def limit_order_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display limit orders menu with pending orders."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    pending = await db.list_limit_orders(user_id, "PENDING")
    filled = await db.list_limit_orders(user_id, "FILLED")

    text = (
        "🎯 <b>LIMIT ORDERS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Set buy orders that execute when\n"
        "price dips to your target.\n\n"
    )

    if pending:
        text += f"⏳ <b>Pending:</b> {len(pending)}\n"
        for i, o in enumerate(pending[:5], 1):
            sym = o.get("token_symbol") or o["token_address"][:8]
            text += (
                f"  {i}. {sym} @ ${o['target_price']:.10g}\n"
                f"     Amount: ${o['amount_usd']:.2f}\n"
            )
        text += "\n"

    if filled:
        text += f"✅ <b>Recently Filled:</b> {len(filled)}\n"
        for o in filled[:3]:
            sym = o.get("token_symbol") or o["token_address"][:8]
            text += f"  • {sym} @ ${o['target_price']:.10g} (${o['amount_usd']:.2f})\n"

    text += "\n━━━━━━━━━━━━━━━━━━━━━━━"

    buttons = [
        [InlineKeyboardButton("➕ New Limit Order", callback_data="limit_new")],
    ]
    for o in pending[:5]:
        sym = o.get("token_symbol") or o["token_address"][:6]
        buttons.append([
            InlineKeyboardButton(
                f"❌ Cancel {sym} limit",
                callback_data=f"limit_cancel_{o['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard")])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return LIMIT_ORDER_MENU


async def limit_new_token_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for token address."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 Enter the <b>token contract address</b> for limit buy:",
        parse_mode="HTML",
    )
    return LIMIT_ORDER_TOKEN


async def limit_token_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle token address input."""
    address = update.message.text.strip()
    if len(address) < 20:
        await update.effective_chat.send_message("⚠️ Invalid address. Try again:")
        return LIMIT_ORDER_TOKEN

    context.user_data["limit_token"] = address
    await update.effective_chat.send_message(
        f"✅ Token: <code>{address[:8]}...{address[-6:]}</code>\n\n"
        "💲 Enter the <b>target buy price</b> in USD\n"
        "(order fills when price drops to this):",
        parse_mode="HTML",
    )
    return LIMIT_ORDER_PRICE


async def limit_price_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle target price input."""
    try:
        price = float(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter a valid price:")
        return LIMIT_ORDER_PRICE

    context.user_data["limit_price"] = price
    await update.effective_chat.send_message(
        f"✅ Target: ${price:.10g}\n\n"
        "💰 Enter <b>amount in USD</b> to buy:",
        parse_mode="HTML",
    )
    return LIMIT_ORDER_AMOUNT


async def limit_amount_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle amount input and create the limit order."""
    try:
        amount = float(update.message.text.strip())
        if amount < 1 or amount > 100000:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter amount ($1-$100,000):")
        return LIMIT_ORDER_AMOUNT

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    token = context.user_data.get("limit_token", "")
    price = context.user_data.get("limit_price", 0)

    order_id = await db.create_limit_order(
        telegram_id=user_id, chain=chain, token_address=token,
        token_symbol=token[:8], target_price=price, amount_usd=amount,
    )

    await update.effective_chat.send_message(
        "✅ <b>LIMIT ORDER PLACED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: <code>{token[:8]}...</code>\n"
        f"💲 Buy at: ${price:.10g}\n"
        f"💰 Amount: ${amount:.2f}\n"
        f"🆔 Order ID: #{order_id}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Will execute when price drops to target.</i>",
        reply_markup=back_button("menu_limit_orders"),
        parse_mode="HTML",
    )
    return LIMIT_ORDER_MENU


async def limit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel a pending limit order."""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.replace("limit_cancel_", ""))
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    await db.cancel_limit_order(order_id, user_id)

    await query.answer("✅ Limit order cancelled", show_alert=True)
    return await limit_order_menu(update, context)
