"""
Alert settings handler — configure when the bot sends notifications.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.menus import ALERTS_MENU
from core.logger import get_logger

logger = get_logger(__name__)


async def alerts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show current alert configurations."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    alerts = await db.get_alert_settings(user_id)

    text = (
        "🔔 <b>ALERT SETTINGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Toggle which push notifications you want to receive:"
    )

    whale_emoji = "✅" if alerts.get("notify_whale_detect", 1) else "❌"
    trade_emoji = "✅" if alerts.get("notify_trade_executed", 1) else "❌"
    stop_emoji = "✅" if alerts.get("notify_sl_tp_hit", 1) else "❌"

    buttons = [
        [InlineKeyboardButton(f"{whale_emoji} Whale Detections", callback_data="alert_toggle_whale")],
        [InlineKeyboardButton(f"{trade_emoji} Trade Executions", callback_data="alert_toggle_trade")],
        [InlineKeyboardButton(f"{stop_emoji} SL/TP Hits", callback_data="alert_toggle_stop")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
    )
    return ALERTS_MENU


async def alert_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle toggling of alert configurations."""
    query = update.callback_query
    await query.answer()

    action = query.data.replace("alert_toggle_", "")
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    alerts = await db.get_alert_settings(user_id)

    field_map = {
        "whale": "notify_whale_detect",
        "trade": "notify_trade_executed",
        "stop": "notify_sl_tp_hit"
    }

    if action in field_map:
        field = field_map[action]
        current_val = alerts.get(field, 1)
        new_val = 0 if current_val else 1
        await db.update_alert_settings(user_id, **{field: new_val})

    return await alerts_menu(update, context)
