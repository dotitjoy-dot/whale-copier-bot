"""
Blacklist handler — manage list of tokens to avoid copying.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import BLACKLIST_MENU, BLACKLIST_ADD_ADDRESS
from core.logger import get_logger

logger = get_logger(__name__)


async def blacklist_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the currently blacklisted tokens and provide add/remove options."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")

    blacklist = await db.list_blacklist(user_id)
    text = "🚫 <b>BLACKLISTED TOKENS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    buttons = []
    
    if not blacklist:
        text += "Your blacklist is empty.\n"
    else:
        for idx, item in enumerate(blacklist):
            addr = item["address"]
            text += f"{idx + 1}. <code>{addr[:8]}...{addr[-6:]}</code>"
            if item["reason"]:
                text += f" - {item['reason']}"
            text += "\n"
            
            # Add a remove button for each item
            buttons.append([
                InlineKeyboardButton(f"❌ Remove {addr[:6]}...", callback_data=f"blacklist_rm_{item['id']}")
            ])

    buttons.append([InlineKeyboardButton("➕ Add Token", callback_data="blacklist_add")])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_settings")])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
    )
    return BLACKLIST_MENU


async def blacklist_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove a token from the blacklist."""
    query = update.callback_query
    await query.answer()
    
    item_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    
    # Needs a soft removal or specific address removal
    # To handle exactly from DB we need a custom method. Let's redirect to menu for now if method lacks.
    try:
        # Get address from ID first (assuming we have a method for it, or just use delete)
        await db._conn.execute("DELETE FROM blacklist WHERE id=? AND telegram_id=?", (item_id, user_id))
        await db._conn.commit()
    except Exception as e:
        logger.error(f"Error removing blacklist token: {e}")
        
    return await blacklist_menu(update, context)


async def blacklist_add_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for a token address to blacklist."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 Send the contract address of the token you want to blacklist. Let's stop copying trades for this coin."
    )
    return BLACKLIST_ADD_ADDRESS


async def blacklist_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process user input to add a token to the blacklist."""
    address = update.message.text.strip()
    if not address.startswith("0x") and len(address) < 30:
        await update.effective_chat.send_message("⚠️ Invalid address. Are you sure you copied it correctly?")
        return BLACKLIST_ADD_ADDRESS

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "") # Apply globablly or contextually

    await db.add_blacklist(user_id, address, chain, "Added manually")
    
    await update.effective_chat.send_message(
        f"✅ Token `{address}` added to blacklist.",
        reply_markup=back_button("settings_blacklist"),
        parse_mode="Markdown",
    )
    return BLACKLIST_MENU
