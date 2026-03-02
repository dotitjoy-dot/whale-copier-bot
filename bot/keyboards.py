"""
InlineKeyboardMarkup factory functions for the Telegram bot GUI.
Every menu screen in the bot has a corresponding keyboard builder here.
UI rules: emoji badges, truncated addresses, back/home buttons on every screen.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.constants import CHAIN_INFO, ITEMS_PER_PAGE, PROGRESS_BAR_LENGTH


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Progress bar
# ─────────────────────────────────────────────────────────────────────────────

def _progress_bar(pct: float, length: int = PROGRESS_BAR_LENGTH) -> str:
    """Generate a Unicode progress bar string from a percentage."""
    filled = int(pct / 100 * length)
    return "▓" * filled + "░" * (length - filled) + f" {pct:.0f}%"


def _truncate(address: str, pre: int = 6, suf: int = 4) -> str:
    """Return a truncated address like 0x1234...5678."""
    if len(address) > pre + suf + 3:
        return f"{address[:pre]}...{address[-suf:]}"
    return address


# ─────────────────────────────────────────────────────────────────────────────
# Main Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def main_dashboard_keyboard(is_copy_active: bool, chain: str) -> InlineKeyboardMarkup:
    """
    Build the main dashboard inline keyboard.

    Args:
        is_copy_active: Whether copy trading is currently running.
        chain: Currently selected chain name (ETH/BSC/SOL).

    Returns:
        InlineKeyboardMarkup for the dashboard.
    """
    copy_icon = "🟢" if is_copy_active else "🔴"
    chain_emoji = CHAIN_INFO.get(chain, {}).get("emoji", "⛓️")

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 My Wallets", callback_data="menu_wallets"),
         InlineKeyboardButton("🐋 Whale Wallets", callback_data="menu_whales")],
        [InlineKeyboardButton(f"{chain_emoji} Chain: {chain}", callback_data="menu_chain"),
         InlineKeyboardButton(f"🚦 Copy Trading {copy_icon}", callback_data="menu_copy")],
        [InlineKeyboardButton("💹 Portfolio", callback_data="menu_portfolio"),
         InlineKeyboardButton("📜 History", callback_data="menu_history")],
        [InlineKeyboardButton("💰 DCA Orders", callback_data="menu_dca"),
         InlineKeyboardButton("🎯 Limit Orders", callback_data="menu_limit_orders")],
        [InlineKeyboardButton("🔔 Price Alerts", callback_data="menu_alerts_price"),
         InlineKeyboardButton("🛡️ Token Audit", callback_data="menu_audit")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
         InlineKeyboardButton("📊 PnL Report", callback_data="menu_pnl")],
        [InlineKeyboardButton("🚨 KILL SWITCH", callback_data="menu_kill_switch"),
         InlineKeyboardButton("🔄 Refresh", callback_data="menu_dashboard")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Wallet Menu
# ─────────────────────────────────────────────────────────────────────────────

def wallet_menu_keyboard(wallets: list) -> InlineKeyboardMarkup:
    """
    Build the wallet management menu keyboard.

    Args:
        wallets: List of wallet dicts from list_user_wallets.

    Returns:
        InlineKeyboardMarkup with wallet actions and wallet list.
    """
    buttons = [
        [InlineKeyboardButton("➕ Create Wallet", callback_data="wallet_create"),
         InlineKeyboardButton("📥 Import Wallet", callback_data="wallet_import")],
        [InlineKeyboardButton("📤 Export Wallet", callback_data="wallet_export"),
         InlineKeyboardButton("💵 Check Balance", callback_data="wallet_balance")],
        [InlineKeyboardButton("🗑️ Remove Wallet", callback_data="wallet_remove")],
    ]

    for w in wallets[:10]:
        chain_emoji = CHAIN_INFO.get(w.get("chain", ""), {}).get("emoji", "")
        label = w.get("label", "Wallet")
        addr = _truncate(w.get("address", ""))
        buttons.append([
            InlineKeyboardButton(
                f"{chain_emoji} {label}: {addr}",
                callback_data=f"wallet_info_{w.get('wallet_id', 0)}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# Chain Selector
# ─────────────────────────────────────────────────────────────────────────────

def chain_selector_keyboard(current: str) -> InlineKeyboardMarkup:
    """
    Build the chain selection toggle keyboard.

    Args:
        current: Currently active chain name.

    Returns:
        InlineKeyboardMarkup with chain toggle buttons.
    """
    buttons = []
    for chain_code, info in CHAIN_INFO.items():
        check = "  ✅" if chain_code == current else ""
        buttons.append([
            InlineKeyboardButton(
                f"{info['emoji']} {info['name']}{check}",
                callback_data=f"chain_select_{chain_code}"
            )
        ])
    buttons.append([
        InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# Whale List
# ─────────────────────────────────────────────────────────────────────────────

def whale_list_keyboard(whales: list, page: int = 0) -> InlineKeyboardMarkup:
    """
    Build paginated whale wallet list keyboard.

    Args:
        whales: List of whale wallet dicts.
        page: Current page number (0-indexed).

    Returns:
        InlineKeyboardMarkup with whale entries and pagination.
    """
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_whales = whales[start:end]
    total_pages = max(1, (len(whales) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    buttons = [
        [InlineKeyboardButton("➕ Add Whale", callback_data="whale_add"),
         InlineKeyboardButton("❌ Remove Whale", callback_data="whale_remove")],
    ]

    for w in page_whales:
        chain_emoji = CHAIN_INFO.get(w.get("chain", ""), {}).get("emoji", "")
        status = "🟢" if w.get("is_active", 0) else "🔴"
        label = w.get("label", "") or "Whale"
        addr = _truncate(w.get("address", ""))
        buttons.append([
            InlineKeyboardButton(
                f"{status} {chain_emoji} {label}: {addr}",
                callback_data=f"whale_inspect_{w.get('id', 0)}"
            )
        ])

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"whale_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if end < len(whales):
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"whale_page_{page + 1}"))
    buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_leaderboard"),
    ])

    buttons.append([
        InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# Copy Trading Control
# ─────────────────────────────────────────────────────────────────────────────

def copy_control_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    """
    Build the copy trading control keyboard.

    Args:
        is_active: Whether copy trading is currently enabled.

    Returns:
        InlineKeyboardMarkup with start/stop and position controls.
    """
    if is_active:
        toggle_btn = InlineKeyboardButton("⏹️ STOP Copy Trading", callback_data="copy_stop")
    else:
        toggle_btn = InlineKeyboardButton("▶️ START Copy Trading", callback_data="copy_start")

    return InlineKeyboardMarkup([
        [toggle_btn],
        [InlineKeyboardButton("📈 Open Positions", callback_data="copy_positions")],
        [InlineKeyboardButton("⚡ Force Close Position", callback_data="copy_force_close")],
        [InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard"),
         InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Money Management
# ─────────────────────────────────────────────────────────────────────────────

def money_mgmt_keyboard(config: Dict) -> InlineKeyboardMarkup:
    """
    Build the money management settings keyboard showing current values.

    Args:
        config: copy_config dict with current settings.

    Returns:
        InlineKeyboardMarkup for money management menu.
    """
    mode = config.get("trade_size_mode", "fixed").upper()
    fixed = config.get("fixed_amount_usd", 10.0)
    pct = config.get("percent_of_balance", 5.0)
    mult = config.get("mirror_multiplier", 1.0)
    max_pos = config.get("max_position_usd", 100.0)
    paper = "✅" if config.get("paper_trading_enabled", 0) else "❌"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🤖 Paper Trading: {paper}", callback_data="money_toggle_paper")],
        [InlineKeyboardButton(f"🕹️ Execution Mode: {mode}", callback_data="money_mode")],
        [InlineKeyboardButton(f"💵 Fixed Bet: ${fixed:.2f}", callback_data="money_fixed"),
         InlineKeyboardButton(f"📈 % Balance: {pct:.1f}%", callback_data="money_percent")],
        [InlineKeyboardButton(f"🪞 Whale Multiplier: {mult:.1f}x", callback_data="money_multiplier")],
        [InlineKeyboardButton(f"🔒 Max Position Size: ${max_pos:.2f}", callback_data="money_max_pos")],
        [InlineKeyboardButton("◀️ Settings", callback_data="menu_settings"),
         InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Risk Management
# ─────────────────────────────────────────────────────────────────────────────

def risk_mgmt_keyboard(config: Dict) -> InlineKeyboardMarkup:
    """
    Build the risk management settings keyboard showing current values.
    Includes custom gas, break-even SL, auto-sell, partial TPs, and smart slippage.
    """
    sl = config.get("stop_loss_pct", 20.0)
    tp = config.get("take_profit_pct", 50.0)
    ts = config.get("trailing_stop_pct", 0.0)
    daily = config.get("daily_loss_limit_usd", 50.0)
    slip = config.get("max_slippage_pct", 5.0)
    mev = "✅" if config.get("mev_protect_enabled", 1) else "❌"
    smart_slip = "✅" if config.get("smart_slippage_enabled", 1) else "❌"
    custom_gas = float(config.get("custom_gas_gwei", 0))
    priority_tip = float(config.get("priority_tip_gwei", 0))
    be_enabled = "✅" if config.get("breakeven_enabled", 0) else "❌"
    be_trigger = float(config.get("breakeven_trigger_pct", 50.0))
    auto_sell = float(config.get("auto_sell_hours", 0))
    auto_sell_str = f"{auto_sell:.0f}h" if auto_sell > 0 else "OFF"
    partial_tp = "✅" if config.get("partial_tp_enabled", 0) else "❌"
    gas_str = f"{custom_gas:.1f}" if custom_gas > 0 else "AUTO"
    tip_str = f"{priority_tip:.1f}" if priority_tip > 0 else "AUTO"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🛡️ MEV Protection: {mev}", callback_data="risk_toggle_mev")],
        [InlineKeyboardButton(f"🔻 Stop Loss: {sl:.1f}%", callback_data="risk_sl"),
         InlineKeyboardButton(f"🔺 Take Profit: {tp:.1f}%", callback_data="risk_tp")],
        [InlineKeyboardButton(f"📉 Trailing Stop: {ts:.1f}%", callback_data="risk_ts")],
        [InlineKeyboardButton(f"🛡️ Break-Even SL: {be_enabled} ({be_trigger:.0f}%)", callback_data="risk_breakeven")],
        [InlineKeyboardButton(f"🟡 Partial TPs: {partial_tp}", callback_data="risk_partial_tp")],
        [InlineKeyboardButton(f"⏰ Auto-Sell: {auto_sell_str}", callback_data="risk_auto_sell")],
        [InlineKeyboardButton(f"📅 Daily Loss: ${daily:.2f}", callback_data="risk_daily")],
        [InlineKeyboardButton(f"💧 Slippage: {slip:.1f}%", callback_data="risk_slippage"),
         InlineKeyboardButton(f"🧠 Smart Slip: {smart_slip}", callback_data="risk_toggle_smart_slip")],
        [InlineKeyboardButton(f"⛽ Gas: {gas_str} gwei", callback_data="risk_custom_gas"),
         InlineKeyboardButton(f"🚀 Tip: {tip_str} gwei", callback_data="risk_priority_tip")],
        [InlineKeyboardButton(f"🧊 Anti-FOMO: {int(config.get('cooldown_minutes', 0))}m", callback_data="risk_cooldown")],
        [InlineKeyboardButton("◀️ Settings", callback_data="menu_settings"),
         InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Open Positions
# ─────────────────────────────────────────────────────────────────────────────

def open_positions_keyboard(trades: list) -> InlineKeyboardMarkup:
    """
    Build keyboard showing open positions with live PnL indicators.

    Args:
        trades: List of open trade dicts.

    Returns:
        InlineKeyboardMarkup with position entries.
    """
    buttons = []
    for t in trades[:10]:
        symbol = t.get("token_symbol", "?")
        pnl = float(t.get("pnl_usd", 0))
        emoji = "📈" if pnl >= 0 else "📉"
        amount = t.get("amount_in_usd", 0)
        buttons.append([
            InlineKeyboardButton(
                f"{emoji} {symbol} | ${amount:.2f} | PnL: ${pnl:+.2f}",
                callback_data=f"trade_detail_{t.get('id', 0)}"
            )
        ])

    if not trades:
        buttons.append([InlineKeyboardButton("No open positions", callback_data="noop")])

    buttons.append([
        InlineKeyboardButton("◀️ Back", callback_data="menu_copy"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# Trade History
# ─────────────────────────────────────────────────────────────────────────────

def trade_history_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Build trade history navigation keyboard with PnL card and journey buttons.
    """
    buttons = [
        [InlineKeyboardButton("📅 Today", callback_data="history_today"),
         InlineKeyboardButton("📆 Last 7 Days", callback_data="history_7d")],
        [InlineKeyboardButton("📋 All Time", callback_data="history_all"),
         InlineKeyboardButton("📤 Export CSV", callback_data="history_csv")],
        [InlineKeyboardButton("🖼️ Share PnL Card", callback_data="history_pnl_card"),
         InlineKeyboardButton("📋 Trade Journey", callback_data="history_journey")],
        [InlineKeyboardButton("📝 Trade Notes", callback_data="menu_notes")],
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"history_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page + 1 < total_pages:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"history_page_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("◀️ Back", callback_data="menu_dashboard"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# Confirm Action (YES/NO)
# ─────────────────────────────────────────────────────────────────────────────

def confirm_action_keyboard(action_id: str) -> InlineKeyboardMarkup:
    """
    Build a YES/NO confirmation keyboard.

    Args:
        action_id: Identifier for the action being confirmed.

    Returns:
        InlineKeyboardMarkup with confirm/cancel buttons.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Confirm", callback_data=f"confirm_yes_{action_id}"),
         InlineKeyboardButton("❌ Cancel", callback_data=f"confirm_no_{action_id}")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Settings Menu
# ─────────────────────────────────────────────────────────────────────────────

def settings_keyboard() -> InlineKeyboardMarkup:
    """Build the main settings hub keyboard with all feature options."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 Money Mgmt", callback_data="settings_money"),
         InlineKeyboardButton("🛡️ Risk Mgmt", callback_data="settings_risk")],
        [InlineKeyboardButton("🔍 Trade Filters", callback_data="settings_filters"),
         InlineKeyboardButton("🚫 Blacklist", callback_data="settings_blacklist")],
        [InlineKeyboardButton("🔔 Alert Settings", callback_data="settings_alerts"),
         InlineKeyboardButton("🎯 Auto-Sniper", callback_data="settings_sniper")],
        [InlineKeyboardButton("⏸️ Snooze Mode", callback_data="settings_snooze"),
         InlineKeyboardButton("🔄 Wallet Rotation", callback_data="settings_rotation")],
        [InlineKeyboardButton("◀️ Return to Dashboard", callback_data="menu_dashboard")],
    ])


