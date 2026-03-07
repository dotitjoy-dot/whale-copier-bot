"""
Wallet handler — create, import, export, balance check, and remove wallet flows.
All wallet operations are multi-step via ConversationHandler.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import wallet_menu_keyboard, chain_selector_keyboard, back_button, confirm_action_keyboard
from bot.middlewares import auth_check
from bot.menus import (
    WALLET_MENU, WALLET_CREATE_CHAIN, WALLET_CREATE_LABEL,
    WALLET_CREATE_PASSPHRASE, WALLET_IMPORT_CHAIN, WALLET_IMPORT_KEY,
    WALLET_IMPORT_LABEL, WALLET_IMPORT_PASSPHRASE, WALLET_BALANCE_SELECT,
    WALLET_EXPORT_SELECT, WALLET_EXPORT_PASSPHRASE,
    WALLET_REMOVE_SELECT, WALLET_REMOVE_CONFIRM,
)
from config.constants import CHAIN_INFO
from core.logger import get_logger
from wallets import wallet_manager

logger = get_logger(__name__)


async def wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Display the wallet management menu with existing wallets.

    Args:
        update: Telegram callback query update.
        context: Bot context.

    Returns:
        WALLET_MENU state.
    """
    if not await auth_check(update, context):
        return -1

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    wallets = await wallet_manager.list_user_wallets(db, user_id)

    text = (
        "💰 <b>MY WALLETS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total wallets: {len(wallets)}\n\n"
        "Select an action below:"
    )

    keyboard = wallet_menu_keyboard(wallets)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")

    return WALLET_MENU


async def wallet_create_chain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to select chain for new wallet creation."""
    query = update.callback_query
    await query.answer()

    text = "➕ <b>Create New Wallet</b>\n\nSelect chain:"
    keyboard = chain_selector_keyboard("")
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    return WALLET_CREATE_CHAIN


async def wallet_create_chain_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle chain selection for wallet creation, prompt for label."""
    query = update.callback_query
    await query.answer()

    chain = query.data.replace("chain_select_", "")
    context.user_data["create_chain"] = chain

    chain_name = CHAIN_INFO.get(chain, {}).get("name", chain)
    await query.edit_message_text(
        f"Creating {chain_name} wallet.\n\nEnter a label for this wallet (e.g., 'Main', 'Trading'):",
        reply_markup=back_button("wallet_create"),
        parse_mode="HTML",
    )
    return WALLET_CREATE_LABEL


async def wallet_create_label(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle wallet label input, prompt for passphrase."""
    label = update.message.text.strip()[:30]
    context.user_data["create_label"] = label

    auth = context.bot_data.get("auth")
    user_id = update.effective_user.id
    passphrase = auth.get_session_passphrase(user_id) if auth else ""

    if passphrase:
        # Session active — use existing passphrase
        return await _execute_create_wallet(update, context, passphrase)

    await update.effective_chat.send_message(
        "🔐 Enter your wallet passphrase to encrypt the private key:\n"
        "(This message will be deleted for security)"
    )
    return WALLET_CREATE_PASSPHRASE


async def wallet_create_passphrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle passphrase for wallet creation and execute."""
    passphrase = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    return await _execute_create_wallet(update, context, passphrase)


async def _execute_create_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE, passphrase: str) -> int:
    """Actually create the wallet and show mnemonic."""
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("create_chain", "ETH")
    label = context.user_data.get("create_label", "Main")

    try:
        if chain in ("ETH", "BSC"):
            result = await wallet_manager.create_evm_wallet(db, user_id, chain, label, passphrase)
        else:
            result = await wallet_manager.create_solana_wallet(db, user_id, label, passphrase)

        mnemonic = result.get("mnemonic", "")
        address = result.get("address", "")

        text = (
            "✅ <b>Wallet Created Successfully!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⛓️ Chain: {CHAIN_INFO.get(chain, {}).get('name', chain)}\n"
            f"🏷️ Label: {label}\n"
            f"📍 Address: <code>{address}</code>\n\n"
            "📝 <b>RECOVERY PHRASE (SAVE THIS!):</b>\n"
            f"<code>{mnemonic}</code>\n\n"
            "⚠️ <b>WARNING:</b> This mnemonic is shown ONCE only!\n"
            "Write it down and store it safely. It will NOT be shown again."
        )

        await update.effective_chat.send_message(text, parse_mode="HTML")
        return await wallet_menu(update, context)

    except Exception as exc:
        await update.effective_chat.send_message(f"❌ Wallet creation failed: {exc}")
        return await wallet_menu(update, context)


