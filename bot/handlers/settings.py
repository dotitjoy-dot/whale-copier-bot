"""
Settings handler — money management, risk management, trade filters,
blacklist, and alert settings configuration.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import (
    settings_keyboard, money_mgmt_keyboard, risk_mgmt_keyboard, back_button,
)
from bot.middlewares import auth_check
from bot.menus import (
    SETTINGS_MENU, MONEY_MENU, MONEY_MODE_SELECT, MONEY_FIXED_AMOUNT,
    MONEY_PERCENT, MONEY_MULTIPLIER, MONEY_MAX_POSITION,
    RISK_MENU, RISK_STOP_LOSS, RISK_TAKE_PROFIT, RISK_TRAILING_STOP,
    RISK_DAILY_LIMIT, RISK_MAX_SLIPPAGE,
    BLACKLIST_MENU, BLACKLIST_ADD_ADDRESS, BLACKLIST_REMOVE_SELECT,
    FILTER_MIN_WHALE,
)
from core.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Settings Hub
# ─────────────────────────────────────────────────────────────────────────────

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the main settings menu."""
    if not await auth_check(update, context):
        return -1

    text = (
        "⚙️ <b>SETTINGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Configure copy trading parameters below:"
    )
    keyboard = settings_keyboard()

    query = update.callback_query
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")

    return SETTINGS_MENU


# ─────────────────────────────────────────────────────────────────────────────
# Money Management
# ─────────────────────────────────────────────────────────────────────────────

async def money_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display money management settings with current values."""
    query = update.callback_query
    await query.answer()

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
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    return MONEY_MENU


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
    await query.answer()

    mode = query.data.replace("money_set_mode_", "")
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")

    await db.upsert_copy_config(user_id, chain, {"trade_size_mode": mode})
    await query.edit_message_text(
        f"✅ Trade size mode set to: {mode.upper()}",
        reply_markup=back_button("settings_money"),
    )
    return MONEY_MENU


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
        if amount <= 0 or amount > 10000:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Invalid amount. Enter a number between 0.01 and 10000:")
        return MONEY_FIXED_AMOUNT

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"fixed_amount_usd": amount})
    await update.effective_chat.send_message(
        f"✅ Fixed amount set to: ${amount:.2f}",
        reply_markup=back_button("settings_money"),
    )
    return MONEY_MENU


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
    await update.effective_chat.send_message(
        f"✅ Percent of balance set to: {pct:.1f}%",
        reply_markup=back_button("settings_money"),
    )
    return MONEY_MENU


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
        if val <= 0 or val > 100000:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message("⚠️ Invalid amount. Try again:")
        return MONEY_MAX_POSITION

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {"max_position_usd": val})
    await update.effective_chat.send_message(
        f"✅ Max position set to: ${val:.2f}",
        reply_markup=back_button("settings_money"),
    )
    return MONEY_MENU


# ─────────────────────────────────────────────────────────────────────────────
# Risk Management
# ─────────────────────────────────────────────────────────────────────────────

async def risk_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display risk management settings."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}

    text = (
        "🛡️ <b>RISK MANAGEMENT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Configure stop-loss, take-profit, and limits:"
    )
    keyboard = risk_mgmt_keyboard(config)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    return RISK_MENU


async def _set_numeric_config(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    field: str, label: str, min_val: float, max_val: float, return_state: int
) -> int:
    """Generic numeric config setter."""
    try:
        val = float(update.message.text.strip())
        if val < min_val or val > max_val:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message(
            f"⚠️ Invalid value. Enter a number between {min_val} and {max_val}:"
        )
        return return_state

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.upsert_copy_config(user_id, chain, {field: val})

    unit = "%" if "pct" in field else "$"
    await update.effective_chat.send_message(
        f"✅ {label} set to: {unit}{val:.1f}" if unit == "$" else f"✅ {label} set to: {val:.1f}%",
        reply_markup=back_button("settings_risk"),
    )
    return RISK_MENU


async def risk_sl_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔻 Enter stop loss percentage (e.g., 20 for -20%):")
    return RISK_STOP_LOSS


async def risk_sl_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "stop_loss_pct", "Stop Loss", 1, 99, RISK_STOP_LOSS)


async def risk_tp_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔺 Enter take profit percentage (e.g., 50 for +50%):")
    return RISK_TAKE_PROFIT


async def risk_tp_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "take_profit_pct", "Take Profit", 1, 1000, RISK_TAKE_PROFIT)


async def risk_ts_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📉 Enter trailing stop percentage (0 to disable):")
    return RISK_TRAILING_STOP


async def risk_ts_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "trailing_stop_pct", "Trailing Stop", 0, 99, RISK_TRAILING_STOP)


async def risk_daily_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📅 Enter daily loss limit in USD (e.g., 50):")
    return RISK_DAILY_LIMIT


async def risk_daily_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "daily_loss_limit_usd", "Daily Loss Limit", 1, 100000, RISK_DAILY_LIMIT)


async def risk_slippage_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💧 Enter max slippage percentage (e.g., 5):")
    return RISK_MAX_SLIPPAGE


async def risk_slippage_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "max_slippage_pct", "Max Slippage", 0.1, 25, RISK_MAX_SLIPPAGE)


# ─────────────────────────────────────────────────────────────────────────────
# Blacklist
# ─────────────────────────────────────────────────────────────────────────────

async def blacklist_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show current blacklisted tokens."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    blacklist = await db.list_blacklist(user_id)

    text = "🚫 <b>TOKEN BLACKLIST</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    if blacklist:
        for b in blacklist:
            text += f"• <code>{b['token_address'][:12]}...</code>\n"
    else:
        text += "No tokens blacklisted.\n"

    buttons = [
        [InlineKeyboardButton("➕ Add Token", callback_data="blacklist_add")],
        [InlineKeyboardButton("❌ Remove Token", callback_data="blacklist_remove")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
    )
    return BLACKLIST_MENU


async def blacklist_add_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚫 Paste the token address to blacklist:")
    return BLACKLIST_ADD_ADDRESS


async def blacklist_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Add a token to blacklist."""
    addr = update.message.text.strip()
    user_id = update.effective_user.id
    db = context.bot_data.get("db")

    await db.add_blacklist(user_id, addr)
    await update.effective_chat.send_message(
        f"✅ Token <code>{addr[:12]}...</code> blacklisted.",
        reply_markup=back_button("settings_blacklist"),
        parse_mode="HTML",
    )
    return SETTINGS_MENU


