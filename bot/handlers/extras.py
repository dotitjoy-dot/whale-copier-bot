"""
Snooze handler — temporarily pause copy-trading for X hours, auto-resume.
Anti-FOMO cooldown — prevent rapid consecutive trades on same token.
Multi-Wallet rotation — rotate between wallets for privacy/risk.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import SNOOZE_SET, COOLDOWN_SET, WALLET_ROTATION_MENU, SETTINGS_MENU
from core.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Snooze Mode
# ─────────────────────────────────────────────────────────────────────────────

async def snooze_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show snooze mode options."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}

    snooze_until = config.get("snooze_until", "")
    is_snoozed = False
    remaining = ""

    if snooze_until:
        try:
            wake_time = datetime.fromisoformat(snooze_until)
            if wake_time > datetime.utcnow():
                is_snoozed = True
                diff = wake_time - datetime.utcnow()
                hours = diff.total_seconds() / 3600
                remaining = f" ({hours:.1f}h remaining)"
        except (ValueError, TypeError):
            pass

    status = f"😴 SNOOZED{remaining}" if is_snoozed else "👀 ACTIVE"

    text = (
        "⏸️ <b>SNOOZE MODE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Status: {status}\n\n"
        "Temporarily pause all copy-trading.\n"
        "Bot will auto-resume after the timer.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = []
    if is_snoozed:
        buttons.append([InlineKeyboardButton("▶️ Wake Up Now", callback_data="snooze_wake")])
    else:
        buttons.extend([
            [
                InlineKeyboardButton("1h", callback_data="snooze_1"),
                InlineKeyboardButton("4h", callback_data="snooze_4"),
                InlineKeyboardButton("8h", callback_data="snooze_8"),
            ],
            [
                InlineKeyboardButton("12h", callback_data="snooze_12"),
                InlineKeyboardButton("24h", callback_data="snooze_24"),
                InlineKeyboardButton("Custom", callback_data="snooze_custom"),
            ],
        ])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_settings")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return SNOOZE_SET


async def snooze_set_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set snooze from a preset duration."""
    query = update.callback_query
    await query.answer()

    hours_str = query.data.replace("snooze_", "")
    if hours_str == "custom":
        await query.edit_message_text("⏱️ Enter snooze duration in hours (1-168):")
        return SNOOZE_SET
    elif hours_str == "wake":
        # Wake up immediately
        user_id = update.effective_user.id
        db = context.bot_data.get("db")
        chain = context.user_data.get("chain", "ETH")
        await db.upsert_copy_config(user_id, chain, {"snooze_until": ""})
        await query.answer("▶️ Snooze cancelled! Bot is active.", show_alert=True)
        return await snooze_menu(update, context)

    try:
        hours = int(hours_str)
    except ValueError:
        return await snooze_menu(update, context)

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    wake_time = datetime.utcnow() + timedelta(hours=hours)
    await db.upsert_copy_config(user_id, chain, {"snooze_until": wake_time.isoformat()})

    await query.answer(f"😴 Snoozed for {hours} hours!", show_alert=True)
    return await snooze_menu(update, context)


async def snooze_custom_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom snooze duration input."""
    try:
        hours = float(update.message.text.strip())
        if hours < 0.5 or hours > 168:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter hours (0.5-168):")
        return SNOOZE_SET

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    wake_time = datetime.utcnow() + timedelta(hours=hours)
    await db.upsert_copy_config(user_id, chain, {"snooze_until": wake_time.isoformat()})

    await update.effective_chat.send_message(
        f"😴 Snoozed for {hours:.1f} hours!\n"
        f"Auto-resume: {wake_time.strftime('%H:%M UTC')}",
        reply_markup=back_button("menu_settings"),
    )
    return SETTINGS_MENU


# ─────────────────────────────────────────────────────────────────────────────
# Anti-FOMO Cooldown
# ─────────────────────────────────────────────────────────────────────────────

async def cooldown_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for anti-FOMO cooldown minutes."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    current = config.get("cooldown_minutes", 0)

    await query.edit_message_text(
        "🧊 <b>ANTI-FOMO COOLDOWN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Prevent rapid consecutive trades on the\n"
        "same token within X minutes.\n\n"
        f"Current: {current} min {'(disabled)' if current == 0 else ''}\n\n"
        "Enter cooldown in minutes (0 to disable):",
        parse_mode="HTML",
    )
    return COOLDOWN_SET


async def cooldown_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set anti-FOMO cooldown minutes."""
    try:
        minutes = int(update.message.text.strip())
        if minutes < 0 or minutes > 1440:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Enter minutes (0-1440):")
        return COOLDOWN_SET

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"cooldown_minutes": minutes})

    status = f"{minutes} minutes" if minutes > 0 else "disabled"
    await update.effective_chat.send_message(
        f"✅ Anti-FOMO cooldown set to: {status}\n"
        "Same tokens won't be bought again within this window.",
        reply_markup=back_button("settings_risk"),
    )
    return SETTINGS_MENU


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Wallet Rotation
# ─────────────────────────────────────────────────────────────────────────────

async def wallet_rotation_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show wallet rotation toggle."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    wallets = await db.list_wallets_by_chain(user_id, chain)

    enabled = config.get("wallet_rotation_enabled", 0)
    toggle_emoji = "✅" if enabled else "❌"

    text = (
        "🔄 <b>MULTI-WALLET ROTATION</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Status: {toggle_emoji} {'Enabled' if enabled else 'Disabled'}\n"
        f"Available wallets on {chain}: {len(wallets)}\n\n"
        "When enabled, the bot rotates between\n"
        "your available wallets for each trade\n"
        "to distribute risk and improve privacy.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    if len(wallets) < 2:
        text += "\n\n⚠️ You need at least 2 wallets for rotation."

    buttons = [
        [InlineKeyboardButton(
            f"{toggle_emoji} {'Disable' if enabled else 'Enable'} Rotation",
            callback_data="rotation_toggle"
        )],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return WALLET_ROTATION_MENU


async def wallet_rotation_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle wallet rotation on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}

    new_val = 0 if config.get("wallet_rotation_enabled", 0) else 1
    await db.upsert_copy_config(user_id, chain, {"wallet_rotation_enabled": new_val})

    status = "ENABLED ✅" if new_val else "DISABLED ❌"
    await query.answer(f"Wallet rotation {status}", show_alert=True)
    return await wallet_rotation_menu(update, context)
