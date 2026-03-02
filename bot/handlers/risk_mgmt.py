"""
Risk management handler — configure SL, TP, TS, daily limits, slippage,
custom gas/priority fees, break-even SL, partial take profits,
auto-sell timeout, and smart slippage.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import (
    back_button, risk_mgmt_keyboard,
    partial_tp_keyboard,
)
from bot.menus import (
    RISK_MENU, RISK_STOP_LOSS, RISK_TAKE_PROFIT,
    RISK_TRAILING_STOP, RISK_DAILY_LIMIT, RISK_MAX_SLIPPAGE,
    RISK_CUSTOM_GAS, RISK_PRIORITY_TIP, RISK_AUTO_SELL,
    PARTIAL_TP_MENU, PARTIAL_TP_INPUT, BREAKEVEN_TRIGGER,
)
from core.logger import get_logger

logger = get_logger(__name__)


async def risk_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display risk management settings."""
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
        "🛡️ <b>RISK MANAGEMENT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Configure your safety nets, gas, and advanced features:"
    )
    keyboard = risk_mgmt_keyboard(config)
    
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    return RISK_MENU


async def risk_toggle_mev(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle MEV / Sandwich Protection mode on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("mev_protect_enabled", 1) else 1
    await db.upsert_copy_config(user_id, chain, {"mev_protect_enabled": new_val})
    
    status_text = "ENABLED ✅\nUsing secure Flash/Jito RPCs." if new_val else "DISABLED ❌\nStandard public RPCs active."
    await query.answer(f"MEV Protection {status_text}", show_alert=True)
    return await risk_menu(update, context)


async def risk_toggle_smart_slippage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle Smart Slippage (volatility-based) on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("smart_slippage_enabled", 1) else 1
    await db.upsert_copy_config(user_id, chain, {"smart_slippage_enabled": new_val})
    
    status = "🧠 ENABLED — Slippage auto-adjusts to market volatility." if new_val else "📐 DISABLED — Using fixed slippage cap."
    await query.answer(f"Smart Slippage {status}", show_alert=True)
    return await risk_menu(update, context)


async def risk_toggle_breakeven(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle Break-Even Stop Loss on/off or configure trigger percentage."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("breakeven_enabled", 0) else 1
    await db.upsert_copy_config(user_id, chain, {"breakeven_enabled": new_val})
    
    if new_val:
        trigger = float(config.get("breakeven_trigger_pct", 50.0))
        await query.answer(
            f"🛡️ Break-Even SL ENABLED!\nSL moves to entry when profit hits +{trigger:.0f}%.",
            show_alert=True,
        )
    else:
        await query.answer("Break-Even SL DISABLED", show_alert=True)
    return await risk_menu(update, context)


async def _set_numeric_config(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, min_val: float, max_val: float, err_msg: str, success_msg: str, return_state: int) -> int:
    """Helper for setting numeric risk configurations."""
    try:
        val = float(update.message.text.strip())
        if val < min_val or val > max_val:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_chat.send_message(err_msg)
        return return_state

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    
    await db.upsert_copy_config(user_id, chain, {key: val})
    await update.message.reply_text(success_msg.format(val=val))
    return await risk_menu(update, context)


# ── Standard Risk Prompts ────────────────────────────────────────────────────

async def risk_sl_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔻 Enter Stop Loss percentage (e.g., 20 for -20%):")
    return RISK_STOP_LOSS

async def risk_sl_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "stop_loss_pct", 0, 100, "⚠️ Enter a number between 0 and 100:", "✅ Stop Loss set to: {val:.1f}%", RISK_STOP_LOSS)

async def risk_tp_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🎯 Enter Take Profit percentage (e.g., 50 for +50%):")
    return RISK_TAKE_PROFIT

async def risk_tp_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "take_profit_pct", 0, 10000, "⚠️ Enter a number > 0:", "✅ Take Profit set to: {val:.1f}%", RISK_TAKE_PROFIT)

async def risk_ts_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🎢 Enter Trailing Stop percentage (0 to disable, e.g., 10 for 10% trailing):")
    return RISK_TRAILING_STOP