# ─────────────────────────────────────────────────────────────────────────────
# Trade Filters
# ─────────────────────────────────────────────────────────────────────────────

async def filters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show trade filter settings."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}

    min_whale = config.get("min_whale_trade_usd", 500)
    copy_buys = "✅" if config.get("copy_buys", 1) else "❌"
    copy_sells = "✅" if config.get("copy_sells", 1) else "❌"
    anti_rug = "✅" if config.get("anti_rug_enabled", 1) else "❌"
    smart_money = "✅" if config.get("smart_money_enabled", 0) else "❌"

    text = (
        "🔍 <b>TRADE FILTERS & SECURITY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ Anti-Rug/Honeypot Checker: {anti_rug}\n"
        f"🧠 Copy Nansen Smart Money: {smart_money}\n"
        f"💰 Min whale trade: ${min_whale:.0f}\n"
        f"🟢 Copy buys: {copy_buys}\n"
        f"🔴 Copy sells: {copy_sells}\n"
    )

    buttons = [
        [InlineKeyboardButton(f"🛡️ Anti-Rug/Honeypot: {anti_rug}", callback_data="filter_toggle_anti_rug")],
        [InlineKeyboardButton(f"🧠 Smart Money: {smart_money}", callback_data="filter_toggle_smart_money")],
        [InlineKeyboardButton(f"💰 Min Whale Trade: ${min_whale:.0f}", callback_data="filter_min_whale")],
        [InlineKeyboardButton(f"🟢 Copy Buys: {copy_buys}", callback_data="filter_toggle_buys")],
        [InlineKeyboardButton(f"🔴 Copy Sells: {copy_sells}", callback_data="filter_toggle_sells")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_settings")],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
    )
    return SETTINGS_MENU


async def filter_toggle_anti_rug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle Anti-Rug / Honeypot checker on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("anti_rug_enabled", 1) else 1
    await db.upsert_copy_config(user_id, chain, {"anti_rug_enabled": new_val})
    return await filters_menu(update, context)


async def filter_toggle_buys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle copy buys on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("copy_buys", 1) else 1
    await db.upsert_copy_config(user_id, chain, {"copy_buys": new_val})
    return await filters_menu(update, context)


async def filter_toggle_sells(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle copy sells on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("copy_sells", 1) else 1
    await db.upsert_copy_config(user_id, chain, {"copy_sells": new_val})
    return await filters_menu(update, context)


async def filter_min_whale_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💰 Enter minimum whale trade USD value (e.g., 500):")
    return FILTER_MIN_WHALE


async def filter_min_whale_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(
        update, context, "min_whale_trade_usd", "Min Whale Trade", 1, 1000000, FILTER_MIN_WHALE
    )

async def filter_toggle_smart_money(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle Nansen Smart Money tracking."""
    query = update.callback_query
    
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    
    auth = context.bot_data.get("auth")
    if auth:
        sub = auth.get_subscription(user_id)
        if sub.tier == "FREE":
            await query.answer("⚠️ Smart Money feed requires PRO or ELITE tier.", show_alert=True)
            return SETTINGS_MENU

    await query.answer()

    current = config.get("smart_money_enabled", 0)
    new_val = 0 if current else 1

    await db.upsert_copy_config(user_id, chain, {"smart_money_enabled": new_val})
    return await filters_menu(update, context)
