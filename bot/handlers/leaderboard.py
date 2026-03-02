"""
Whale leaderboard handler — rank whales by profitability and trade frequency.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import WHALE_LEADERBOARD, DASHBOARD
from core.logger import get_logger

logger = get_logger(__name__)

MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


async def whale_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display whale profitability leaderboard."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")

    # Get user's tracked whales
    whales = await db.list_whales(user_id)
    whale_addresses = {w["address"]: w.get("label", "") for w in whales}

    # Get scores for all whales on this chain
    all_scores = await db.get_whale_scores(chain)

    # Filter to only tracked whales
    tracked_scores = [
        s for s in all_scores if s["whale_address"] in whale_addresses
    ]

    text = (
        "🏆 <b>WHALE LEADERBOARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⛓️ Chain: {chain}\n\n"
    )

    if not tracked_scores:
        text += (
            "📊 No profitability data yet.\n"
            "Scores are tracked automatically as\n"
            "copy-trades close with results.\n"
        )
    else:
        for idx, score in enumerate(tracked_scores[:10]):
            addr = score["whale_address"]
            label = whale_addresses.get(addr, addr[:8])
            if not label:
                label = f"{addr[:6]}...{addr[-4:]}"
            medal = MEDALS[idx] if idx < len(MEDALS) else f"#{idx + 1}"

            total = score["total_trades"]
            wins = score["winning_trades"]
            win_rate = (wins / total * 100) if total > 0 else 0
            pnl = score["total_pnl_usd"]
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"

            text += (
                f"{medal} <b>{label}</b>\n"
                f"   {pnl_emoji} PnL: ${pnl:+,.2f} | "
                f"WR: {win_rate:.0f}% ({wins}/{total})\n\n"
            )

    text += "━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "<i>Updated automatically on trade close</i>"

    buttons = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="menu_leaderboard")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_whales")],
    ]

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

    return WHALE_LEADERBOARD
