"""
Auto-Sniper handler — configure and manage the auto-sniper mode.
Allows users to toggle sniping, set buy amounts, liquidity minimums,
and max pair age filters.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import sniper_settings_keyboard, back_button
from bot.menus import SNIPER_MENU, SNIPER_AMOUNT, SNIPER_MIN_LIQ, SNIPER_MAX_AGE
from core.logger import get_logger

logger = get_logger(__name__)


async def sniper_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the auto-sniper settings menu."""
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

    enabled = "🟢 ACTIVE" if config.get("sniper_enabled", 0) else "🔴 INACTIVE"
    text = (
        f"🎯 <b>AUTO-SNIPER MODE</b> — {enabled}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Automatically snipes trending new token pair\n"
        "creations from DEX Screener.\n\n"
        "⚡ <b>How it works:</b>\n"
        "• Monitors DEX Screener for trending tokens\n"
        "• Filters by liquidity and pair age\n"
        "• Auto-buys matching tokens with your configured amount\n\n"
        "⚠️ <b>Warning:</b> High risk! Only use with small amounts.\n"
        "New tokens can be volatile or rugs."
    )

    keyboard = sniper_settings_keyboard(config)
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    return SNIPER_MENU


async def sniper_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle auto-sniper mode on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("sniper_enabled", 0) else 1
    await db.upsert_copy_config(user_id, chain, {"sniper_enabled": new_val})

    if new_val:
        await query.answer("🎯 Auto-Sniper ENABLED! Hunting for new pairs...", show_alert=True)
    else:
        await query.answer("Auto-Sniper DISABLED", show_alert=True)
    return await sniper_menu(update, context)


async def sniper_amount_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for sniper buy amount in USD."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💰 <b>Sniper Buy Amount</b>\n\n"
        "Enter the amount in USD to spend per sniped token.\n"
        "💡 Recommended: $5-25 (small amounts for new tokens).\n\n"
        "Enter amount:",
        parse_mode="HTML",
    )
    return SNIPER_AMOUNT


async def sniper_amount_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set sniper buy amount."""
    try:
        val = float(update.message.text.strip())
        if val < 1 or val > 1000:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter a number between $1 and $1000:")
        return SNIPER_AMOUNT

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"sniper_amount_usd": val})
    await update.message.reply_text(f"✅ Sniper buy amount set to: ${val:.2f}")
    return await sniper_menu(update, context)


async def sniper_min_liq_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for minimum liquidity filter."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💧 <b>Minimum Liquidity</b>\n\n"
        "Only snipe tokens with at least this much pool liquidity.\n"
        "Higher = safer (avoids low-liquidity rugs).\n\n"
        "• Conservative: $50,000+\n"
        "• Moderate: $10,000+\n"
        "• Aggressive: $5,000+\n\n"
        "Enter minimum USD liquidity:",
        parse_mode="HTML",
    )
    return SNIPER_MIN_LIQ


async def sniper_min_liq_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set minimum liquidity filter."""
    try:
        val = float(update.message.text.strip())
        if val < 100 or val > 10000000:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter a number between $100 and $10,000,000:")
        return SNIPER_MIN_LIQ

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"sniper_min_liquidity_usd": val})
    await update.message.reply_text(f"✅ Minimum liquidity set to: ${val:,.0f}")
    return await sniper_menu(update, context)


async def sniper_max_age_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for maximum pair age filter."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⏱️ <b>Maximum Pair Age</b>\n\n"
        "Only snipe tokens created within the last X minutes.\n"
        "Lower = fresher tokens (riskier but more potential).\n\n"
        "• Very fresh: 5-10 minutes\n"
        "• Normal: 15-30 minutes\n"
        "• Liberal: 60+ minutes\n\n"
        "Enter max age in minutes:",
        parse_mode="HTML",
    )
    return SNIPER_MAX_AGE


async def sniper_max_age_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set max pair age filter."""
    try:
        val = int(float(update.message.text.strip()))
        if val < 1 or val > 1440:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter a number between 1 and 1440 minutes:")
        return SNIPER_MAX_AGE

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"sniper_max_age_minutes": val})
    await update.message.reply_text(f"✅ Max pair age set to: {val} minutes")
    return await sniper_menu(update, context)