async def risk_ts_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "trailing_stop_pct", 0, 100, "⚠️ Enter a number between 0 and 100:", "✅ Trailing Stop set to: {val:.1f}%", RISK_TRAILING_STOP)

async def risk_daily_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🛑 Enter max Daily Loss Limit in USD (e.g., 50.0):")
    return RISK_DAILY_LIMIT

async def risk_daily_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "daily_loss_limit_usd", 0, 100000, "⚠️ Enter a number > 0:", "✅ Daily Loss Limit set to: ${val:.2f}", RISK_DAILY_LIMIT)

async def risk_slippage_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🏃‍♂️ Enter Maximum Slippage percentage (e.g., 5.0):")
    return RISK_MAX_SLIPPAGE

async def risk_slippage_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(update, context, "max_slippage_pct", 0.1, 50, "⚠️ Enter a number between 0.1 and 50:", "✅ Max Slippage set to: {val:.1f}%", RISK_MAX_SLIPPAGE)


# ── Custom Gas & Priority Fee ────────────────────────────────────────────────

async def risk_custom_gas_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user for custom base gas in gwei."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⛽ <b>Custom Base Gas (Gwei)</b>\n\n"
        "Enter a value in gwei for your base gas fee.\n"
        "Higher = faster transaction inclusion.\n\n"
        "• <b>0</b> = Auto (dynamic estimation)\n"
        "• Typical ETH: 20-100 gwei\n"
        "• Typical BSC: 3-10 gwei\n\n"
        "Enter value (0 for auto):",
        parse_mode="HTML",
    )
    return RISK_CUSTOM_GAS

async def risk_custom_gas_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(
        update, context, "custom_gas_gwei", 0, 5000,
        "⚠️ Enter a number between 0 and 5000:",
        "✅ Custom Gas set to: {val:.1f} gwei (0 = auto)",
        RISK_CUSTOM_GAS,
    )

async def risk_priority_tip_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user for priority tip (miner tip) in gwei."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🚀 <b>Priority Tip (Gwei)</b>\n\n"
        "Enter a value in gwei for your priority fee (miner tip).\n"
        "Higher tip = your tx gets prioritized over others.\n\n"
        "• <b>0</b> = Auto (dynamic estimation)\n"
        "• Competitive: 2-5 gwei\n"
        "• Aggressive: 10-50 gwei\n\n"
        "Enter value (0 for auto):",
        parse_mode="HTML",
    )
    return RISK_PRIORITY_TIP

async def risk_priority_tip_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(
        update, context, "priority_tip_gwei", 0, 1000,
        "⚠️ Enter a number between 0 and 1000:",
        "✅ Priority Tip set to: {val:.1f} gwei (0 = auto)",
        RISK_PRIORITY_TIP,
    )


# ── Time-Based Auto-Sell ─────────────────────────────────────────────────────

async def risk_auto_sell_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user for auto-sell timeout in hours."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⏰ <b>Time-Based Auto-Sell</b>\n\n"
        "Automatically sell tokens if they don't hit your profit targets\n"
        "within the specified number of hours.\n\n"
        "This improves capital efficiency by freeing up funds.\n\n"
        "• <b>0</b> = Disabled\n"
        "• Recommended: 12-48 hours\n\n"
        "Enter hours (0 to disable):",
        parse_mode="HTML",
    )
    return RISK_AUTO_SELL

async def risk_auto_sell_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(
        update, context, "auto_sell_hours", 0, 720,
        "⚠️ Enter a number between 0 and 720:",
        "✅ Auto-Sell set to: {val:.0f} hours (0 = disabled)",
        RISK_AUTO_SELL,
    )


# ── Break-Even Trigger Percentage ────────────────────────────────────────────

async def risk_breakeven_trigger_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user for break-even trigger percentage."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🛡️ <b>Break-Even Trigger %</b>\n\n"
        "When a trade reaches this profit percentage, the stop-loss\n"
        "automatically moves to your entry price (break-even).\n\n"
        "• Default: 50% (SL moves to entry at +50% profit)\n"
        "• Aggressive: 25% (safer, locks in earlier)\n"
        "• Conservative: 100% (only after 2x)\n\n"
        "Enter percentage:",
        parse_mode="HTML",
    )
    return BREAKEVEN_TRIGGER

