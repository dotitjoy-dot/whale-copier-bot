"""
Whale wallet handler — add, remove, list, and inspect whale wallets.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import whale_list_keyboard, back_button, chain_selector_keyboard
from bot.middlewares import auth_check
from bot.menus import WHALE_MENU, WHALE_ADD_CHAIN, WHALE_ADD_ADDRESS, WHALE_ADD_LABEL
from config.constants import CHAIN_INFO, SUPPORTED_CHAINS
from core.logger import get_logger

logger = get_logger(__name__)


async def whale_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the whale wallet management menu."""
    if not await auth_check(update, context):
        return -1

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    whales = await db.list_whales(user_id)
    page = context.user_data.get("whale_page", 0)

    text = (
        "🐋 <b>WHALE WALLETS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Tracking: {len(whales)} whale(s)\n\n"
        "Select an action or tap a whale to inspect:"
    )
    keyboard = whale_list_keyboard(whales, page)

    query = update.callback_query
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")

    return WHALE_MENU


async def whale_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the add whale flow — prompt for chain."""
    query = update.callback_query
    await query.answer()

    text = "➕ <b>Add Whale Wallet</b>\n\nSelect chain:"
    keyboard = chain_selector_keyboard("")
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    return WHALE_ADD_CHAIN


async def whale_add_chain_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle chain selection for whale, prompt for address."""
    query = update.callback_query
    await query.answer()

    chain = query.data.replace("chain_select_", "")
    context.user_data["whale_add_chain"] = chain

    chain_name = CHAIN_INFO.get(chain, {}).get("name", chain)
    if chain in ("ETH", "BSC"):
        hint = "0x-prefixed Ethereum/BSC address"
    else:
        hint = "Solana base58 public key"

    await query.edit_message_text(
        f"🐋 Adding whale on {chain_name}.\n\nPaste the whale's {hint}:",
        parse_mode="HTML",
    )
    return WHALE_ADD_ADDRESS


async def whale_add_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle whale address input, validate, prompt for label."""
    address = update.message.text.strip()
    chain = context.user_data.get("whale_add_chain", "ETH")

    # Basic validation
    if chain in ("ETH", "BSC"):
        if not address.startswith("0x") or len(address) != 42:
            await update.effective_chat.send_message(
                "⚠️ Invalid EVM address. Must be 42 chars starting with 0x. Try again:"
            )
            return WHALE_ADD_ADDRESS
    else:
        if len(address) < 32 or len(address) > 44:
            await update.effective_chat.send_message(
                "⚠️ Invalid Solana address. Must be 32-44 chars base58. Try again:"
            )
            return WHALE_ADD_ADDRESS

    context.user_data["whale_add_address"] = address

    await update.effective_chat.send_message(
        "Enter a label for this whale (e.g., 'Smart Money #1'):"
    )
    return WHALE_ADD_LABEL


async def whale_add_label(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle whale label input and save to DB."""
    label = update.message.text.strip()[:30]
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("whale_add_chain", "ETH")
    address = context.user_data.get("whale_add_address", "")

    try:
        whale_id = await db.add_whale(user_id, chain, address, label)
        chain_name = CHAIN_INFO.get(chain, {}).get("name", chain)
        await update.effective_chat.send_message(
            f"✅ Whale added!\n\n"
            f"⛓️ Chain: {chain_name}\n"
            f"🏷️ Label: {label}\n"
            f"📍 Address: <code>{address}</code>",
            parse_mode="HTML",
        )
    except Exception as exc:
        await update.effective_chat.send_message(f"❌ Failed to add whale: {exc}")

    return await whale_menu(update, context)


async def whale_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to select a whale to remove."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    whales = await db.list_whales(user_id)

    if not whales:
        await query.edit_message_text("No whales to remove.", reply_markup=back_button("menu_whales"))
        return WHALE_MENU

    buttons = []
    for w in whales:
        chain_emoji = CHAIN_INFO.get(w.get("chain", ""), {}).get("emoji", "")
        label = w.get("label", "Whale") or "Whale"
        addr = w.get("address", "")[:10] + "..."
        buttons.append([InlineKeyboardButton(
            f"❌ {chain_emoji} {label}: {addr}",
            callback_data=f"whale_rm_{w['id']}"
        )])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_whales")])

    await query.edit_message_text(
        "❌ Select whale to remove:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return WHALE_MENU


async def whale_remove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove the selected whale."""
    query = update.callback_query
    await query.answer()

    whale_id = int(query.data.replace("whale_rm_", ""))
    user_id = update.effective_user.id
    db = context.bot_data.get("db")

    await db.remove_whale(whale_id, user_id)
    await query.edit_message_text("✅ Whale removed.", reply_markup=back_button("menu_whales"))
    return WHALE_MENU


async def whale_inspect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show details and recent transactions for a specific whale."""
    query = update.callback_query
    await query.answer()

    whale_id = int(query.data.replace("whale_inspect_", ""))
    db = context.bot_data.get("db")
    whale = await db.get_whale(whale_id)

    if not whale:
        await query.edit_message_text("Whale not found.", reply_markup=back_button("menu_whales"))
        return WHALE_MENU

    chain_name = CHAIN_INFO.get(whale["chain"], {}).get("name", whale["chain"])
    chain_emoji = CHAIN_INFO.get(whale["chain"], {}).get("emoji", "")
    status = "🟢 Active" if whale.get("is_active") else "🔴 Inactive"
    explorer = CHAIN_INFO.get(whale["chain"], {}).get("explorer", "")
    addr_link = f'<a href="{explorer}/address/{whale["address"]}">{whale["address"][:10]}...{whale["address"][-6:]}</a>'

    text = (
        f"🔍 <b>WHALE INSPECTION</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{chain_emoji} Chain: {chain_name}\n"
        f"🏷️ Label: {whale.get('label', 'N/A')}\n"
        f"📍 Address: {addr_link}\n"
        f"📊 Status: {status}\n"
        f"📅 Added: {whale.get('added_at', 'N/A')}\n"
        f"🔗 Last TX: <code>{whale.get('last_tx_hash', 'None')[:16]}...</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    await query.edit_message_text(text, reply_markup=back_button("menu_whales"), parse_mode="HTML")
    return WHALE_MENU


async def whale_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle pagination for whale list."""
    query = update.callback_query
    await query.answer()

    page = int(query.data.replace("whale_page_", ""))
    context.user_data["whale_page"] = page
    return await whale_menu(update, context)
