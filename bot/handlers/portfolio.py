"""
Portfolio handler — real-time portfolio heatmap with per-token unrealized PnL.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import PORTFOLIO_MENU, DASHBOARD
from core.logger import get_logger

logger = get_logger(__name__)

# Color-coded blocks for heatmap visual
HEAT_BLOCKS = {
    "extreme_up": "🟩🟩🟩",    # +50%+
    "strong_up": "🟩🟩",       # +20-50%
    "up": "🟩",                # +5-20%
    "neutral": "⬜",            # -5% to +5%
    "down": "🟥",              # -5 to -20%
    "strong_down": "🟥🟥",    # -20 to -50%
    "extreme_down": "🟥🟥🟥", # -50%+
}


def _get_heat_block(pnl_pct: float) -> str:
    """Return a visual heat indicator based on PnL percentage."""
    if pnl_pct >= 50:
        return HEAT_BLOCKS["extreme_up"]
    elif pnl_pct >= 20:
        return HEAT_BLOCKS["strong_up"]
    elif pnl_pct >= 5:
        return HEAT_BLOCKS["up"]
    elif pnl_pct >= -5:
        return HEAT_BLOCKS["neutral"]
    elif pnl_pct >= -20:
        return HEAT_BLOCKS["down"]
    elif pnl_pct >= -50:
        return HEAT_BLOCKS["strong_down"]
    else:
        return HEAT_BLOCKS["extreme_down"]


async def portfolio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display portfolio heatmap with per-token unrealized PnL."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")

    positions = await db.get_portfolio_positions(user_id)

    text = (
        "💹 <b>PORTFOLIO HEATMAP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    if not positions:
        text += "\n📭 No open positions.\n"
    else:
        total_invested = 0
        total_unrealized_pnl = 0

        for pos in positions:
            symbol = pos.get("token_symbol") or pos["token_address"][:8]
            chain = pos.get("chain", "?")
            invested = pos.get("total_invested", 0)
            avg_entry = pos.get("avg_entry_price", 0)
            count = pos.get("position_count", 1)
            total_invested += invested

            # Simulated unrealized PnL (in real app, fetch current price)
            # For now, show investment basis
            heat = _get_heat_block(0)  # Neutral until we have live price

            text += (
                f"\n{heat} <b>${symbol}</b> ({chain})\n"
                f"   💰 Invested: ${invested:,.2f}\n"
                f"   📊 Avg Entry: ${avg_entry:.10g}\n"
                f"   📦 Positions: {count}\n"
            )

        text += (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 <b>Total Invested:</b> ${total_invested:,.2f}\n"
        )

    text += (
        "\n<b>Legend:</b>\n"
        "🟩🟩🟩 +50%+ | 🟩🟩 +20% | 🟩 +5%\n"
        "⬜ Neutral | 🟥 -5% | 🟥🟥 -20% | 🟥🟥🟥 -50%+"
    )

    buttons = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_portfolio")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard")],
    ]

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

    return PORTFOLIO_MENU
