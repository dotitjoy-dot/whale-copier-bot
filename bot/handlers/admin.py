"""
Advanced Admin Panel — full control dashboard for the bot owner.

Features:
  - Real-time user & subscription stats
  - License key generation (bulk or single)
  - User management: ban/unban, upgrade, revoke, inspect
  - Key list and revocation
  - Broadcast messages
  - System status
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import back_button
from bot.menus import ADMIN_MENU, ADMIN_BROADCAST
from core.auth_manager import AuthManager, TIERS, TRIAL_DAYS
from core.logger import get_logger

logger = get_logger(__name__)

# Extra admin states (above existing ADMIN_MENU / ADMIN_BROADCAST)
ADMIN_KEY_GEN       = 1301
ADMIN_KEY_LIST      = 1302
ADMIN_USER_LIST     = 1303
ADMIN_USER_INSPECT  = 1304
ADMIN_GRANT_TIER    = 1305
ADMIN_SET_DURATION  = 1306
ADMIN_BAN_CONFIRM   = 1307
ADMIN_NOTES_INPUT   = 1308


def _admin_check(auth: AuthManager, user_id: int) -> bool:
    return auth is not None and auth.is_admin(user_id)


# ─────────────────────────────────────────────────────────────────────────────
# Main Admin Dashboard
# ─────────────────────────────────────────────────────────────────────────────

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the full admin control panel."""
    user_id = update.effective_user.id
    auth: AuthManager = context.bot_data.get("auth")

    if not _admin_check(auth, user_id):
        msg = update.effective_message
        if msg:
            await msg.reply_text("⛔ Admin access only.")
        return -1

    db = context.bot_data.get("db")
    all_users = await db.list_all_users()
    stats = await db.get_subscription_stats()
    keys = await db.list_license_keys(unredeemed_only=True)

    # Build stats summary
    total = len(all_users)
    pro_count   = stats.get("PRO",   {}).get("count", 0)
    elite_count = stats.get("ELITE", {}).get("count", 0)
    free_count  = stats.get("FREE",  {}).get("count", 0)
    banned      = sum(s.get("banned", 0) for s in stats.values())
    avail_keys  = len(keys)

    text = (
        "🔑 <b>ADMIN CONTROL PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users:   <b>{total}</b>\n"
        f"🆓 Free/Trial:    <b>{free_count}</b>\n"
        f"⭐ Pro:           <b>{pro_count}</b>\n"
        f"💎 Elite:         <b>{elite_count}</b>\n"
        f"🚫 Banned:        <b>{banned}</b>\n"
        f"🔑 Active Keys:   <b>{avail_keys}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [InlineKeyboardButton("🔑 Generate License Key",  callback_data="admin_keygen")],
        [InlineKeyboardButton("📋 View Active Keys",      callback_data="admin_keylist")],
        [InlineKeyboardButton("👥 Manage Users",          callback_data="admin_users")],
        [InlineKeyboardButton("📢 Broadcast Message",     callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 System Status",         callback_data="admin_status")],
        [InlineKeyboardButton("⏹️ Force Stop ALL Copy",   callback_data="admin_stop_all")],
        [InlineKeyboardButton("◀️ Back to Dashboard",     callback_data="menu_dashboard")],
    ]

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

    return ADMIN_MENU


# ─────────────────────────────────────────────────────────────────────────────
# License Key Generation
# ─────────────────────────────────────────────────────────────────────────────

async def admin_keygen_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show license key generation menu — choose tier and duration."""
    query = update.callback_query
    await query.answer()

    text = (
        "🔑 <b>GENERATE LICENSE KEY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select tier and duration:\n\n"
        "⭐ PRO:   10 whales, DCA, alerts, limit orders\n"
        "💎 ELITE: 50 whales, all features + sniper"
    )

    buttons = [
        [InlineKeyboardButton("⭐ PRO  — 30 days",  callback_data="admin_key_PRO_30"),
         InlineKeyboardButton("⭐ PRO  — 90 days",  callback_data="admin_key_PRO_90")],
        [InlineKeyboardButton("⭐ PRO  — 180 days", callback_data="admin_key_PRO_180"),
         InlineKeyboardButton("⭐ PRO  — 365 days", callback_data="admin_key_PRO_365")],
        [InlineKeyboardButton("💎 ELITE — 30 days", callback_data="admin_key_ELITE_30"),
         InlineKeyboardButton("💎 ELITE — 90 days", callback_data="admin_key_ELITE_90")],
        [InlineKeyboardButton("💎 ELITE — 180 days",callback_data="admin_key_ELITE_180"),
         InlineKeyboardButton("💎 ELITE — 365 days",callback_data="admin_key_ELITE_365")],
        [InlineKeyboardButton("📦 Bulk: 5× PRO 30d",  callback_data="admin_bulk_PRO_30_5"),
         InlineKeyboardButton("📦 Bulk: 5× ELITE 30d",callback_data="admin_bulk_ELITE_30_5")],
        [InlineKeyboardButton("◀️ Back", callback_data="admin")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return ADMIN_KEY_GEN


async def admin_keygen_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate key(s) based on callback data: admin_key_TIER_DAYS or admin_bulk_TIER_DAYS_QTY."""
    query = update.callback_query
    await query.answer()

    data = query.data  # e.g. admin_key_PRO_30 or admin_bulk_PRO_30_5
    parts = data.split("_")

    auth: AuthManager = context.bot_data.get("auth")
    db = context.bot_data.get("db")
    admin_id = update.effective_user.id

    if parts[1] == "bulk":
        # admin_bulk_TIER_DAYS_QTY
        tier = parts[2]
        days = int(parts[3])
        qty  = int(parts[4])
    else:
        # admin_key_TIER_DAYS
        tier = parts[2]
        days = int(parts[3])
        qty  = 1

    generated = []
    for _ in range(qty):
        lk = auth.generate_key(tier, days, admin_id)
        await db.save_license_key(lk.key, lk.tier, lk.duration_days, admin_id)
        generated.append(lk.key)

    tier_info = TIERS.get(tier, {})
    keys_text = "\n".join(f"<code>{k}</code>" for k in generated)
    text = (
        f"✅ <b>{qty} key(s) generated!</b>\n"
        f"🎯 Tier: {tier_info.get('label', tier)}\n"
        f"📅 Duration: {days} days\n\n"
        f"🔑 <b>Keys:</b>\n{keys_text}\n\n"
        "<i>Copy and share these keys with users.</i>"
    )

    buttons = [
        [InlineKeyboardButton("🔑 Generate More", callback_data="admin_keygen")],
        [InlineKeyboardButton("◀️ Admin Panel",   callback_data="admin")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return ADMIN_KEY_GEN


# ─────────────────────────────────────────────────────────────────────────────
# Key List + Revoke
# ─────────────────────────────────────────────────────────────────────────────

async def admin_key_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show unredeemed license keys with revoke buttons."""
    query = update.callback_query
    await query.answer()

    auth: AuthManager = context.bot_data.get("auth")
    unredeemed = auth.list_keys(show_redeemed=False)[:15]

    if not unredeemed:
        await query.edit_message_text(
            "📋 No active (unredeemed) keys.",
            reply_markup=back_button("admin"),
        )
        return ADMIN_KEY_LIST

    text = "📋 <b>ACTIVE LICENSE KEYS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []
    for lk in unredeemed:
        tier_info = TIERS.get(lk.tier, {})
        text += (
            f"🔑 <code>{lk.key}</code>\n"
            f"   {tier_info.get('label', lk.tier)} | {lk.duration_days}d\n\n"
        )
        buttons.append([InlineKeyboardButton(
            f"🗑️ Revoke {lk.key[:12]}...",
            callback_data=f"admin_revoke_key_{lk.key}"
        )])

    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="admin")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return ADMIN_KEY_LIST


async def admin_revoke_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Revoke a license key."""
    query = update.callback_query
    await query.answer()

    key_str = query.data.replace("admin_revoke_key_", "")
    auth: AuthManager = context.bot_data.get("auth")
    db = context.bot_data.get("db")

    revoked = auth.revoke_key(key_str)
    await db.delete_license_key(key_str)

    if revoked:
        await query.answer(f"✅ Key {key_str[:12]}... revoked.", show_alert=True)
    else:
        await query.answer("❌ Key not found.", show_alert=True)

    return await admin_key_list(update, context)


# ─────────────────────────────────────────────────────────────────────────────
# User Management
# ─────────────────────────────────────────────────────────────────────────────

async def admin_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """List all users with their subscription status."""
    query = update.callback_query
    await query.answer()

    db = context.bot_data.get("db")
    auth: AuthManager = context.bot_data.get("auth")

    users = await db.list_all_users()
    page = context.user_data.get("admin_user_page", 0)
    per_page = 8
    slice_start = page * per_page
    page_users = users[slice_start: slice_start + per_page]

    text = f"👥 <b>USER MANAGEMENT</b> (Page {page + 1})\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    buttons = []
    for u in page_users:
        uid = u["telegram_id"]
        sub = auth.get_subscription(uid)
        tier_label = TIERS.get(sub.tier, {}).get("label", sub.tier)
        ban_icon = "🚫" if sub.is_banned else ("✅" if sub.is_active else "⏳")
        username = u.get("username") or f"uid:{uid}"
        text += f"{ban_icon} <b>{username}</b>  [{tier_label}]\n"
        buttons.append([InlineKeyboardButton(
            f"🔍 {username[:20]}",
            callback_data=f"admin_inspect_{uid}"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data="admin_users_prev"))
    if slice_start + per_page < len(users):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data="admin_users_next"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="admin")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return ADMIN_USER_LIST


async def admin_users_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if "next" in query.data:
        context.user_data["admin_user_page"] = context.user_data.get("admin_user_page", 0) + 1
    else:
        context.user_data["admin_user_page"] = max(0, context.user_data.get("admin_user_page", 0) - 1)
    return await admin_user_list(update, context)


async def admin_inspect_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show detailed info and actions for a single user."""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("admin_inspect_"):
        uid = int(query.data.replace("admin_inspect_", ""))
        context.user_data["admin_target_uid"] = uid
    else:
        uid = context.user_data.get("admin_target_uid")
        if not uid:
            return await admin_user_list(update, context)

    auth: AuthManager = context.bot_data.get("auth")
    db = context.bot_data.get("db")

    sub = auth.get_subscription(uid)
    db_user = await db.get_user(uid)
    username = db_user.get("username", f"uid:{uid}") if db_user else f"uid:{uid}"
    tier_info = TIERS.get(sub.tier, {})

    expires_str = sub.expires_at.strftime("%Y-%m-%d") if sub.expires_at else "N/A (trial)"
    trial_end = (sub.trial_started_at + __import__("datetime").timedelta(days=TRIAL_DAYS)).strftime("%Y-%m-%d")

    text = (
        f"🔍 <b>USER: {username}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Telegram ID: <code>{uid}</code>\n"
        f"🎯 Tier: {tier_info.get('label', sub.tier)}\n"
        f"📅 Expires: {expires_str}\n"
        f"🆓 Trial ends: {trial_end}\n"
        f"⏳ Days left: {sub.days_remaining}\n"
        f"🚫 Banned: {'Yes' if sub.is_banned else 'No'}\n"
        f"📝 Notes: {sub.notes or '-'}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    ban_btn = (
        InlineKeyboardButton("✅ Unban", callback_data=f"admin_unban_{uid}")
        if sub.is_banned
        else InlineKeyboardButton("🚫 Ban User", callback_data=f"admin_ban_{uid}")
    )

    buttons = [
        [InlineKeyboardButton("⭐ Grant PRO",   callback_data=f"admin_grant_PRO_{uid}"),
         InlineKeyboardButton("💎 Grant ELITE", callback_data=f"admin_grant_ELITE_{uid}")],
        [InlineKeyboardButton("🔄 Revoke Sub",  callback_data=f"admin_revoke_sub_{uid}"),
         ban_btn],
        [InlineKeyboardButton("◀️ Back to Users", callback_data="admin_users")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return ADMIN_USER_INSPECT


async def admin_grant_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin grants a tier to user — picks duration preset."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")  # admin_grant_TIER_UID
    tier = parts[2]
    uid  = int(parts[3])
    context.user_data["admin_target_uid"] = uid
    context.user_data["admin_grant_tier"] = tier

    tier_info = TIERS.get(tier, {})
    text = (
        f"💎 <b>GRANT {tier_info.get('label', tier)}</b>\n"
        f"To user: <code>{uid}</code>\n\n"
        "Select duration:"
    )
    buttons = [
        [InlineKeyboardButton("30 days",  callback_data=f"admin_grantdo_{tier}_{uid}_30"),
         InlineKeyboardButton("90 days",  callback_data=f"admin_grantdo_{tier}_{uid}_90")],
        [InlineKeyboardButton("180 days", callback_data=f"admin_grantdo_{tier}_{uid}_180"),
         InlineKeyboardButton("365 days", callback_data=f"admin_grantdo_{tier}_{uid}_365")],
        [InlineKeyboardButton("◀️ Back",  callback_data=f"admin_inspect_{uid}")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    return ADMIN_GRANT_TIER


async def admin_grant_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Actually grant the subscription."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")  # admin_grantdo_TIER_UID_DAYS
    tier = parts[2]
    uid  = int(parts[3])
    days = int(parts[4])

    auth: AuthManager = context.bot_data.get("auth")
    db   = context.bot_data.get("db")

    sub = auth.set_subscription(uid, tier, days)
    await _save_sub_to_db(db, sub)

    tier_info = TIERS.get(tier, {})
    await query.answer(f"✅ Granted {tier_info.get('label', tier)} for {days} days!", show_alert=True)

    # Notify user
    try:
        expiry = sub.expires_at.strftime("%Y-%m-%d") if sub.expires_at else "N/A"
        await context.bot.send_message(
            chat_id=uid,
            text=(
                f"🎉 <b>Subscription Activated!</b>\n\n"
                f"🎯 Tier: {tier_info.get('label', tier)}\n"
                f"📅 Valid until: {expiry}\n\n"
                "Enjoy your upgraded access! Use /start to continue."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    context.user_data["admin_target_uid"] = uid
    return await admin_inspect_user(update, context)


async def admin_revoke_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Revoke a user's subscription immediately."""
    query = update.callback_query
    await query.answer()

    uid = int(query.data.replace("admin_revoke_sub_", ""))
    auth: AuthManager = context.bot_data.get("auth")
    db   = context.bot_data.get("db")

    auth.revoke_subscription(uid)
    sub = auth.get_subscription(uid)
    await _save_sub_to_db(db, sub)

    await query.answer("✅ Subscription revoked.", show_alert=True)

    try:
        await context.bot.send_message(
            chat_id=uid,
            text="⚠️ Your subscription has been <b>revoked</b> by the admin.\nPlease contact support.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    context.user_data["admin_target_uid"] = uid
    return await admin_inspect_user(update, context)


async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ban a user."""
    query = update.callback_query
    await query.answer()

    uid = int(query.data.replace("admin_ban_", ""))
    auth: AuthManager = context.bot_data.get("auth")
    db   = context.bot_data.get("db")

    auth.ban_user(uid, notes="Banned by admin")
    sub = auth.get_subscription(uid)
    await _save_sub_to_db(db, sub)

    await query.answer(f"🚫 User {uid} banned.", show_alert=True)

    try:
        await context.bot.send_message(
            chat_id=uid,
            text="⛔ Your account has been <b>banned</b>. Contact support if you believe this is an error.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    context.user_data["admin_target_uid"] = uid
    return await admin_inspect_user(update, context)


async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Unban a user."""
    query = update.callback_query
    await query.answer()

    uid = int(query.data.replace("admin_unban_", ""))
    auth: AuthManager = context.bot_data.get("auth")
    db   = context.bot_data.get("db")

    auth.unban_user(uid)
    sub = auth.get_subscription(uid)
    await _save_sub_to_db(db, sub)

    await query.answer(f"✅ User {uid} unbanned.", show_alert=True)

    try:
        await context.bot.send_message(
            chat_id=uid,
            text="✅ Your account has been <b>unbanned</b>. Use /start to continue.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    context.user_data["admin_target_uid"] = uid
    return await admin_inspect_user(update, context)


# ─────────────────────────────────────────────────────────────────────────────
# Broadcast + Status (existing features, updated)
# ─────────────────────────────────────────────────────────────────────────────

async def admin_broadcast_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📢 <b>BROADCAST MESSAGE</b>\n\n"
        "Type the HTML message to send to ALL users.\n"
        "You can use <b>bold</b>, <i>italic</i>, <code>code</code> tags.",
        parse_mode="HTML",
    )
    return ADMIN_BROADCAST


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg_text = update.message.text.strip()
    db = context.bot_data.get("db")
    users = await db.list_all_users()

    sent = failed = 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=f"📢 <b>ANNOUNCEMENT</b>\n\n{msg_text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # Respect Telegram rate limits

    await update.effective_chat.send_message(
        f"📢 Broadcast complete!\n✅ Sent: {sent}\n❌ Failed: {failed}",
        reply_markup=back_button("admin"),
    )
    return ADMIN_MENU


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    import sys, platform
    tracker     = context.bot_data.get("whale_tracker")
    copy_engine = context.bot_data.get("copy_engine")
    auth: AuthManager = context.bot_data.get("auth")

    tracker_status = "🟢 Running" if (tracker and getattr(tracker, "_running", False)) else "🔴 Stopped"
    engine_status  = "🟢 Running" if (copy_engine and getattr(copy_engine, "_running", False)) else "🔴 Stopped"

    subs = auth.list_subscriptions() if auth else []
    active_sessions = sum(1 for uid in auth._sessions if auth._sessions.get(uid)) if auth else 0

    text = (
        "📊 <b>SYSTEM STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🐍 Python: {sys.version.split()[0]}\n"
        f"💻 OS: {platform.system()} {platform.release()}\n"
        f"🐋 Whale Tracker: {tracker_status}\n"
        f"🤖 Copy Engine: {engine_status}\n"
        f"👤 Active Sessions: {active_sessions}\n"
        f"👥 Total Subscribers: {len(subs)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    await query.edit_message_text(text, reply_markup=back_button("admin"), parse_mode="HTML")
    return ADMIN_MENU


async def admin_stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    db = context.bot_data.get("db")
    await db.disable_all_copy()

    copy_engine = context.bot_data.get("copy_engine")
    if copy_engine:
        try:
            await copy_engine.stop()
        except Exception:
            pass

    await query.edit_message_text(
        "⏹️ <b>All copy trading force-stopped.</b>",
        reply_markup=back_button("admin"),
        parse_mode="HTML",
    )
    return ADMIN_MENU


async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Alias — go to user list."""
    context.user_data["admin_user_page"] = 0
    return await admin_user_list(update, context)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _save_sub_to_db(db, sub) -> None:
    """Persist a UserSubscription to the database."""
    expires_str = sub.expires_at.isoformat() if sub.expires_at else ""
    trial_str   = sub.trial_started_at.isoformat()
    await db.upsert_subscription(
        sub.telegram_id, sub.tier, expires_str,
        int(sub.is_banned), trial_str, sub.notes,
    )
