"""
Trade history, PnL report, shareable PnL card, and trade journey handler.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import trade_history_keyboard, back_button
from bot.middlewares import auth_check
from bot.menus import HISTORY_MENU, PNL_MENU, TRADE_JOURNEY
from config.constants import ITEMS_PER_PAGE
from core.logger import get_logger

logger = get_logger(__name__)


async def history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show trade history with period filters."""
    if not await auth_check(update, context):
        return -1

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    page = context.user_data.get("history_page", 0)
    period = context.user_data.get("history_period", "all")

    # Determine date filter
    if period == "today":
        since = date.today().isoformat()
    elif period == "7d":
        since = (date.today() - timedelta(days=7)).isoformat()
    else:
        since = None

    trades = await db.list_trades(user_id, chain, since=since)
    total_pages = max(1, (len(trades) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_trades = trades[start:end]

    text = (
        "📜 <b>TRADE HISTORY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Period: {period.upper()} | Chain: {chain}\n"
        f"Total trades: {len(trades)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for i, t in enumerate(page_trades):
        emoji = "🟢" if t.get("action") == "BUY" else "🔴"
        pnl = float(t.get("pnl_usd", 0))
        pnl_str = f"${pnl:+.2f}" if pnl != 0 else "—"
        status = t.get("status", "UNKNOWN")
        trade_id = t.get("id", 0)
        remaining = float(t.get("remaining_pct", 100))
        remaining_str = f" [{remaining:.0f}%]" if remaining < 100 else ""
        
        text += (
            f"{emoji} {t.get('action', '?')} {t.get('token_symbol', '?')} | "
            f"${t.get('amount_in_usd', 0):.2f} | PnL: {pnl_str} | {status}{remaining_str}\n"
        )
        # Add clickable journey link
        text += f"  └─ <code>/journey_{trade_id}</code>\n"

    if not page_trades:
        text += "No trades found for this period.\n"

    keyboard = trade_history_keyboard(page, total_pages)

    query = update.callback_query
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")

    return HISTORY_MENU


async def history_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle period filter button."""
    query = update.callback_query
    await query.answer()

    period = query.data.replace("history_", "")  # 'today', '7d', 'all'
    context.user_data["history_period"] = period
    context.user_data["history_page"] = 0
    return await history_menu(update, context)


async def history_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle history pagination."""
    query = update.callback_query
    await query.answer()

    page = int(query.data.replace("history_page_", ""))
    context.user_data["history_page"] = page
    return await history_menu(update, context)


async def history_csv_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Export all trades as a CSV file."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    trades = await db.list_trades(user_id, chain)

    if not trades:
        await query.edit_message_text("No trades to export.", reply_markup=back_button("menu_history"))
        return HISTORY_MENU

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "chain", "action", "token_symbol", "token_address",
        "amount_in_usd", "amount_in_native", "entry_price_usd",
        "exit_price_usd", "pnl_usd", "status", "created_at",
    ])
    writer.writeheader()
    for t in trades:
        writer.writerow({k: t.get(k, "") for k in writer.fieldnames})

    csv_bytes = io.BytesIO(output.getvalue().encode())
    csv_bytes.name = f"trades_{chain}_{date.today().isoformat()}.csv"

    await update.effective_chat.send_document(
        document=csv_bytes,
        filename=csv_bytes.name,
        caption=f"📤 {chain} trade history ({len(trades)} trades)"
    )
    return HISTORY_MENU


# ── PnL Report ───────────────────────────────────────────────────────────────

async def pnl_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate and display PnL report."""
    if not await auth_check(update, context):
        return -1

    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")

    today = date.today().isoformat()
    stats = await db.get_daily_stats(user_id, today) or {}

    total_trades = int(stats.get("trades_count", 0))
    wins = int(stats.get("wins", 0))
    losses = int(stats.get("losses", 0))
    total_pnl = float(stats.get("total_pnl_usd", 0))
    daily_loss = float(stats.get("daily_loss_usd", 0))
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    text = (
        "📊 <b>PnL REPORT — TODAY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Date: {today}\n"
        f"📈 Trades: {total_trades}\n"
        f"✅ Wins: {wins} | ❌ Losses: {losses}\n"
        f"🎯 Win Rate: {win_rate:.1f}%\n"
        f"{pnl_emoji} Total PnL: ${total_pnl:+,.2f}\n"
        f"📉 Daily Loss: ${daily_loss:.2f}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [InlineKeyboardButton("🖼️ Share PnL Card", callback_data="history_pnl_card")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=keyboard, parse_mode="HTML")

    return PNL_MENU


# ── Shareable PnL Card ───────────────────────────────────────────────────────

async def share_pnl_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate and send a shareable PnL card image."""
    query = update.callback_query
    if query:
        await query.answer("Generating PnL card...")

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")
    username = update.effective_user.username or f"User{user_id}"

    today = date.today().isoformat()
    stats = await db.get_daily_stats(user_id, today) or {}

    total_trades = int(stats.get("trades_count", 0))
    wins = int(stats.get("wins", 0))
    losses = int(stats.get("losses", 0))
    total_pnl = float(stats.get("total_pnl_usd", 0))
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    # Get best and worst trades
    all_trades = await db.list_trades(user_id, chain)
    pnl_values = [float(t.get("pnl_usd", 0)) for t in all_trades if float(t.get("pnl_usd", 0)) != 0]
    best_trade = max(pnl_values) if pnl_values else 0
    worst_trade = min(pnl_values) if pnl_values else 0
    total_gas = sum(float(t.get("gas_used_usd", 0)) for t in all_trades)

    try:
        from trading.pnl_card import generate_pnl_card

        card_image = generate_pnl_card(
            username=username,
            period="Today",
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            total_pnl=total_pnl,
            best_trade=best_trade,
            worst_trade=worst_trade,
            win_rate=win_rate,
            total_gas=total_gas,
            chain=chain,
        )

        await update.effective_chat.send_photo(
            photo=card_image,
            caption=f"🐋 PnL Card — @{username} — {today}\n💰 Total: ${total_pnl:+,.2f} | Win Rate: {win_rate:.1f}%",
        )
    except ImportError:
        await update.effective_chat.send_message(
            "⚠️ PnL card generation requires Pillow. Install with: pip install Pillow",
        )
    except Exception as exc:
        logger.error("PnL card generation failed: %s", exc)
        await update.effective_chat.send_message(
            f"⚠️ Failed to generate PnL card: {exc}",
        )

    return HISTORY_MENU


# ── Trade Journey ────────────────────────────────────────────────────────────

async def trade_journey_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to select a trade for the journey timeline."""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    db = context.bot_data.get("db")
    chain = context.user_data.get("chain", "ETH")

    # Get recent trades with any events
    trades = await db.list_trades(user_id, chain)
    recent = trades[:10]  # Last 10 trades

    if not recent:
        text = "📋 No trades found for journey view."
        if query:
            await query.edit_message_text(text, reply_markup=back_button("menu_history"))
        else:
            await update.effective_chat.send_message(text, reply_markup=back_button("menu_history"))
        return HISTORY_MENU

    text = (
        "📋 <b>TRADE JOURNEY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select a trade to view its journey:\n\n"
    )

    buttons = []
    for t in recent:
        trade_id = t.get("id", 0)
        symbol = t.get("token_symbol", "???")
        pnl = float(t.get("pnl_usd", 0))
        status = t.get("status", "?")
        emoji = "🟢" if pnl >= 0 else "🔴"
        buttons.append([InlineKeyboardButton(
            f"{emoji} #{trade_id} {symbol} | ${pnl:+.2f} | {status}",
            callback_data=f"journey_{trade_id}",
        )])

    buttons.append([InlineKeyboardButton("◀️ Back", callback_data="menu_history")])

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    else:
        await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

    return TRADE_JOURNEY


async def trade_journey_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View the timeline/journey for a specific trade."""
    query = update.callback_query
    if query:
        await query.answer("Loading trade journey...")

    trade_id_str = query.data.replace("journey_", "")
    try:
        trade_id = int(trade_id_str)
    except (ValueError, TypeError):
        await query.edit_message_text("⚠️ Invalid trade ID.", reply_markup=back_button("menu_history"))
        return HISTORY_MENU

    db = context.bot_data.get("db")
    trade = await db.get_trade(trade_id)

    if not trade:
        await query.edit_message_text("⚠️ Trade not found.", reply_markup=back_button("menu_history"))
        return HISTORY_MENU

    events = await db.get_trade_events(trade_id)
    token_symbol = trade.get("token_symbol", "???")

    # Generate text timeline
    from trading.trade_journey import format_trade_journey_text
    timeline_text = format_trade_journey_text(trade, events, token_symbol)

    buttons = [
        [InlineKeyboardButton("🖼️ Journey Image", callback_data=f"journey_img_{trade_id}")],
        [InlineKeyboardButton("◀️ Back", callback_data="history_journey")],
    ]

    await query.edit_message_text(
        timeline_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )
    return TRADE_JOURNEY


async def trade_journey_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate and send a visual trade journey image."""
    query = update.callback_query
    if query:
        await query.answer("Generating journey image...")

    trade_id_str = query.data.replace("journey_img_", "")
    try:
        trade_id = int(trade_id_str)
    except (ValueError, TypeError):
        return TRADE_JOURNEY

    db = context.bot_data.get("db")
    trade = await db.get_trade(trade_id)
    if not trade:
        return TRADE_JOURNEY

    events = await db.get_trade_events(trade_id)
    token_symbol = trade.get("token_symbol", "???")

    try:
        from trading.trade_journey import generate_trade_journey_image
        img = generate_trade_journey_image(trade, events, token_symbol)
        username = update.effective_user.username or f"User{update.effective_user.id}"
        pnl = float(trade.get("pnl_usd", 0))

        await update.effective_chat.send_photo(
            photo=img,
            caption=f"📋 Trade Journey: ${token_symbol} — PnL: ${pnl:+,.2f}\n🐋 @{username}",
        )
    except ImportError:
        await update.effective_chat.send_message(
            "⚠️ Journey image requires Pillow. Install with: pip install Pillow",
        )
    except Exception as exc:
        logger.error("Journey image generation failed: %s", exc)
        await update.effective_chat.send_message(f"⚠️ Failed to generate journey image: {exc}")

    return TRADE_JOURNEY
