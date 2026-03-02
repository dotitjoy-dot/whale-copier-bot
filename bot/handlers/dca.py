"""
DCA handler — Dollar Cost Averaging: split buys into smaller chunks over time.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import (
    DCA_MENU, DCA_TOKEN_ADDRESS, DCA_AMOUNT, DCA_SPLITS, DCA_INTERVAL,
    DASHBOARD,
)
from core.logger import get_logger

logger = get_logger(__name__)


async def dca_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display DCA menu with active orders."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    orders = await db.list_active_dca_orders(user_id)

    text = (
        "💰 <b>DOLLAR COST AVERAGING</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Split buys into smaller chunks over time\n"
        "to reduce impact of volatility.\n\n"
    )

    if orders:
        text += f"📋 <b>Active DCA Orders:</b> {len(orders)}\n"
        for i, o in enumerate(orders[:5], 1):
            progress = f"{o['executed_splits']}/{o['num_splits']}"
            text += (
                f"\n{i}. ${o['token_symbol']} — ${o['total_amount_usd']:.2f}\n"
                f"   Progress: {progress} | Every {o['interval_minutes']}m\n"
            )
    else:
        text += "No active DCA orders.\n"

    text += "\n━━━━━━━━━━━━━━━━━━━━━━━"

    buttons = [
        [InlineKeyboardButton("➕ New DCA Order", callback_data="dca_new")],
    ]
    # Add cancel buttons for active orders
    for o in orders[:5]:
        buttons.append([
            InlineKeyboardButton(
                f"❌ Cancel ${o['token_symbol']} DCA",
                callback_data=f"dca_cancel_{o['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard")])

    target = query if query else update
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return DCA_MENU


async def dca_new_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for token address for DCA."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 Enter the <b>token contract address</b> for DCA:",
        parse_mode="HTML",
    )
    return DCA_TOKEN_ADDRESS


async def dca_token_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle token address input."""
    address = update.message.text.strip()
    if len(address) < 20:
        await update.effective_chat.send_message("⚠️ Invalid address. Try again:")
        return DCA_TOKEN_ADDRESS

    context.user_data["dca_token"] = address
    await update.effective_chat.send_message(
        f"✅ Token: <code>{address[:8]}...{address[-6:]}</code>\n\n"
        "💵 Enter <b>total amount in USD</b> to DCA (e.g., 100):",
        parse_mode="HTML",
    )
    return DCA_AMOUNT


async def dca_amount_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle total amount input."""
    try:
        amount = float(update.message.text.strip())
        if amount < 1 or amount > 100000:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter a valid amount ($1-$100,000):")
        return DCA_AMOUNT

    context.user_data["dca_amount"] = amount
    await update.effective_chat.send_message(
        f"✅ Total: ${amount:.2f}\n\n"
        "🔢 How many splits? (e.g., 5 = buy 5 times):",
    )
    return DCA_SPLITS


async def dca_splits_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle number of splits input."""
    try:
        splits = int(update.message.text.strip())
        if splits < 2 or splits > 100:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter a number between 2 and 100:")
        return DCA_SPLITS

    context.user_data["dca_splits"] = splits
    amount = context.user_data.get("dca_amount", 0)
    per_split = amount / splits

    await update.effective_chat.send_message(
        f"✅ Splits: {splits} (${per_split:.2f} each)\n\n"
        "⏱️ Interval between buys in <b>minutes</b> (e.g., 10):",
        parse_mode="HTML",
    )
    return DCA_INTERVAL


async def dca_interval_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle interval input and create the DCA order."""
    try:
        interval = int(update.message.text.strip())
        if interval < 1 or interval > 10080:  # max 7 days
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter minutes (1-10080):")
        return DCA_INTERVAL

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    token = context.user_data.get("dca_token", "")
    amount = context.user_data.get("dca_amount", 0)
    splits = context.user_data.get("dca_splits", 5)

    order_id = await db.create_dca_order(
        telegram_id=user_id, chain=chain, token_address=token,
        token_symbol=token[:8], total_amount_usd=amount,
        num_splits=splits, interval_minutes=interval,
    )

    per_split = amount / splits
    total_time = splits * interval

    await update.effective_chat.send_message(
        "✅ <b>DCA ORDER CREATED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: <code>{token[:8]}...</code>\n"
        f"💰 Total: ${amount:.2f}\n"
        f"🔢 Splits: {splits} × ${per_split:.2f}\n"
        f"⏱️ Every {interval} min (~{total_time} min total)\n"
        f"🆔 Order ID: #{order_id}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=back_button("menu_dca"),
        parse_mode="HTML",
    )
    return DCA_MENU


async def dca_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel an active DCA order."""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.replace("dca_cancel_", ""))
    db = context.bot_data.get("db")
    await db.update_dca_order(order_id, status="CANCELLED")

    await query.answer("✅ DCA order cancelled", show_alert=True)
    return await dca_menu(update, context)