async def wallet_import_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the wallet import flow — prompt for chain."""
    query = update.callback_query
    await query.answer()

    text = "📥 <b>Import Wallet</b>\n\nSelect chain:"
    keyboard = chain_selector_keyboard("")
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    return WALLET_IMPORT_CHAIN


async def wallet_import_chain_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle chain selection for import, prompt for private key."""
    query = update.callback_query
    await query.answer()

    chain = query.data.replace("chain_select_", "")
    context.user_data["import_chain"] = chain

    if chain in ("ETH", "BSC"):
        key_hint = "0x-prefixed or raw hex private key"
    else:
        key_hint = "base58-encoded private key"

    await query.edit_message_text(
        f"📥 Import {CHAIN_INFO.get(chain, {}).get('name', chain)} wallet.\n\n"
        f"Paste your {key_hint}:\n"
        "(Message will be deleted for security)",
        parse_mode="HTML",
    )
    return WALLET_IMPORT_KEY


async def wallet_import_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle private key input for import."""
    private_key = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    context.user_data["import_key"] = private_key
    await update.effective_chat.send_message("Enter a label for this wallet:")
    return WALLET_IMPORT_LABEL


async def wallet_import_label(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle label input for import, execute import."""
    label = update.message.text.strip()[:30]
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    auth = context.bot_data.get("auth")
    chain = context.user_data.get("import_chain", "ETH")
    private_key = context.user_data.get("import_key", "")

    passphrase = auth.get_session_passphrase(user_id) if auth else ""
    if not passphrase:
        await update.effective_chat.send_message("🔐 Enter your passphrase:")
        context.user_data["import_label"] = label
        return WALLET_IMPORT_PASSPHRASE

    return await _execute_import(update, context, label, passphrase)


async def wallet_import_passphrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle passphrase for import."""
    passphrase = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    label = context.user_data.get("import_label", "Imported")
    return await _execute_import(update, context, label, passphrase)


async def _execute_import(update, context, label, passphrase):
    """Execute wallet import."""
    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("import_chain", "ETH")
    private_key = context.user_data.pop("import_key", "")

    try:
        if chain in ("ETH", "BSC"):
            result = await wallet_manager.import_evm_wallet(db, user_id, chain, label, private_key, passphrase)
        else:
            result = await wallet_manager.import_solana_wallet(db, user_id, label, private_key, passphrase)

        address = result.get("address", "")
        await update.effective_chat.send_message(
            f"✅ Wallet imported!\n📍 Address: <code>{address}</code>",
            parse_mode="HTML",
        )
    except Exception as exc:
        await update.effective_chat.send_message(f"❌ Import failed: {exc}")

    return await wallet_menu(update, context)


async def wallet_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show balance for all user wallets."""
    if not await auth_check(update, context):
        return -1

    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    wallets = await wallet_manager.list_user_wallets(db, user_id)

    if not wallets:
        text = "No wallets found. Create one first!"
        if query:
            await query.edit_message_text(text, reply_markup=back_button("menu_wallets"))
        else:
            await update.effective_chat.send_message(text, reply_markup=back_button("menu_wallets"))
        return WALLET_MENU

    text = "💵 <b>WALLET BALANCES</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for w in wallets:
        chain_emoji = CHAIN_INFO.get(w["chain"], {}).get("emoji", "")
        text += f"{chain_emoji} <b>{w['label']}</b>: <code>{w['address_masked']}</code>\n"
        try:
            balance = await wallet_manager.get_wallet_balance(db, w["wallet_id"], "")
            native = balance.get("native_balance", 0)
            symbol = balance.get("native_symbol", "")
            usd = balance.get("usd_value", 0)
            text += f"   {native:.6f} {symbol} (≈${usd:.2f})\n\n"
        except Exception:
            text += "   ⚠️ Could not fetch balance\n\n"

    if query:
        await query.edit_message_text(text, reply_markup=back_button("menu_wallets"), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=back_button("menu_wallets"), parse_mode="HTML")

    return WALLET_MENU


