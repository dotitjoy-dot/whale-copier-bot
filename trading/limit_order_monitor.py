"""
Limit Order Monitor — background service that checks token prices
and fills simulated limit orders when price drops to target.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Dict, List, Optional

import httpx

from core.database import Database
from core.logger import get_logger

logger = get_logger(__name__)

DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"


class LimitOrderMonitor:
    """
    Periodically checks prices for tokens with pending limit orders
    and fills them when price target is met.
    """

    def __init__(
        self,
        db: Database,
        notify_callback: Optional[Callable] = None,
        poll_interval: int = 30,
    ) -> None:
        self._db = db
        self._notify = notify_callback
        self._poll_interval = poll_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the limit order monitor."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Limit Order Monitor started (poll every %ds)", self._poll_interval)

    async def stop(self) -> None:
        """Stop the limit order monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Limit Order Monitor stopped")

    async def _loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._check_orders()
            except Exception as e:
                logger.error("Limit Order Monitor error: %s", e, exc_info=True)
            await asyncio.sleep(self._poll_interval)

    async def _fetch_price(self, token_address: str) -> Optional[float]:
        """Fetch current price from DexScreener."""
        try:
            url = f"{DEXSCREENER_API}/{token_address}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    return float(pairs[0].get("priceUsd", 0))
        except Exception as e:
            logger.debug("Price fetch error: %s", e)
        return None

    async def _check_orders(self) -> None:
        """Check all pending limit orders."""
        orders = await self._db.list_all_pending_limit_orders()
        if not orders:
            return

        # Group by token to minimize API calls
        token_orders: Dict[str, List[dict]] = {}
        for order in orders:
            addr = order["token_address"]
            if addr not in token_orders:
                token_orders[addr] = []
            token_orders[addr].append(order)

        for token_address, order_list in token_orders.items():
            price = await self._fetch_price(token_address)
            if price is None or price <= 0:
                continue

            for order in order_list:
                target = order["target_price"]
                direction = order.get("direction", "buy")

                # For buy limit orders: fill when price drops to/below target
                should_fill = False
                if direction == "buy" and price <= target:
                    should_fill = True

                if should_fill:
                    await self._fill_order(order, price)

            await asyncio.sleep(0.5)

    async def _fill_order(self, order: dict, current_price: float) -> None:
        """Mark order as filled and notify user."""
        await self._db.fill_limit_order(order["id"])

        logger.info(
            "Limit order #%d filled: %s at $%.10g (target: $%.10g)",
            order["id"], order["token_symbol"],
            current_price, order["target_price"],
        )

        # TODO: Integrate with actual swap execution via CopyEngine
        # For now, just mark as filled and notify

        if self._notify:
            from bot.notifications import limit_order_filled_notification
            msg = limit_order_filled_notification(
                token_symbol=order.get("token_symbol") or order["token_address"][:8],
                target_price=order["target_price"],
                amount_usd=order["amount_usd"],
            )
            try:
                await self._notify(order["telegram_id"], msg)
            except Exception:
                pass
