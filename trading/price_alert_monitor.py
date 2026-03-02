"""
Price Alert Monitor — background service that checks token prices
against user-defined alert targets and triggers notifications.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Dict, List, Optional

import httpx

from core.database import Database
from core.logger import get_logger

logger = get_logger(__name__)

# DexScreener price API
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"


class PriceAlertMonitor:
    """
    Periodically checks prices for tokens with active alerts and
    fires notifications when targets are hit.
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
        self._price_cache: Dict[str, float] = {}
        self._cache_ttl = 15  # seconds

    async def start(self) -> None:
        """Start the price alert monitor."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Price Alert Monitor started (poll every %ds)", self._poll_interval)

    async def stop(self) -> None:
        """Stop the price alert monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Price Alert Monitor stopped")

    async def _loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._check_alerts()
            except Exception as e:
                logger.error("Price Alert Monitor error: %s", e, exc_info=True)
            await asyncio.sleep(self._poll_interval)

    async def _fetch_price(self, token_address: str) -> Optional[float]:
        """Fetch current price from DexScreener."""
        # Check cache first
        if token_address in self._price_cache:
            return self._price_cache[token_address]

        try:
            url = f"{DEXSCREENER_API}/{token_address}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    price = float(pairs[0].get("priceUsd", 0))
                    self._price_cache[token_address] = price
                    return price
        except Exception as e:
            logger.debug("Price fetch error for %s: %s", token_address[:10], e)
        return None

    async def _check_alerts(self) -> None:
        """Check all active price alerts."""
        alerts = await self._db.list_all_active_price_alerts()
        if not alerts:
            return

        # Group by token to minimize API calls
        token_alerts: Dict[str, List[dict]] = {}
        for alert in alerts:
            addr = alert["token_address"]
            if addr not in token_alerts:
                token_alerts[addr] = []
            token_alerts[addr].append(alert)

        # Clear cache each cycle
        self._price_cache.clear()

        for token_address, alert_list in token_alerts.items():
            price = await self._fetch_price(token_address)
            if price is None or price <= 0:
                continue

            for alert in alert_list:
                triggered = False
                target = alert["target_price"]
                direction = alert["direction"]

                if direction == "above" and price >= target:
                    triggered = True
                elif direction == "below" and price <= target:
                    triggered = True

                if triggered:
                    await self._trigger_alert(alert, price)

            # Small delay between token checks
            await asyncio.sleep(0.5)

    async def _trigger_alert(self, alert: dict, current_price: float) -> None:
        """Mark alert as triggered and notify user."""
        await self._db.trigger_price_alert(alert["id"])

        logger.info(
            "Price alert #%d triggered: %s %s $%.10g (current: $%.10g)",
            alert["id"], alert["direction"], alert["token_symbol"],
            alert["target_price"], current_price,
        )

        if self._notify:
            from bot.notifications import price_alert_notification
            msg = price_alert_notification(
                token_symbol=alert.get("token_symbol") or alert["token_address"][:8],
                direction=alert["direction"],
                target_price=alert["target_price"],
                current_price=current_price,
            )
            try:
                await self._notify(alert["telegram_id"], msg)
            except Exception:
                pass
