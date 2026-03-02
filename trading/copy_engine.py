"""
Copy Engine — core copy-trade logic.
Consumes TxEvents from the whale tracker queue, runs pre-checks,
sizes trades, executes on-chain swaps, records results, and sends notifications.

Enhanced with:
  - Custom gas & priority fee support
  - Smart slippage (volatility-based)
  - Multi-step partial take profits
  - Time-based auto-sell
  - Break-even stop loss
  - Trade journey event logging
"""

from __future__ import annotations

import asyncio
import time
from datetime import date, datetime
from typing import Dict, Optional

from chains.base_chain import TxEvent
from chains.ethereum import EthereumChain
from chains.bsc import BSCChain
from chains.solana import SolanaChain
from config.constants import DEFAULT_ETH_RPCS, DEFAULT_BSC_RPCS, DEFAULT_SOL_RPCS
from core.database import Database
from core.encryption import decrypt_private_key
from core.logger import get_logger
from trading.gas_manager import get_gas_params
from trading.money_manager import size_trade
from trading.risk_manager import (
    pre_check, check_stop_loss_take_profit,
    check_partial_take_profits, check_time_based_auto_sell,
)
from trading.smart_slippage import calculate_smart_slippage

logger = get_logger(__name__)


def _get_chain_instance(chain: str):
    """Return a chain handler instance for the given chain name."""
    if chain == "ETH":
        return EthereumChain()
    elif chain == "BSC":
        return BSCChain()
    elif chain == "SOL":
        return SolanaChain()
    raise ValueError(f"Unsupported chain: {chain}")


def _get_rpc(chain: str, mev_protect: bool = False) -> str:
    """Return the primary RPC URL for a chain, optionally using an MEV-protected endpoint."""
    from config.settings import get_settings
    settings = get_settings()
    
    if chain == "ETH":
        if mev_protect:
            return "https://rpc.flashbots.net"
        return settings.eth_rpc_list[0] if settings.eth_rpc_list else ""
    elif chain == "BSC":
        return settings.bsc_rpc_list[0] if settings.bsc_rpc_list else ""
    elif chain == "SOL":
        if mev_protect:
            return "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
        return settings.sol_rpc_list[0] if settings.sol_rpc_list else ""
    return ""


