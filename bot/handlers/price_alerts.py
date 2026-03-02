"""
Price alert handler — set price alerts for any token and get notified.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import (
    PRICE_ALERT_MENU, PRICE_ALERT_TOKEN, PRICE_ALERT_PRICE,
    PRICE_ALERT_DIRECTION, DASHBOARD,
)
from core.logger import get_logger

logger = get_logger(__name__)


async def price_alert_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display active price alerts and options."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    alerts = await db.list_price_alerts(user_id)

    text = (
        "🔔 <b>PRICE ALERTS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Get notified when tokens hit your targets.\n\n"
    )

    if alerts:
        text += f"📋 <b>Active Alerts:</b> {len(alerts)}\n"
        for i, a in enumerate(alerts[:10], 1):
            direction = "📈 Above" if a["direction"] == "above" else "📉 Below"
            text += (
                f"\n{i}. ${a['token_symbol'] or a['token_address'][:8]}\n"
                f"   {direction} ${a['target_price']:.10g}\n"
            )
    else:
        text += "No active alerts.\n"

    text += "\n━━━━━━━━━━━━━━━━━━━━━━━"

    buttons = [
        [InlineKeyboardButton("➕ New Alert", callback_data="alert_new")],
    ]
    for a in alerts[:5]:
        sym = a["token_symbol"] or a["token_address"][:6]
        buttons.append([
            InlineKeyboardButton(
                f"🗑️ Remove {sym} alert",
                callback_data=f"alert_rm_{a['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard")])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return PRICE_ALERT_MENU


async def alert_new_token_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for token address."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 Enter the <b>token contract address</b> (or symbol):",
        parse_mode="HTML",
    )
    return PRICE_ALERT_TOKEN


async def alert_token_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle token input."""
    token = update.message.text.strip()
    context.user_data["alert_token"] = token
    context.user_data["alert_symbol"] = token[:10] if len(token) < 20 else ""

    await update.effective_chat.send_message(
        f"✅ Token: <code>{token[:16]}...</code>\n\n"
        "💲 Enter the <b>target price</b> in USD:",
        parse_mode="HTML",
    )
    return PRICE_ALERT_PRICE


async def alert_price_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle target price input."""
    try:
        price = float(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter a valid price:")
        return PRICE_ALERT_PRICE

    context.user_data["alert_price"] = price

    buttons = [
        [InlineKeyboardButton("📈 Above (price goes UP to target)", callback_data="alert_dir_above")],
        [InlineKeyboardButton("📉 Below (price DROPS to target)", callback_data="alert_dir_below")],
    ]

    await update.effective_chat.send_message(
        f"✅ Target: ${price:.10g}\n\n"
        "📊 Alert when price goes:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return PRICE_ALERT_DIRECTION


async def alert_direction_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle direction selection and create alert."""
    query = update.callback_query
    await query.answer()

    direction = "above" if "above" in query.data else "below"
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    token = context.user_data.get("alert_token", "")
    symbol = context.user_data.get("alert_symbol", "")
    price = context.user_data.get("alert_price", 0)

    alert_id = await db.add_price_alert(
        telegram_id=user_id, chain=chain, token_address=token,
        token_symbol=symbol, target_price=price, direction=direction,
    )

    dir_emoji = "📈" if direction == "above" else "📉"

    await query.edit_message_text(
        "✅ <b>PRICE ALERT SET</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: <code>{token[:16]}...</code>\n"
        f"{dir_emoji} Direction: {direction.upper()}\n"
        f"💲 Target: ${price:.10g}\n"
        f"🆔 Alert ID: #{alert_id}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>You'll be notified when the target is hit.</i>",
        reply_markup=back_button("menu_alerts_price"),
        parse_mode="HTML",
    )
    return PRICE_ALERT_MENU


async def alert_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove an active price alert."""
    query = update.callback_query
    await query.answer()

    alert_id = int(query.data.replace("alert_rm_", ""))
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    await db.remove_price_alert(alert_id, user_id)

    await query.answer("✅ Alert removed", show_alert=True)
    return await price_alert_menu(update, context)
