"""
Notification templates for push alerts to Telegram users.
Formats rich HTML messages for whale detections, trade executions, SL/TP hits,
and daily reports using Telegram's HTML parse mode.
"""

from __future__ import annotations

from typing import Dict, Optional

from config.constants import CHAIN_INFO


def _truncate(s: str, pre: int = 6, suf: int = 4) -> str:
    """Truncate an address/hash for display."""
    if len(s) > pre + suf + 3:
        return f"{s[:pre]}...{s[-suf:]}"
    return s


def _explorer_link(chain: str, tx_hash: str) -> str:
    """Build a block explorer link for a transaction hash."""
    base = CHAIN_INFO.get(chain, {}).get("explorer", "")
    if not base:
        return tx_hash[:20]
    return f'<a href="{base}/tx/{tx_hash}">{_truncate(tx_hash)}</a>'


def notify_whale_detected(
    chain: str,
    whale_address: str,
    whale_label: str,
    action: str,
    token_symbol: str,
    token_address: str,
    amount_usd: float,
    amount_native: float,
    tx_hash: str,
) -> str:
    """
    Format a whale detection notification message (HTML).

    Args:
        chain: Chain name.
        whale_address: Whale wallet address.
        whale_label: Human label for the whale.
        action: 'BUY' or 'SELL'.
        token_symbol: Token ticker symbol.
        token_address: Token contract address.
        amount_usd: Trade value in USD.
        amount_native: Trade amount in native coin.
        tx_hash: Transaction hash.

    Returns:
        Formatted HTML notification string.
    """
    chain_info = CHAIN_INFO.get(chain, {})
    chain_name = chain_info.get("name", chain)
    native = chain_info.get("native", "")
    action_emoji = "🟢 BUY" if action == "BUY" else "🔴 SELL"

    return (
        "📢 <b>NEW WHALE MOVE DETECTED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⛓️  Chain:   {chain_name}\n"
        f"🐋  Whale:   <code>{_truncate(whale_address)}</code> ({whale_label})\n"
        f"📊  Action:  {action_emoji}\n"
        f"🪙  Token:   ${token_symbol} (<code>{_truncate(token_address)}</code>)\n"
        f"💰  Amount:  ${amount_usd:,.2f} ({amount_native:.4f} {native})\n"
        f"🔗  TX:      {_explorer_link(chain, tx_hash)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 Copying trade now..."
    )


