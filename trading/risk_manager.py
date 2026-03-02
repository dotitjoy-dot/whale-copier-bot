"""
Risk Manager — pre-trade checks, stop-loss/take-profit monitoring,
break-even stop loss, multi-step partial take profits, and time-based auto-sell.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from core.database import Database
from core.logger import get_logger

logger = get_logger(__name__)


async def check_honeypot(token_address: str, chain: str) -> bool:
    """
    Mock integration for GoPlus Security / TokenSniffer API.
    Returns True if the token is a honeypot, False if safe.
    """
    if "bad" in token_address.lower():
        return True
    return False


async def pre_check(
    db: Database,
    telegram_id: int,
    chain: str,
    token_address: str,
    action: str,
    amount_usd: float,
    config: Dict,
) -> Tuple[bool, str]:
    """
    Perform all pre-trade risk checks before executing a copy trade.

    Checks (in order):
        1. Daily loss limit not exceeded.
        2. Max open trades not exceeded.
        3. Token not blacklisted by user.
        4. Anti-Rug / Honeypot Check.
        5. Whale trade USD >= config.min_whale_trade_usd.
        6. Action is allowed (copy_buys / copy_sells flags).

    Returns:
        Tuple of (can_trade: bool, reason: str).
    """
    # 1. Daily loss limit
    today = date.today().isoformat()
    daily = await db.get_daily_stats(telegram_id, today)
    if daily:
        daily_loss = float(daily.get("daily_loss_usd", 0))
        limit = float(config.get("daily_loss_limit_usd", 50.0))
        if daily_loss >= limit:
            reason = f"Daily loss limit reached (${daily_loss:.2f} / ${limit:.2f})"
            logger.info("Pre-check BLOCKED for user %d: %s", telegram_id, reason)
            return False, reason

    # 2. Max open trades
    open_trades = await db.count_open_trades(telegram_id, chain)
    max_open = int(config.get("max_open_trades", 5))
    if open_trades >= max_open:
        reason = f"Max open trades reached ({open_trades}/{max_open})"
        logger.info("Pre-check BLOCKED for user %d: %s", telegram_id, reason)
        return False, reason

    # 3. Blacklist check
    is_blocked = await db.is_blacklisted(telegram_id, token_address)
    if is_blocked:
        reason = f"Token {token_address[:10]}... is blacklisted"
        logger.info("Pre-check BLOCKED for user %d: %s", telegram_id, reason)
        return False, reason

    # 3.5 Anti-Rug / Honeypot Check
    if config.get("anti_rug_enabled", 1):
        is_honeypot = await check_honeypot(token_address, chain)
        if is_honeypot:
            reason = f"🛡️ Anti-Rug protection triggered for {token_address[:10]}..."
            logger.warning("Pre-check BLOCKED for user %d: %s", telegram_id, reason)
            return False, reason

    # 4. Minimum whale trade size
    min_whale_usd = float(config.get("min_whale_trade_usd", 500.0))
    if amount_usd < min_whale_usd:
        reason = f"Whale trade ${amount_usd:.2f} below minimum ${min_whale_usd:.2f}"
        logger.debug("Pre-check SKIP for user %d: %s", telegram_id, reason)
        return False, reason

    # 5. Action allowed
    if action == "BUY" and not config.get("copy_buys", 1):
        reason = "Copy buys is disabled"
        logger.debug("Pre-check SKIP for user %d: %s", telegram_id, reason)
        return False, reason

    if action == "SELL" and not config.get("copy_sells", 1):
        reason = "Copy sells is disabled"
        logger.debug("Pre-check SKIP for user %d: %s", telegram_id, reason)
        return False, reason

    logger.debug("Pre-check PASSED for user %d on %s %s", telegram_id, action, chain)
    return True, ""


async def check_stop_loss_take_profit(
    db: Database,
    trade_id: int,
    current_price_usd: float,
) -> Optional[str]:
    """
    Check if a trade has hit stop-loss, take-profit, trailing stop,
    or break-even stop loss levels.

    Returns:
        'STOP_LOSS' | 'TAKE_PROFIT' | 'TRAILING_STOP' | 'BREAKEVEN_STOP' | None
    """
    trade = await db.get_trade(trade_id)
    if not trade:
        return None

    entry_price = float(trade.get("entry_price_usd", 0))
    if entry_price <= 0 or current_price_usd <= 0:
        return None

    telegram_id = trade["telegram_id"]
    chain = trade["chain"]

    config = await db.get_copy_config(telegram_id, chain)
    if not config:
        return None

    pnl_pct = ((current_price_usd - entry_price) / entry_price) * 100

    # ── Track Peak Price for Trailing Stop ──
    peak_price = float(trade.get("peak_price_usd", 0))
    if current_price_usd > peak_price:
        await db.update_trade(trade_id, peak_price_usd=current_price_usd)
        peak_price = current_price_usd

    # ── Break-Even Stop Loss ──
    breakeven_enabled = bool(config.get("breakeven_enabled", 0))
    breakeven_trigger = float(config.get("breakeven_trigger_pct", 50.0))
    breakeven_activated = bool(trade.get("breakeven_activated", 0))

    if breakeven_enabled and not breakeven_activated and pnl_pct >= breakeven_trigger:
        # Activate break-even SL — move SL to entry price
        await db.update_trade(trade_id, breakeven_activated=1)
        await db.add_trade_event(
            trade_id, "BREAKEVEN_SL",
            f"Break-even SL activated at +{pnl_pct:.1f}% — SL moved to entry ${entry_price:.10f}",
            price_usd=current_price_usd,
            pnl_pct=pnl_pct,
        )
        logger.info(
            "Trade %d: Break-even SL activated at +%.1f%% — SL now at entry $%.10f",
            trade_id, pnl_pct, entry_price,
        )
        breakeven_activated = True

    # ── Stop Loss (with break-even awareness) ──
    sl_pct = float(config.get("stop_loss_pct", 20.0))
    if breakeven_activated:
        # Break-even SL: sell if price drops back to entry or below
        if current_price_usd <= entry_price:
            logger.info("Trade %d hit BREAKEVEN STOP at %.1f%%", trade_id, pnl_pct)
            await db.add_trade_event(
                trade_id, "STOP_LOSS_HIT",
                f"Break-even stop loss triggered at ${current_price_usd:.10f}",
                price_usd=current_price_usd,
                pnl_pct=pnl_pct,
            )
            return "BREAKEVEN_STOP"
    elif sl_pct > 0 and pnl_pct <= -sl_pct:
        logger.info("Trade %d hit STOP LOSS at %.1f%%", trade_id, pnl_pct)
        await db.add_trade_event(
            trade_id, "STOP_LOSS_HIT",
            f"Stop loss triggered at -{sl_pct:.0f}%",
            price_usd=current_price_usd,
            pnl_pct=pnl_pct,
        )
        return "STOP_LOSS"

    # ── Take Profit ──
    tp_pct = float(config.get("take_profit_pct", 50.0))
    if tp_pct > 0 and pnl_pct >= tp_pct:
        logger.info("Trade %d hit TAKE PROFIT at %.1f%%", trade_id, pnl_pct)
        await db.add_trade_event(
            trade_id, "TAKE_PROFIT_HIT",
            f"Take profit triggered at +{tp_pct:.0f}%",
            price_usd=current_price_usd,
            pnl_pct=pnl_pct,
        )
        return "TAKE_PROFIT"

    # ── Trailing Stop (uses tracked peak price) ──
    trailing_pct = float(config.get("trailing_stop_pct", 0.0))
    if trailing_pct > 0 and peak_price > entry_price:
        drawdown_from_peak = ((peak_price - current_price_usd) / peak_price) * 100
        if drawdown_from_peak >= trailing_pct:
            logger.info(
                "Trade %d hit TRAILING STOP: peak=$%.10f, current=$%.10f, drawdown=%.1f%%",
                trade_id, peak_price, current_price_usd, drawdown_from_peak,
            )
            await db.add_trade_event(
                trade_id, "TRAILING_STOP_HIT",
                f"Trailing stop triggered — {drawdown_from_peak:.1f}% drawdown from peak",
                price_usd=current_price_usd,
                pnl_pct=pnl_pct,
            )
            return "TRAILING_STOP"

    return None


async def check_partial_take_profits(
    db: Database,
    trade_id: int,
    current_price_usd: float,
) -> Optional[Dict]:
    """
    Check if a trade should trigger a partial take profit step.

    Returns:
        Dict with 'sell_pct' and 'reason' if partial TP triggered, None otherwise.
    """
    trade = await db.get_trade(trade_id)
    if not trade:
        return None

    entry_price = float(trade.get("entry_price_usd", 0))
    remaining_pct = float(trade.get("remaining_pct", 100))
    if entry_price <= 0 or current_price_usd <= 0 or remaining_pct <= 0:
        return None

    telegram_id = trade["telegram_id"]
    chain = trade["chain"]

    config = await db.get_copy_config(telegram_id, chain)
    if not config or not config.get("partial_tp_enabled", 0):
        return None

    # Current price multiple vs entry
    price_multiple = current_price_usd / entry_price

    # Get partial TP steps
    steps = await db.get_partial_take_profits(telegram_id, chain)
    if not steps:
        return None

    # Check from highest to lowest target to respect priority
    for step in sorted(steps, key=lambda s: s["target_multiple"], reverse=True):
        target_mult = float(step["target_multiple"])
        sell_pct = float(step["sell_pct"])

        # Check if we've reached this target
        if price_multiple >= target_mult:
            # Check if we already executed this step by looking at trade events
            events = await db.get_trade_events(trade_id)
            step_key = f"PARTIAL_{target_mult:.1f}x"
            already_executed = any(
                e.get("event_type") == "PARTIAL_SELL" and step_key in e.get("description", "")
                for e in events
            )

            if not already_executed and remaining_pct > 0:
                actual_sell_pct = min(sell_pct, remaining_pct)
                if actual_sell_pct <= 0:
                    continue

                logger.info(
                    "Trade %d: Partial TP triggered at %.1fx — selling %.0f%% of remaining %.0f%%",
                    trade_id, target_mult, sell_pct, remaining_pct,
                )

                # Update remaining percentage
                new_remaining = remaining_pct - actual_sell_pct
                await db.update_trade(trade_id, remaining_pct=new_remaining)

                pnl_pct = (price_multiple - 1) * 100
                await db.add_trade_event(
                    trade_id, "PARTIAL_SELL",
                    f"Partial sell {actual_sell_pct:.0f}% at {target_mult:.1f}x (PARTIAL_{target_mult:.1f}x)",
                    price_usd=current_price_usd,
                    pnl_pct=pnl_pct,
                )

                return {
                    "sell_pct": actual_sell_pct,
                    "target_multiple": target_mult,
                    "reason": f"PARTIAL_TP_{target_mult:.0f}x",
                }

    return None


async def check_time_based_auto_sell(
    db: Database,
    trade_id: int,
    current_price_usd: float,
) -> Optional[str]:
    """
    Check if a trade should be auto-sold due to time expiration.
    If the trade has been open for longer than auto_sell_hours and
    hasn't hit its take profit target, trigger an auto-sell.

    Returns:
        'AUTO_SELL_TIMEOUT' if timeout reached, None otherwise.
    """
    trade = await db.get_trade(trade_id)
    if not trade:
        return None

    telegram_id = trade["telegram_id"]
    chain = trade["chain"]

    config = await db.get_copy_config(telegram_id, chain)
    if not config:
        return None

    auto_sell_hours = float(config.get("auto_sell_hours", 0))
    if auto_sell_hours <= 0:
        return None

    # Parse trade creation time
    created_str = trade.get("created_at", "")
    if not created_str:
        return None

    try:
        created_dt = datetime.fromisoformat(created_str)
        elapsed_hours = (datetime.utcnow() - created_dt).total_seconds() / 3600
    except (ValueError, TypeError):
        return None

    if elapsed_hours >= auto_sell_hours:
        entry_price = float(trade.get("entry_price_usd", 0))
        pnl_pct = ((current_price_usd - entry_price) / entry_price * 100) if entry_price > 0 else 0

        logger.info(
            "Trade %d: Auto-sell timeout after %.1f hours (limit: %.1f hours). PnL: %.1f%%",
            trade_id, elapsed_hours, auto_sell_hours, pnl_pct,
        )

        await db.add_trade_event(
            trade_id, "AUTO_SELL_TIMEOUT",
            f"Auto-sell triggered after {elapsed_hours:.1f} hours (limit: {auto_sell_hours:.0f}h)",
            price_usd=current_price_usd,
            pnl_pct=pnl_pct,
        )

        return "AUTO_SELL_TIMEOUT"

    return None