def sniper_settings_keyboard(config: Dict) -> InlineKeyboardMarkup:
    """Build the auto-sniper settings keyboard."""
    enabled = "✅" if config.get("sniper_enabled", 0) else "❌"
    min_liq = float(config.get("sniper_min_liquidity_usd", 10000))
    max_age = int(config.get("sniper_max_age_minutes", 30))
    amount = float(config.get("sniper_amount_usd", 10.0))

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🎯 Sniper Mode: {enabled}", callback_data="sniper_toggle")],
        [InlineKeyboardButton(f"💰 Buy Amount: ${amount:.2f}", callback_data="sniper_amount")],
        [InlineKeyboardButton(f"💧 Min Liquidity: ${min_liq:,.0f}", callback_data="sniper_min_liq")],
        [InlineKeyboardButton(f"⏱️ Max Age: {max_age} min", callback_data="sniper_max_age")],
        [InlineKeyboardButton("◀️ Settings", callback_data="menu_settings"),
         InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard")],
    ])


def partial_tp_keyboard(steps: list, enabled: bool) -> InlineKeyboardMarkup:
    """Build the partial take profit settings keyboard."""
    status = "✅ ON" if enabled else "❌ OFF"
    buttons = [
        [InlineKeyboardButton(f"🟡 Partial TPs: {status}", callback_data="partial_tp_toggle")],
    ]

    if steps:
        for step in steps:
            sell_pct = float(step.get("sell_pct", 0))
            target = float(step.get("target_multiple", 0))
            buttons.append([
                InlineKeyboardButton(
                    f"Step {step.get('step_order', '?')}: Sell {sell_pct:.0f}% at {target:.1f}x",
                    callback_data="noop"
                )
            ])
    else:
        buttons.append([InlineKeyboardButton("No steps configured", callback_data="noop")])

    buttons.append([InlineKeyboardButton("📝 Set Default (50/25/25)", callback_data="partial_tp_default")])
    buttons.append([InlineKeyboardButton("✏️ Custom Steps", callback_data="partial_tp_custom")])
    buttons.append([
        InlineKeyboardButton("◀️ Risk Mgmt", callback_data="settings_risk"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard"),
    ])
    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# Back Button Helper
# ─────────────────────────────────────────────────────────────────────────────

def back_button(target: str) -> InlineKeyboardMarkup:
    """
    Build a simple back + home button row.

    Args:
        target: Callback data for the back button target.

    Returns:
        InlineKeyboardMarkup with back and home buttons.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Back", callback_data=target),
         InlineKeyboardButton("🏠 Main Menu", callback_data="menu_dashboard")],
    ])
