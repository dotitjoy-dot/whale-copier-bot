"""
DCA Executor — background service that periodically checks and executes
pending DCA (Dollar Cost Average) order splits.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Optional

from core.database import Database
from core.logger import get_logger

logger = get_logger(__name__)


class DCAExecutor:
    """
    Periodically scans active DCA orders and executes the next split
    if enough time has elapsed since the last split.
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
        """Start the DCA executor loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("DCA Executor started (poll every %ds)", self._poll_interval)

    async def stop(self) -> None:
        """Stop the DCA executor loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DCA Executor stopped")

    async def _loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._process_pending_orders()
            except Exception as e:
                logger.error("DCA Executor error: %s", e, exc_info=True)
            await asyncio.sleep(self._poll_interval)

    async def _process_pending_orders(self) -> None:
        """Check all active DCA orders and execute ready splits."""
        orders = await self._db.list_active_dca_orders()
        now = datetime.utcnow()

        for order in orders:
            try:
                await self._check_and_execute(order, now)
            except Exception as e:
                logger.error("DCA order #%d error: %s", order["id"], e)

    async def _check_and_execute(self, order: dict, now: datetime) -> None:
        """Check if a single DCA order is ready for the next split."""
        created = datetime.fromisoformat(order["created_at"])
        executed = order["executed_splits"]
        total = order["num_splits"]
        interval_min = order["interval_minutes"]

        if executed >= total:
            await self._db.update_dca_order(order["id"], status="COMPLETED")
            logger.info("DCA order #%d completed all %d splits", order["id"], total)
            return

        # Calculate when the next split should execute
        next_split_time = created + timedelta(minutes=interval_min * (executed + 1))

        if now < next_split_time:
            return  # Not time yet

        # Execute the split
        amount = order["amount_per_split"]
        token = order["token_address"]
        symbol = order["token_symbol"]
        chain = order["chain"]
        user_id = order["telegram_id"]

        logger.info(
            "DCA order #%d: executing split %d/%d — $%.2f of %s on %s",
            order["id"], executed + 1, total, amount, symbol, chain,
        )

        # TODO: Integrate with actual swap execution via CopyEngine
        # For now, record the split and notify

        new_executed = executed + 1
        update_fields = {"executed_splits": new_executed}
        if new_executed >= total:
            update_fields["status"] = "COMPLETED"

        await self._db.update_dca_order(order["id"], **update_fields)

        # Notify user
        if self._notify:
            remaining_usd = (total - new_executed) * amount
            from bot.notifications import dca_split_notification
            msg = dca_split_notification(symbol, new_executed, total, amount, remaining_usd)
            try:
                await self._notify(user_id, msg)
            except Exception:
                pass

        logger.info(
            "DCA order #%d: split %d/%d executed ($%.2f)",
            order["id"], new_executed, total, amount,
        )