async def wallet_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to select a wallet to remove."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    wallets = await wallet_manager.list_user_wallets(db, user_id)

    if not wallets:
        await query.edit_message_text("No wallets to remove.", reply_markup=back_button("menu_wallets"))
        return WALLET_MENU

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for w in wallets:
        chain_emoji = CHAIN_INFO.get(w["chain"], {}).get("emoji", "")
        buttons.append([InlineKeyboardButton(
            f"🗑️ {chain_emoji} {w['label']}: {w['address_masked']}",
            callback_data=f"wallet_rm_{w['wallet_id']}"
        )])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_wallets")])

    await query.edit_message_text(
        "🗑️ Select wallet to remove:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return WALLET_REMOVE_SELECT


async def wallet_remove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove the selected wallet after confirmation."""
    query = update.callback_query
    await query.answer()

    wallet_id = int(query.data.replace("wallet_rm_", ""))
    user_id = update.effective_user.id
    db = context.bot_data.get("db")

    await db.remove_wallet(wallet_id, user_id)
    await query.edit_message_text("✅ Wallet removed.", reply_markup=back_button("menu_wallets"))
    return WALLET_MENU


# ─────────────────────────────────────────────────────────────────────────────
# Wallet Export Flow
# ─────────────────────────────────────────────────────────────────────────────

async def wallet_export_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to select a wallet to export."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    wallets = await wallet_manager.list_user_wallets(db, user_id)

    if not wallets:
        await query.edit_message_text("No wallets to export.", reply_markup=back_button("menu_wallets"))
        return WALLET_MENU

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for w in wallets:
        chain_emoji = CHAIN_INFO.get(w["chain"], {}).get("emoji", "")
        buttons.append([InlineKeyboardButton(
            f"📤 {chain_emoji} {w['label']}: {w['address_masked']}",
            callback_data=f"wallet_exp_{w['wallet_id']}"
        )])
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_wallets")])

    await query.edit_message_text(
        "📤 <b>Export Wallet</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select wallet to export its private key:\n\n"
        "⚠️ <b>WARNING:</b> Never share your private key!",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )
    return WALLET_EXPORT_SELECT


async def wallet_export_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle wallet selection for export — check passphrase or execute directly."""
    query = update.callback_query
    await query.answer()

    wallet_id = int(query.data.replace("wallet_exp_", ""))
    context.user_data["export_wallet_id"] = wallet_id

    # Check if we have a session passphrase
    auth = context.bot_data.get("auth")
    user_id = update.effective_user.id
    passphrase = auth.get_session_passphrase(user_id) if auth else ""

    if passphrase:
        return await _do_export(update, context, passphrase)

    await query.edit_message_text(
        "🔐 Enter your wallet passphrase to decrypt the private key:\n"
        "(Message will be deleted for security)",
    )
    return WALLET_EXPORT_PASSPHRASE


async def wallet_export_passphrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle passphrase input for export."""
    passphrase = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    return await _do_export(update, context, passphrase)


async def _do_export(update: Update, context: ContextTypes.DEFAULT_TYPE, passphrase: str) -> int:
    """Decrypt and display recovery phrase + private key for export."""
    db = context.bot_data.get("db")
    wallet_id = context.user_data.get("export_wallet_id")

    if not wallet_id:
        await update.effective_chat.send_message("❌ No wallet selected.", reply_markup=back_button("menu_wallets"))
        return WALLET_MENU

    try:
        export = await wallet_manager.export_wallet_full(db, wallet_id, passphrase)

        chain = export["chain"]
        address = export["address"]
        label = export["label"]
        mnemonic = export.get("mnemonic", "")
        private_key = export["private_key"]
        derivation_path = export["derivation_path"]
        compatible = export["compatible_wallets"]

        chain_name = CHAIN_INFO.get(chain, {}).get("name", chain)

        text = (
            "📤 <b>WALLET EXPORT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⛓️ Chain: {chain_name}\n"
            f"🏷️ Label: {label}\n"
            f"📍 Address:\n<code>{address}</code>\n\n"
        )

        if mnemonic:
            text += (
                "📝 <b>RECOVERY PHRASE (12 words):</b>\n"
                f"<tg-spoiler>{mnemonic}</tg-spoiler>\n\n"
                f"🔀 Derivation Path: <code>{derivation_path}</code>\n\n"
            )
        else:
            text += (
                "📝 <i>Recovery phrase not available</i>\n"
                "<i>(Wallet was imported via private key only)</i>\n\n"
            )

        text += (
            f"🔑 <b>PRIVATE KEY:</b>\n"
            f"<tg-spoiler>{private_key}</tg-spoiler>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Compatible with:</b>\n"
            f"   {compatible}\n\n"
            "⚠️ <b>SECURITY WARNING:</b>\n"
            "• Never share these with anyone\n"
            "• This message auto-deletes in 60s\n"
            "• Store offline in a safe place\n"
            "• Recovery phrase works across\n"
            "  all BIP-39 compatible wallets"
        )

        msg = await update.effective_chat.send_message(text, parse_mode="HTML")

        # Auto-delete the sensitive message after 60 seconds
        import asyncio
        async def _auto_delete():
            await asyncio.sleep(60)
            try:
                await msg.delete()
            except Exception:
                pass

        asyncio.create_task(_auto_delete())

    except Exception as exc:
        await update.effective_chat.send_message(
            f"❌ Export failed: {exc}\n\n"
            "Check your passphrase and try again.",
            reply_markup=back_button("menu_wallets"),
        )

    context.user_data.pop("export_wallet_id", None)
    return await wallet_menu(update, context)