def notify_trade_executed(
    action: str,
    token_symbol: str,
    amount_usd: float,
    amount_native: float,
    native_symbol: str,
    tokens_received: float,
    gas_usd: float,
    tx_hash: str,
    chain: str,
    entry_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> str:
    """
    Format a successful copy trade execution notification (HTML).

    Args:
        action: 'BUY' or 'SELL'.
        token_symbol: Token ticker.
        amount_usd: Amount spent/received in USD.
        amount_native: Amount in native coin.
        native_symbol: Native coin symbol (ETH/BNB/SOL).
        tokens_received: Number of tokens received.
        gas_usd: Gas cost in USD.
        tx_hash: Copy transaction hash.
        chain: Chain name.
        entry_price: Token price at entry.
        stop_loss_pct: Active stop loss percentage.
        take_profit_pct: Active take profit percentage.

    Returns:
        Formatted HTML notification string.
    """
    action_emoji = "🟢 BUY" if action == "BUY" else "🔴 SELL"

    return (
        "✅ <b>COPY TRADE EXECUTED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊  Action:  {action_emoji}\n"
        f"🪙  Token:   ${token_symbol}\n"
        f"💰  Spent:   ${amount_usd:,.2f} ({amount_native:.6f} {native_symbol})\n"
        f"🎁  Received: {tokens_received:,.0f} {token_symbol}\n"
        f"⛽  Gas:     ${gas_usd:.2f}\n"
        f"🔗  TX Hash: {_explorer_link(chain, tx_hash)}\n"
        f"📈  Entry Price: ${entry_price:.10f}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Stop Loss at: -{stop_loss_pct:.0f}% | TP at: +{take_profit_pct:.0f}%"
    )


def notify_sl_tp_hit(
    reason: str,
    token_symbol: str,
    entry_price: float,
    exit_price: float,
    pnl_usd: float,
    pnl_pct: float,
) -> str:
    """
    Format a stop-loss / take-profit hit notification (HTML).

    Args:
        reason: 'STOP_LOSS', 'TAKE_PROFIT', or 'TRAILING_STOP'.
        token_symbol: Token ticker.
        entry_price: Entry price.
        exit_price: Exit price.
        pnl_usd: Profit/loss in USD.
        pnl_pct: Profit/loss as percentage.

    Returns:
        Formatted HTML notification string.
    """
    reason_map = {
        "STOP_LOSS": "🔻 STOP LOSS HIT",
        "TAKE_PROFIT": "🔺 TAKE PROFIT HIT",
        "TRAILING_STOP": "📉 TRAILING STOP HIT",
    }
    header = reason_map.get(reason, f"📊 {reason}")
    pnl_emoji = "🟢" if pnl_usd >= 0 else "🔴"

    return (
        f"{header}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙  Token:   ${token_symbol}\n"
        f"📈  Entry:   ${entry_price:.10f}\n"
        f"📉  Exit:    ${exit_price:.10f}\n"
        f"{pnl_emoji}  PnL:     ${pnl_usd:+,.2f} ({pnl_pct:+.1f}%)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )


def notify_daily_report(
    date_str: str,
    total_trades: int,
    wins: int,
    losses: int,
    total_pnl: float,
    best_trade: float,
    worst_trade: float,
    total_gas: float,
    win_rate: float,
) -> str:
    """
    Format a daily summary report notification (HTML).

    Args:
        date_str: Date string (YYYY-MM-DD).
        total_trades: Total trades executed.
        wins: Number of winning trades.
        losses: Number of losing trades.
        total_pnl: Total PnL in USD.
        best_trade: Best single trade PnL.
        worst_trade: Worst single trade PnL.
        total_gas: Total gas spent in USD.
        win_rate: Win rate percentage.

    Returns:
        Formatted HTML notification string.
    """
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"

    return (
        "📊 <b>DAILY REPORT</b>\n"
        f"📅 {date_str}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈  Trades:    {total_trades}\n"
        f"✅  Wins:      {wins}\n"
        f"❌  Losses:    {losses}\n"
        f"🎯  Win Rate:  {win_rate:.1f}%\n"
        f"{pnl_emoji}  Total PnL: ${total_pnl:+,.2f}\n"
        f"🏆  Best:      ${best_trade:+,.2f}\n"
        f"💀  Worst:     ${worst_trade:+,.2f}\n"
        f"⛽  Gas Spent: ${total_gas:.2f}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )


def breakeven_sl_notification(
    token_symbol: str, chain: str, pnl_pct: float, entry_price: float
) -> str:
    """Template for break-even stop loss activation notification."""
    return (
        "🛡️ <b>BREAK-EVEN SL ACTIVATED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: ${token_symbol} ({chain})\n"
        f"📈 Profit reached: +{pnl_pct:.1f}%\n"
        f"🔒 Stop-Loss moved to entry: ${entry_price:.10f}\n\n"
        "Your position is now risk-free! 🎉"
    )


def partial_sell_notification(
    token_symbol: str, chain: str, sell_pct: float,
    target_mult: float, pnl_pct: float, remaining_pct: float,
) -> str:
    """Template for partial take profit execution notification."""
    return (
        "🟡 <b>PARTIAL TAKE PROFIT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: ${token_symbol} ({chain})\n"
        f"📊 Sold: {sell_pct:.0f}% at {target_mult:.1f}x\n"
        f"📈 Current PnL: {pnl_pct:+.1f}%\n"
        f"📦 Remaining: {remaining_pct:.0f}%\n\n"
        "Letting the rest ride! 🚀"
    )


def auto_sell_notification(
    token_symbol: str, chain: str, hours: float, pnl_usd: float, pnl_pct: float,
) -> str:
    """Template for time-based auto-sell notification."""
    pnl_emoji = "🟢" if pnl_usd >= 0 else "🔴"
    return (
        "⏰ <b>AUTO-SELL (TIMEOUT)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: ${token_symbol} ({chain})\n"
        f"⏱️ Held for: {hours:.1f} hours\n"
        f"{pnl_emoji} PnL: ${pnl_usd:+,.2f} ({pnl_pct:+.1f}%)\n\n"
        "Position closed to free up capital."
    )


def sniper_entry_notification(
    token_symbol: str, chain: str, liquidity_usd: float,
    age_minutes: float, amount_usd: float,
) -> str:
    """Template for auto-sniper entry notification."""
    return (
        "🎯 <b>AUTO-SNIPER ENTRY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: ${token_symbol} ({chain})\n"
        f"💧 Liquidity: ${liquidity_usd:,.0f}\n"
        f"⏱️ Pair Age: {age_minutes:.0f} min\n"
        f"💰 Buy Amount: ${amount_usd:.2f}\n\n"
        "New trending token sniped! 🔫"
    )


def kill_switch_notification(closed: int, failed: int) -> str:
    """Template for emergency kill switch notification."""
    return (
        "🚨 <b>KILL SWITCH EXECUTED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Closed: {closed} position(s)\n"
        f"❌ Failed: {failed}\n"
        f"⏹️ Copy trading: STOPPED\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "All positions panic-sold."
    )


def dca_split_notification(
    token_symbol: str, split_num: int, total_splits: int,
    amount_usd: float, remaining_usd: float,
) -> str:
    """Template for DCA split execution notification."""
    return (
        "💰 <b>DCA BUY EXECUTED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: ${token_symbol}\n"
        f"📊 Split: {split_num}/{total_splits}\n"
        f"💵 Amount: ${amount_usd:.2f}\n"
        f"💰 Remaining: ${remaining_usd:.2f}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )


def price_alert_notification(
    token_symbol: str, direction: str, target_price: float,
    current_price: float,
) -> str:
    """Template for price alert trigger notification."""
    dir_emoji = "📈" if direction == "above" else "📉"
    return (
        "🔔 <b>PRICE ALERT TRIGGERED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: ${token_symbol}\n"
        f"{dir_emoji} Direction: {direction.upper()}\n"
        f"🎯 Target: ${target_price:.10g}\n"
        f"💲 Current: ${current_price:.10g}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )


def limit_order_filled_notification(
    token_symbol: str, target_price: float, amount_usd: float,
) -> str:
    """Template for limit order fill notification."""
    return (
        "🎯 <b>LIMIT ORDER FILLED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: ${token_symbol}\n"
        f"💲 Buy Price: ${target_price:.10g}\n"
        f"💰 Amount: ${amount_usd:.2f}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Your limit buy was executed! ✅"
    )


def snooze_resume_notification(chain: str) -> str:
    """Template for snooze auto-resume notification."""
    return (
        "▶️ <b>SNOOZE ENDED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⛓️ Chain: {chain}\n"
        "Copy trading has auto-resumed.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )


def token_audit_warning_notification(
    token_symbol: str, score: int, risks: str
) -> str:
    """Template for token audit warning notification."""
    if score >= 80:
        score_emoji = "🟢"
    elif score >= 50:
        score_emoji = "🟡"
    else:
        score_emoji = "🔴"

    return (
        "🛡️ <b>TOKEN SAFETY CHECK</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 Token: ${token_symbol}\n"
        f"{score_emoji} Score: {score}/100\n"
        f"⚠️ {risks}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