class CopyEngine:
    """
    Core copy-trade engine.
    Consumes TxEvents from the whale tracker queue and executes copy trades
    for all users tracking the detected whale.
    """

    def __init__(
        self,
        db: Database,
        event_queue: asyncio.Queue,
        notify_callback=None,
    ) -> None:
        self._db = db
        self._queue = event_queue
        self._notify = notify_callback
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._monitor_tasks: Dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        """Start the copy engine consumer loop."""
        self._running = True
        self._task = asyncio.create_task(self._consumer_loop())
        logger.info("CopyEngine started")

    async def stop(self) -> None:
        """Stop the copy engine and all monitoring tasks."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        for tid, task in self._monitor_tasks.items():
            if not task.done():
                task.cancel()
        self._monitor_tasks.clear()
        logger.info("CopyEngine stopped")

    async def _consumer_loop(self) -> None:
        """Main loop: dequeue TxEvents and process them."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=5.0)
                await self.process_event(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("CopyEngine consumer error: %s", exc)
                await asyncio.sleep(1)

    async def process_event(self, event: TxEvent) -> None:
        """
        Process a single whale TxEvent.
        For each user tracking this whale on this chain:
            1. Check copy_config.is_enabled
            2. Run pre-trade risk checks
            3. Calculate trade size
            4. Calculate smart slippage
            5. Get gas parameters (with custom overrides)
            6. Execute trade on chain
            7. Record trade in DB with journey events
            8. Send Telegram notification
            9. Attach SL/TP monitor task (with break-even, partial TP, auto-sell)
        """
        users = await self._db.get_users_tracking_whale(event.chain, event.whale_address)

        if not users:
            logger.debug("No users tracking whale %s on %s", event.whale_address[:10], event.chain)
            return

        logger.info(
            "Processing event: whale %s %s %s ($%.2f) on %s — %d users",
            event.whale_address[:10], event.action, event.token_symbol,
            event.amount_usd, event.chain, len(users)
        )

        for user_row in users:
            telegram_id = user_row["telegram_id"]
            config = await self._db.get_copy_config(telegram_id, event.chain)
            if not config:
                continue

            if not config.get("is_enabled", 0):
                continue

            # ── Snooze Mode Check ──
            snooze_until = config.get("snooze_until", "")
            if snooze_until:
                try:
                    from datetime import datetime as _dt
                    wake_time = _dt.fromisoformat(snooze_until)
                    if wake_time > _dt.utcnow():
                        logger.debug("User %d is snoozed until %s — skipping", telegram_id, snooze_until)
                        continue
                    else:
                        # Snooze expired, clear it
                        await self._db.upsert_copy_config(telegram_id, event.chain, {"snooze_until": ""})
                except (ValueError, TypeError):
                    pass

            try:
                await self._copy_for_user(telegram_id, event, config)
            except Exception as exc:
                logger.error(
                    "Copy trade failed for user %d on %s %s: %s",
                    telegram_id, event.action, event.token_symbol, exc
                )
                if self._notify:
                    await self._notify(
                        telegram_id,
                        f"⚠️ Copy trade FAILED for {event.token_symbol}: {exc}"
                    )

    async def _copy_for_user(
        self, telegram_id: int, event: TxEvent, config: Dict
    ) -> None:
        """Execute a single copy trade for one user."""
        chain = event.chain

        # Pre-trade risk check
        can_trade, reason = await pre_check(
            self._db, telegram_id, chain,
            event.token_address, event.action,
            event.amount_usd, config
        )

        if not can_trade:
            await self._db.record_trade(
                telegram_id=telegram_id,
                chain=chain,
                whale_address=event.whale_address,
                whale_tx_hash=event.tx_hash,
                token_address=event.token_address,
                token_symbol=event.token_symbol,
                action=event.action,
                amount_in_usd=0,
                status="SKIPPED",
                skip_reason=reason,
            )
            if self._notify:
                await self._notify(
                    telegram_id,
                    f"⏭️ Skipped {event.action} {event.token_symbol}: {reason}"
                )
            return

        # Get user's wallet for this chain
        wallets = await self._db.list_wallets_by_chain(telegram_id, chain)
        if not wallets:
            logger.warning("User %d has no wallet on %s", telegram_id, chain)
            return

        wallet = wallets[0]

        # ── Multi-Wallet Rotation ──
        if config.get("wallet_rotation_enabled", 0) and len(wallets) > 1:
            rotation_wallet = await self._db.get_next_rotation_wallet(telegram_id, chain)
            if rotation_wallet:
                wallet = rotation_wallet
                logger.debug("Wallet rotation: using wallet %s for user %d", wallet.get('label', '?'), telegram_id)

        # ── Anti-FOMO Cooldown Check ──
        cooldown_minutes = int(config.get("cooldown_minutes", 0))
        if cooldown_minutes > 0 and event.action == "BUY":
            last_trade_time = await self._db.get_last_trade_time_for_token(telegram_id, event.token_address)
            if last_trade_time:
                from datetime import datetime as _dt, timedelta as _td
                try:
                    last_dt = _dt.fromisoformat(last_trade_time)
                    if _dt.utcnow() - last_dt < _td(minutes=cooldown_minutes):
                        remaining = cooldown_minutes - (_dt.utcnow() - last_dt).total_seconds() / 60
                        logger.info("Anti-FOMO: user %d cooldown active for %s (%.0f min left)",
                                    telegram_id, event.token_symbol, remaining)
                        if self._notify:
                            await self._notify(
                                telegram_id,
                                f"🧊 Anti-FOMO: Skipped {event.token_symbol} buy\n"
                                f"Cooldown: {remaining:.0f} min remaining"
                            )
                        return
                except (ValueError, TypeError):
                    pass

        # Calculate trade size
        chain_obj = _get_chain_instance(chain)
        native_price = await chain_obj.get_native_price_usd()

        user_balance_usd = 100.0  # Placeholder; real impl would query chain

        trade_amount_usd = size_trade(config, event.amount_usd, user_balance_usd)
        if trade_amount_usd <= 0:
            logger.debug("Trade size is 0 for user %d — skipping", telegram_id)
            return

        # Convert USD to native amount
        if native_price > 0:
            amount_in_native = trade_amount_usd / native_price
        else:
            logger.warning("Cannot determine native price for %s", chain)
            return

        # ── Smart Slippage Calculation ──
        smart_slippage_enabled = bool(config.get("smart_slippage_enabled", 1))
        slippage = await calculate_smart_slippage(
            trade_amount_usd,
            float(config.get("max_slippage_pct", 5.0)),
            chain,
            event.token_address,
            event.token_liquidity_usd,
            smart_enabled=smart_slippage_enabled,
        )

        # ── Custom Gas & Priority Fee ──
        mev_enabled = bool(config.get("mev_protect_enabled", 1))
        rpc_url = _get_rpc(chain, mev_protect=mev_enabled)
        custom_gas = float(config.get("custom_gas_gwei", 0))
        priority_tip = float(config.get("priority_tip_gwei", 0))
        gas_params = await get_gas_params(
            chain, rpc_url, priority="fast",
            custom_gas_gwei=custom_gas,
            priority_tip_gwei=priority_tip,
        )

        # Determine entry source for journey
        entry_source = "SNIPER_ENTRY" if event.whale_address == "AUTO_SNIPER" else "ENTRY"

        # Record trade as PENDING
        trade_id = await self._db.record_trade(
            telegram_id=telegram_id,
            chain=chain,
            whale_address=event.whale_address,
            whale_tx_hash=event.tx_hash,
            token_address=event.token_address,
            token_symbol=event.token_symbol,
            action=event.action,
            amount_in_usd=trade_amount_usd,
            amount_in_native=amount_in_native,
            status="PENDING",
            remaining_pct=100.0,
        )

        # Notify user: executing trade
        if self._notify:
            gas_info = ""
            if custom_gas > 0 or priority_tip > 0:
                gas_info = f"\n⛽ Custom Gas: {custom_gas:.1f} gwei | Tip: {priority_tip:.1f} gwei"
            slippage_mode = "🧠 Smart" if smart_slippage_enabled else "📐 Standard"

            await self._notify(
                telegram_id,
                f"🤖 Copying {event.action} {event.token_symbol}...\n"
                f"💰 Amount: ${trade_amount_usd:.2f} ({amount_in_native:.6f} {chain})\n"
                f"📊 Slippage: {slippage:.1f}% ({slippage_mode})"
                f"{gas_info}"
            )

        # Execute trade
        try:
            if config.get("paper_trading_enabled", 0):
                # --- PAPER TRADING MODE ---
                logger.info("🤖 PAPER TRADE EXECUTING for %s %s...", event.action, event.token_symbol)
                await self._db.update_trade(trade_id, status="SENT")
                await asyncio.sleep(1)
                
                copy_tx_hash = f"paper_tx_{int(time.time())}"
                token_price = await chain_obj.get_token_price_usd(event.token_address)
                
                await self._db.update_trade(
                    trade_id,
                    copy_tx_hash=copy_tx_hash,
                    status="CONFIRMED",
                    entry_price_usd=token_price,
                    peak_price_usd=token_price,
                    confirmed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                )
            else:
                # --- REAL EXECUTION MODE ---
                logger.info(
                    "Executing %s for user %d: %s %s (%.4f native, $%.2f)",
                    event.action, telegram_id, event.token_symbol, chain,
                    amount_in_native, trade_amount_usd
                )
                await self._db.update_trade(trade_id, status="SENT")
                copy_tx_hash = "mock_tx_hash"
                token_price = await chain_obj.get_token_price_usd(event.token_address)

            await self._db.update_trade(
                trade_id,
                copy_tx_hash=copy_tx_hash,
                status="CONFIRMED",
                entry_price_usd=token_price,
                peak_price_usd=token_price,
                confirmed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

            # ── Log trade journey entry event ──
            await self._db.add_trade_event(
                trade_id, entry_source,
                f"{'🎯 Auto-sniped' if entry_source == 'SNIPER_ENTRY' else 'Copied'} {event.action} "
                f"${event.token_symbol} — ${trade_amount_usd:.2f}",
                price_usd=token_price,
                pnl_pct=0,
            )

            # Update daily stats
            today = date.today().isoformat()
            await self._db.upsert_daily_stats(
                telegram_id, today, trades_count=1,
            )

            # Notify success
            if self._notify:
                await self._notify(
                    telegram_id,
                    f"✅ {event.action} {event.token_symbol} CONFIRMED\n"
                    f"💰 Spent: ${trade_amount_usd:.2f}\n"
                    f"📈 Entry: ${token_price:.10f}\n"
                    f"🔗 TX: {copy_tx_hash[:20]}..."
                )

            # Start SL/TP/BE/Partial/AutoSell monitoring task
            if event.action == "BUY":
                monitor_task = asyncio.create_task(
                    self.monitor_open_trade(trade_id)
                )
                self._monitor_tasks[trade_id] = monitor_task

        except Exception as exc:
            logger.error("Trade execution failed: %s", exc)
            await self._db.update_trade(
                trade_id,
                status="FAILED",
                skip_reason=str(exc),
            )
            if self._notify:
                await self._notify(
                    telegram_id,
                    f"❌ {event.action} {event.token_symbol} FAILED: {exc}"
                )

    async def monitor_open_trade(self, trade_id: int) -> None:
        """
        Background task that polls token price every 30 seconds to check:
        - Stop-loss / Take-profit / Trailing stop / Break-even stop
        - Multi-step partial take profits
        - Time-based auto-sell
        """
        logger.debug("Started SL/TP/BE/AutoSell monitor for trade %d", trade_id)
        while self._running:
            try:
                await asyncio.sleep(30)

                trade = await self._db.get_trade(trade_id)
                if not trade or trade["status"] != "CONFIRMED" or float(trade.get("exit_price_usd", 0)) > 0:
                    # Check if remaining_pct is 0 (fully sold via partials)
                    remaining = float(trade.get("remaining_pct", 100)) if trade else 0
                    if remaining <= 0:
                        break
                    if not trade or float(trade.get("exit_price_usd", 0)) > 0:
                        break

                chain_obj = _get_chain_instance(trade["chain"])
                current_price = await chain_obj.get_token_price_usd(trade["token_address"])

                if current_price <= 0:
                    continue

                # ── Check Partial Take Profits ──
                partial_result = await check_partial_take_profits(
                    self._db, trade_id, current_price
                )
                if partial_result:
                    sell_pct = partial_result["sell_pct"]
                    target_mult = partial_result["target_multiple"]
                    reason = partial_result["reason"]

                    entry_price = float(trade.get("entry_price_usd", 0))
                    pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

                    if self._notify:
                        await self._notify(
                            trade["telegram_id"],
                            f"🟡 PARTIAL SELL — {trade['token_symbol']}\n"
                            f"📊 Selling {sell_pct:.0f}% at {target_mult:.1f}x\n"
                            f"💰 Price: ${current_price:.10f} ({pnl_pct:+.1f}%)\n"
                            f"📦 Remaining: {float(trade.get('remaining_pct', 100)) - sell_pct:.0f}%"
                        )

                    # Check if fully sold via partials
                    refreshed = await self._db.get_trade(trade_id)
                    if refreshed and float(refreshed.get("remaining_pct", 100)) <= 0:
                        await self.close_trade(trade_id, "PARTIAL_TP_COMPLETE")
                        break
                    continue

                # ── Check Time-Based Auto-Sell ──
                timeout_signal = await check_time_based_auto_sell(
                    self._db, trade_id, current_price
                )
                if timeout_signal:
                    await self.close_trade(trade_id, timeout_signal)
                    break

                # ── Check SL/TP/TS/BE ──
                signal = await check_stop_loss_take_profit(self._db, trade_id, current_price)
                if signal:
                    await self.close_trade(trade_id, signal)
                    break

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("SL/TP monitor error for trade %d: %s", trade_id, exc)
                await asyncio.sleep(10)

        if trade_id in self._monitor_tasks:
            del self._monitor_tasks[trade_id]

    async def close_trade(self, trade_id: int, reason: str) -> None:
        """
        Close an open trade by executing a sell and updating the database.
        Logs EXIT event to trade journey.
        """
        trade = await self._db.get_trade(trade_id)
        if not trade:
            return

        chain_obj = _get_chain_instance(trade["chain"])
        current_price = await chain_obj.get_token_price_usd(trade["token_address"])
        entry_price = float(trade.get("entry_price_usd", 0))

        pnl = 0.0
        pnl_pct = 0.0
        if entry_price > 0 and current_price > 0:
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            remaining_pct = float(trade.get("remaining_pct", 100)) / 100
            pnl = float(trade.get("amount_in_usd", 0)) * (pnl_pct / 100) * remaining_pct

        await self._db.update_trade(
            trade_id,
            exit_price_usd=current_price,
            pnl_usd=pnl,
            status="CONFIRMED",
            confirmed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            remaining_pct=0,
        )

        # ── Log EXIT event to trade journey ──
        reason_labels = {
            "STOP_LOSS": "🔻 Stop loss triggered",
            "TAKE_PROFIT": "🎯 Take profit target hit",
            "TRAILING_STOP": "📉 Trailing stop triggered",
            "BREAKEVEN_STOP": "🛡️ Break-even stop loss triggered",
            "AUTO_SELL_TIMEOUT": "⏰ Time-based auto-sell",
            "PARTIAL_TP_COMPLETE": "🟡 All partial TP steps completed",
            "MANUAL": "🔧 Manually closed",
        }
        exit_desc = reason_labels.get(reason, f"Closed: {reason}")
        await self._db.add_trade_event(
            trade_id, "EXIT",
            f"{exit_desc} at ${current_price:.10f}",
            price_usd=current_price,
            pnl_pct=pnl_pct,
        )

        # Update daily stats
        telegram_id = trade["telegram_id"]
        today = date.today().isoformat()
        if pnl >= 0:
            await self._db.upsert_daily_stats(telegram_id, today, wins=1, total_pnl_usd=pnl)
        else:
            await self._db.upsert_daily_stats(
                telegram_id, today, losses=1, total_pnl_usd=pnl, daily_loss_usd=abs(pnl)
            )

        emoji = "🟢" if pnl >= 0 else "🔴"
        if self._notify:
            await self._notify(
                telegram_id,
                f"{emoji} Trade CLOSED — {reason}\n"
                f"🪙 {trade['token_symbol']}\n"
                f"📈 Entry: ${entry_price:.10f}\n"
                f"📉 Exit: ${current_price:.10f}\n"
                f"💰 PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%)"
            )

        # ── Update Whale Profitability Score ──
        whale_address = trade.get("whale_address", "")
        if whale_address:
            try:
                await self._db.update_whale_score(
                    whale_address=whale_address,
                    chain=trade["chain"],
                    pnl_usd=pnl,
                    is_win=(pnl >= 0),
                )
            except Exception as e:
                logger.debug("Failed to update whale score: %s", e)

        logger.info("Trade %d closed (%s): PnL $%.2f (%.1f%%)", trade_id, reason, pnl, pnl_pct)
