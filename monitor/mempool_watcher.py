"""
Optional mempool watcher for Ethereum — subscribes to pending transactions
via WebSocket for faster whale detection before block confirmation.
Falls back gracefully if WebSocket is unavailable.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


class MempoolWatcher:
    """
    Optional Ethereum pending transaction watcher using WebSocket subscriptions.
    This supplements the block-polling approach in WhaleTracker for faster detection.
    Requires a WebSocket-capable RPC endpoint (many free nodes support this).
    """

    def __init__(self, ws_url: str = "wss://eth.llamarpc.com") -> None:
        """
        Initialize the mempool watcher.

        Args:
            ws_url: WebSocket RPC URL to subscribe to.
        """
        self._ws_url = ws_url
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, callback) -> None:
        """
        Start listening for pending transactions.

        Args:
            callback: Async callable(tx_hash: str) to invoke on each pending tx.
        """
        self._running = True
        self._task = asyncio.create_task(self._watch(callback))
        logger.info("MempoolWatcher started on %s", self._ws_url[:30])

    async def stop(self) -> None:
        """Stop the mempool watcher task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MempoolWatcher stopped")

    async def _watch(self, callback) -> None:
        """
        Internal WebSocket subscription loop.
        Subscribes to newPendingTransactions and calls callback for each hash.

        Args:
            callback: Async callable to invoke with each tx hash string.
        """
        while self._running:
            try:
                import websockets
                async with websockets.connect(self._ws_url, ping_interval=20) as ws:
                    subscribe_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newPendingTransactions"],
                    }
                    await ws.send(str(subscribe_msg).replace("'", '"'))
                    logger.debug("Subscribed to newPendingTransactions")

                    while self._running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            import json
                            data = json.loads(msg)
                            tx_hash = data.get("params", {}).get("result")
                            if tx_hash:
                                await callback(tx_hash)
                        except asyncio.TimeoutError:
                            continue
                        except Exception as exc:
                            logger.debug("Mempool message error: %s", exc)
                            break

            except Exception as exc:
                logger.warning("MempoolWatcher connection error: %s — retrying in 30s", exc)
                await asyncio.sleep(30)
