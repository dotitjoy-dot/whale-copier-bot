"""
Money management handler — configure trade sizing (fixed, percent, mirror).
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import money_mgmt_keyboard, back_button
from bot.menus import (
    MONEY_MENU, MONEY_MODE_SELECT, MONEY_FIXED_AMOUNT,
    MONEY_PERCENT, MONEY_MULTIPLIER, MONEY_MAX_POSITION
)
from core.logger import get_logger

logger = get_logger(__name__)


async def money_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display money management settings with current values."""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}

    text = (
        "💸 <b>MONEY MANAGEMENT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Configure how much to trade per copy:"
    )
    keyboard = money_mgmt_keyboard(config)
    
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    return MONEY_MENU


async def money_toggle_paper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle Paper Trading mode on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("paper_trading_enabled", 0) else 1
    await db.upsert_copy_config(user_id, chain, {"paper_trading_enabled": new_val})
    
    status_text = "ENABLED ✅\nReal funds will not be used." if new_val else "DISABLED ❌\nReal funds will be used for execution."
    await query.answer(f"Paper Trading {status_text}", show_alert=True)
    return await money_menu(update, context)


async def money_mode_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show trade size mode options."""
    query = update.callback_query
    await query.answer()

    buttons = [
        [InlineKeyboardButton("💵 Fixed USD Amount", callback_data="money_set_mode_fixed")],
        [InlineKeyboardButton("📈 % of Balance", callback_data="money_set_mode_percent")],
        [InlineKeyboardButton("🪞 Mirror (whale proportional)", callback_data="money_set_mode_mirror")],
        [InlineKeyboardButton("◀️ Back", callback_data="settings_money")],
    ]
    await query.edit_message_text(
        "📊 Select trade size mode:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return MONEY_MODE_SELECT


async def money_mode_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set the selected trade size mode."""
    query = update.callback_query

    mode = query.data.replace("money_set_mode_", "")
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")

    await db.upsert_copy_config(user_id, chain, {"trade_size_mode": mode})
    try:
        await query.answer(f"✅ Mode set to {mode.upper()}", show_alert=True)
    except Exception:
        pass
    
    return await money_menu(update, context)


async def money_fixed_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for fixed USD amount."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💵 Enter fixed amount in USD (e.g., 25.00):")
    return MONEY_FIXED_AMOUNT


async def money_fixed_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set fixed amount from user input."""
    try:
        amount = float(update.message.text.strip())
        if amount <= 0 or amount > 100000:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Invalid amount. Enter a number between 0.01 and 100000:")
        return MONEY_FIXED_AMOUNT

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"fixed_amount_usd": amount})
    await update.message.reply_text(f"✅ Fixed amount set to: ${amount:.2f}")
    return await money_menu(update, context)


async def money_percent_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for percent of balance."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📈 Enter percent of balance (e.g., 5.0):")
    return MONEY_PERCENT


async def money_percent_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set percent of balance."""
    try:
        pct = float(update.message.text.strip())
        if pct <= 0 or pct > 100:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Invalid percentage. Enter a number between 0.1 and 100:")
        return MONEY_PERCENT

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"percent_of_balance": pct})
    await update.message.reply_text(f"✅ Percent of balance set to: {pct:.1f}%")
    return await money_menu(update, context)


async def money_multiplier_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for mirror multiplier."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🪞 Enter mirror multiplier (e.g., 1.0 for 1x, 0.5 for half):")
    return MONEY_MULTIPLIER


async def money_multiplier_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set mirror multiplier."""
    try:
        val = float(update.message.text.strip())
        if val <= 0 or val > 100:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Invalid multiplier. Enter a number > 0:")
        return MONEY_MULTIPLIER

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"mirror_multiplier": val})
    await update.message.reply_text(f"✅ Mirror multiplier set to: {val}x")
    return await money_menu(update, context)


async def money_max_pos_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for max position size."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔒 Enter max position size in USD (e.g., 500):")
    return MONEY_MAX_POSITION


async def money_max_pos_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set max position size."""
    try:
        val = float(update.message.text.strip())
        if val <= 0 or val > 1000000:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Invalid amount. Try again:")
        return MONEY_MAX_POSITION

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"max_position_usd": val})
    await update.message.reply_text(f"✅ Max position set to: ${val:.2f}")
    return await money_menu(update, context)
