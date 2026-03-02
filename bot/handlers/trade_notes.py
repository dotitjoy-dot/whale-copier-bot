"""
Trade notes handler — annotate trades with notes and searchable tags.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import (
    TRADE_NOTE_SELECT, TRADE_NOTE_INPUT, TRADE_TAG_SEARCH,
    HISTORY_MENU,
)
from core.logger import get_logger

logger = get_logger(__name__)


async def trade_note_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show recent trades to select one for adding a note."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    trades = await db.list_trades(user_id, chain=chain, limit=10)

    if not trades:
        msg = "No trades found to annotate."
        if query:
            await query.edit_message_text(msg, reply_markup=back_button("menu_history"))
        else:
            await update.effective_chat.send_message(msg, reply_markup=back_button("menu_history"))
        return HISTORY_MENU

    text = (
        "📝 <b>TRADE NOTES & TAGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select a trade to add notes:\n\n"
    )

    buttons = []
    for t in trades:
        symbol = t.get("token_symbol") or t["token_address"][:8]
        pnl = t.get("pnl_usd", 0)
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        action = t.get("action", "?")
        buttons.append([
            InlineKeyboardButton(
                f"{pnl_emoji} {action} {symbol} (${pnl:+.2f})",
                callback_data=f"note_trade_{t['id']}"
            )
        ])

    buttons.append([InlineKeyboardButton("🔍 Search by Tag", callback_data="note_search")])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_history")])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return TRADE_NOTE_SELECT


async def trade_note_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for note content for a specific trade."""
    query = update.callback_query
    await query.answer()

    trade_id = int(query.data.replace("note_trade_", ""))
    context.user_data["note_trade_id"] = trade_id

    db = context.bot_data.get("db")
    trade = await db.get_trade(trade_id)
    existing_notes = await db.get_trade_notes(trade_id)

    symbol = trade.get("token_symbol", "") if trade else "?"
    text = f"📝 <b>Add Note for Trade #{trade_id}</b>\n"
    text += f"🪙 Token: {symbol}\n\n"

    if existing_notes:
        text += "<b>Existing notes:</b>\n"
        for n in existing_notes:
            text += f"• {n['note']}"
            if n.get("tags"):
                text += f" [tags: {n['tags']}]"
            text += "\n"
        text += "\n"

    text += (
        "Type your note. Add tags with #hashtags.\n"
        "Example: <i>Whale bought at dip #dip #longterm</i>"
    )

    await query.edit_message_text(text, parse_mode="HTML")
    return TRADE_NOTE_INPUT


async def trade_note_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the note and extract tags."""
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    trade_id = context.user_data.get("note_trade_id", 0)

    raw_text = update.message.text.strip()

    # Extract tags (words starting with #)
    words = raw_text.split()
    tags = [w[1:] for w in words if w.startswith("#") and len(w) > 1]
    note_text = " ".join(w for w in words if not w.startswith("#"))
    tags_str = ",".join(tags)

    await db.add_trade_note(trade_id, user_id, note_text, tags_str)

    tag_display = f"\n🏷️ Tags: {', '.join('#' + t for t in tags)}" if tags else ""

    await update.effective_chat.send_message(
        f"✅ Note saved for trade #{trade_id}!\n"
        f"📝 {note_text}{tag_display}",
        reply_markup=back_button("menu_notes"),
        parse_mode="HTML",
    )
    return TRADE_NOTE_SELECT


async def trade_tag_search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for tag search."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 Enter a tag to search (without #):\n"
        "Example: <i>dip</i> or <i>longterm</i>",
        parse_mode="HTML",
    )
    return TRADE_TAG_SEARCH


async def trade_tag_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Search trades by tag and display results."""
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    tag = update.message.text.strip().replace("#", "")

    results = await db.search_trades_by_tag(user_id, tag)

    if not results:
        await update.effective_chat.send_message(
            f"🔍 No trades found with tag '#{tag}'.",
            reply_markup=back_button("menu_notes"),
        )
        return TRADE_NOTE_SELECT

    text = f"🔍 <b>Results for #{tag}</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for r in results[:10]:
        symbol = r.get("token_symbol", "?")
        pnl = r.get("pnl_usd", 0)
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        note = r.get("note", "")[:50]
        text += f"{pnl_emoji} {symbol} ${pnl:+.2f} — {note}\n"

    await update.effective_chat.send_message(
        text, reply_markup=back_button("menu_notes"), parse_mode="HTML",
    )
    return TRADE_NOTE_SELECT