async def risk_breakeven_trigger_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _set_numeric_config(
        update, context, "breakeven_trigger_pct", 5, 500,
        "⚠️ Enter a number between 5 and 500:",
        "✅ Break-Even trigger set to: +{val:.0f}%",
        BREAKEVEN_TRIGGER,
    )


# ── Partial Take Profits ────────────────────────────────────────────────────

async def partial_tp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display partial take profit configuration."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    steps = await db.get_partial_take_profits(user_id, chain)
    enabled = bool(config.get("partial_tp_enabled", 0))

    text = (
        "🟡 <b>MULTI-STEP TAKE PROFITS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Sell portions at different profit levels.\n\n"
        "Example: Sell 50% at 2x, 25% at 3x, let 25% moon 🚀\n\n"
    )

    if steps:
        for step in steps:
            text += f"📊 Step {step['step_order']}: Sell {float(step['sell_pct']):.0f}% at {float(step['target_multiple']):.1f}x\n"
    else:
        text += "No steps configured. Use presets or set custom.\n"

    keyboard = partial_tp_keyboard(steps, enabled)
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    return PARTIAL_TP_MENU


async def partial_tp_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle partial take profits on/off."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    config = await db.get_copy_config(user_id, chain) or {}
    new_val = 0 if config.get("partial_tp_enabled", 0) else 1
    await db.upsert_copy_config(user_id, chain, {"partial_tp_enabled": new_val})
    return await partial_tp_menu(update, context)


async def partial_tp_default(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set default partial TP steps: 50% at 2x, 25% at 3x, 25% at 5x."""
    query = update.callback_query
    await query.answer("Setting default partial TPs...")

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")

    default_steps = [
        {"step_order": 1, "sell_pct": 50, "target_multiple": 2.0},
        {"step_order": 2, "sell_pct": 25, "target_multiple": 3.0},
        {"step_order": 3, "sell_pct": 25, "target_multiple": 5.0},
    ]
    await db.set_partial_take_profits(user_id, chain, default_steps)
    await db.upsert_copy_config(user_id, chain, {"partial_tp_enabled": 1})
    return await partial_tp_menu(update, context)


async def partial_tp_custom_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user for custom partial TP steps."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ <b>Custom Partial Take Profits</b>\n\n"
        "Enter your steps in this format (one per line):\n"
        "<code>sell_pct,target_multiple</code>\n\n"
        "Example (sell 50% at 2x, 30% at 3x, 20% at 10x):\n"
        "<code>50,2\n30,3\n20,10</code>\n\n"
        "Note: percentages should add up to 100% or less.",
        parse_mode="HTML",
    )
    return PARTIAL_TP_INPUT


async def partial_tp_custom_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set custom partial TP steps from user input."""
    text = update.message.text.strip()
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    steps = []
    total_pct = 0
    try:
        for i, line in enumerate(lines, 1):
            parts = line.split(",")
            if len(parts) != 2:
                raise ValueError(f"Invalid format on line {i}")
            sell_pct = float(parts[0].strip())
            target_mult = float(parts[1].strip())
            if sell_pct <= 0 or target_mult <= 1.0:
                raise ValueError(f"Invalid values on line {i}")
            total_pct += sell_pct
            steps.append({
                "step_order": i,
                "sell_pct": sell_pct,
                "target_multiple": target_mult,
            })
        if total_pct > 100:
            raise ValueError(f"Total sell % exceeds 100 ({total_pct:.0f}%)")
    except (ValueError, TypeError) as e:
        await update.effective_chat.send_message(
            f"⚠️ Invalid input: {e}\n\nExpected format:\n<code>50,2\n30,3\n20,10</code>",
            parse_mode="HTML",
        )
        return PARTIAL_TP_INPUT

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    await db.set_partial_take_profits(user_id, chain, steps)
    await db.upsert_copy_config(user_id, chain, {"partial_tp_enabled": 1})
    await update.message.reply_text(f"✅ Set {len(steps)} custom partial TP steps (total: {total_pct:.0f}%)")
    return await partial_tp_menu(update, context)
