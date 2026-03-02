"""
Admin handler — admin-only commands for system management.
Broadcast, list users, force-stop all, system status.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.middlewares import auth_check
from bot.menus import ADMIN_MENU, ADMIN_BROADCAST
from core.logger import get_logger

logger = get_logger(__name__)


async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show admin control panel. Only accessible by ADMIN_TELEGRAM_ID."""
    if not await auth_check(update, context):
        return -1

    user_id = update.effective_user.id
    auth = context.bot_data.get("auth")
    if not (auth and auth.is_admin(user_id)):
        if update.callback_query:
            await update.callback_query.edit_message_text("⛔ Admin access only.")
        else:
            await update.effective_chat.send_message("⛔ Admin access only.")
        return -1

    db = context.bot_data.get("db")
    users = await db.list_all_users()
    total_users = len(users)

    text = (
        "🔑 <b>ADMIN PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users: {total_users}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 List Users", callback_data="admin_users")],
        [InlineKeyboardButton("⏹️ Force Stop All Copy", callback_data="admin_stop_all")],
        [InlineKeyboardButton("📊 System Status", callback_data="admin_status")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard")],
    ]

    query = update.callback_query
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

    return ADMIN_MENU


async def admin_broadcast_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt admin for broadcast message."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text("📢 Type the message to broadcast to all users:")
    return ADMIN_BROADCAST


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send broadcast message to all users."""
    msg_text = update.message.text.strip()
    db = context.bot_data.get("db")
    users = await db.list_all_users()

    sent = 0
    failed = 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=f"📢 <b>ADMIN BROADCAST:</b>\n\n{msg_text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1

    await update.effective_chat.send_message(
        f"📢 Broadcast complete!\n✅ Sent: {sent}\n❌ Failed: {failed}",
        reply_markup=back_button("admin"),
    )
    return ADMIN_MENU


async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """List all registered users."""
    query = update.callback_query
    await query.answer()

    db = context.bot_data.get("db")
    users = await db.list_all_users()

    text = "👥 <b>REGISTERED USERS</b>\n━━━━━━━━━━━━━━━━\n\n"
    for u in users[:20]:
        admin_badge = " 👑" if u.get("is_admin") else ""
        text += f"• {u.get('username', 'N/A')} ({u['telegram_id']}){admin_badge}\n"

    if len(users) > 20:
        text += f"\n... and {len(users) - 20} more"

    await query.edit_message_text(text, reply_markup=back_button("admin"), parse_mode="HTML")
    return ADMIN_MENU


async def admin_stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Force stop copy trading for all users."""
    query = update.callback_query
    await query.answer()

    db = context.bot_data.get("db")
    await db.disable_all_copy()

    copy_engine = context.bot_data.get("copy_engine")
    if copy_engine:
        await copy_engine.stop()

    await query.edit_message_text(
        "⏹️ All copy trading has been force-stopped.",
        reply_markup=back_button("admin"),
    )
    return ADMIN_MENU


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show system status."""
    query = update.callback_query
    await query.answer()

    import os
    import sys
    import platform

    tracker = context.bot_data.get("whale_tracker")
    copy_engine = context.bot_data.get("copy_engine")

    tracker_status = "🟢 Running" if (tracker and tracker._running) else "🔴 Stopped"
    engine_status = "🟢 Running" if (copy_engine and copy_engine._running) else "🔴 Stopped"

    text = (
        "📊 <b>SYSTEM STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🐍 Python: {sys.version.split()[0]}\n"
        f"💻 OS: {platform.system()} {platform.release()}\n"
        f"🐋 Whale Tracker: {tracker_status}\n"
        f"🤖 Copy Engine: {engine_status}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    await query.edit_message_text(text, reply_markup=back_button("admin"), parse_mode="HTML")
    return ADMIN_MENU
