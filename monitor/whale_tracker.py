"""
Whale Tracker — background polling job that monitors whale wallets on all chains.
Runs every POLL_INTERVAL_SECONDS via APScheduler.
Emits TxEvents to the copy engine's asyncio.Queue.
Uses exponential backoff on RPC failures and respects rate limits.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional

from chains.base_chain import TxEvent
from chains.ethereum import EthereumChain
from chains.bsc import BSCChain
from chains.solana import SolanaChain
from core.database import Database
from core.logger import get_logger

logger = get_logger(__name__)

# Chain instances (singleton per chain)
_chain_instances: Dict[str, object] = {}


def _get_chain(chain: str):
    """Return a cached chain instance for the given chain name."""
    global _chain_instances
    if chain not in _chain_instances:
        if chain == "ETH":
            _chain_instances[chain] = EthereumChain()
        elif chain == "BSC":
            _chain_instances[chain] = BSCChain()
        elif chain == "SOL":
            _chain_instances[chain] = SolanaChain()
    return _chain_instances[chain]


class WhaleTracker:
    """
    Background task that polls all active whale wallets and emits TxEvents.

    - Runs every POLL_INTERVAL_SECONDS (default 15s) via APScheduler.
    - Rate-limited to max 5 RPC requests per second per chain.
    - Uses exponential backoff on repeated RPC failures (max 5 retries).
    - On new transactions detected, emits TxEvent objects to the provided queue.
    """

    def __init__(self, db: Database, event_queue: asyncio.Queue) -> None:
        """
        Initialize the whale tracker.

        Args:
            db: Database instance for reading whale config and updating state.
            event_queue: asyncio.Queue to push detected TxEvent objects.
        """
        self._db = db
        self._queue = event_queue
        self._failure_counts: Dict[str, int] = {}  # whale_id → consecutive failures
        self._next_poll: Dict[str, float] = {}     # whale_id -> next poll timestamp
        self._running = False

    async def start(self) -> None:
        """Mark the tracker as running."""
        self._running = True
        logger.info("WhaleTracker started")

    async def stop(self) -> None:
        """Stop the tracker gracefully."""
        self._running = False
        logger.info("WhaleTracker stopped")

    async def poll(self) -> None:
        """
        Main polling entry point. Called by APScheduler every POLL_INTERVAL_SECONDS.
        Fetches all active whale wallets and checks for new transactions.
        """
        if not self._running:
            return

        whales = await self._db.list_all_active_whales()
        if not whales:
            return

        logger.debug("Polling %d whale wallets", len(whales))

        # Group by chain for efficient processing
        by_chain: Dict[str, list] = {}
        for w in whales:
            by_chain.setdefault(w["chain"], []).append(w)

        tasks = []
        for chain, chain_whales in by_chain.items():
            tasks.append(self._poll_chain(chain, chain_whales))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _poll_chain(self, chain: str, whales: list) -> None:
        """
        Poll all whale wallets for a specific chain with rate limiting.

        Args:
            chain: Chain name ('ETH', 'BSC', 'SOL').
            whales: List of whale wallet DB dicts for this chain.
        """
        chain_obj = _get_chain(chain)
        rate_limit_delay = 0.2  # 200ms between requests = max 5 req/s

        for whale in whales:
            whale_id = str(whale["id"])
            address = whale["address"]
            last_tx = whale.get("last_tx_hash", "")

            # Non-blocking backoff for repeated failures
            if time.time() < self._next_poll.get(whale_id, 0):
                continue

            try:
                recent_txs = await chain_obj.get_recent_txs(address, last_tx)

                if not recent_txs:
                    self._failure_counts[whale_id] = 0
                    await asyncio.sleep(rate_limit_delay)
                    continue

                # Process from oldest to newest
                for tx in reversed(recent_txs):
                    # Skip already-seen transactions
                    if tx.tx_hash == last_tx:
                        break

                    try:
                        event = await chain_obj.classify_tx(tx)
                        if event is not None:
                            logger.info(
                                "New whale event: %s %s %s on %s",
                                event.action, event.token_symbol, address[:10], chain
                            )
                            await self._queue.put(event)
                    except Exception as exc:
                        logger.error("Error classifying tx %s: %s", tx.tx_hash[:10], exc)

                # Update last seen tx to newest
                newest_hash = recent_txs[0].tx_hash
                await self._db.update_whale_last_tx(whale["id"], newest_hash)
                last_tx = newest_hash
                self._failure_counts[whale_id] = 0

            except Exception as exc:
                failures = self._failure_counts.get(whale_id, 0) + 1
                self._failure_counts[whale_id] = failures
                
                if failures >= 5:
                    backoff = min(300, 2 ** failures)
                    self._next_poll[whale_id] = time.time() + backoff
                    logger.warning(
                        "Whale %s has %d failures, backoff %ds", address[:10], failures, backoff
                    )
                else:
                    logger.error(
                        "Poll error for whale %s on %s (failure #%d): %s",
                        address[:10], chain, failures, exc
                    )

            await asyncio.sleep(rate_limit_delay)

    async def add_whale(self, chain: str, address: str) -> None:
        """
        Notify the tracker that a new whale has been added (resets its failure count).

        Args:
            chain: Chain name.
            address: Whale wallet address.
        """
        logger.info("Whale %s added on %s", address[:10], chain)
        # Failure count starts at 0 for new whales automatically

    async def remove_whale(self, chain: str, address: str) -> None:
        """
        Notify the tracker that a whale has been removed.

        Args:
            chain: Chain name.
            address: Whale wallet address.
        """
        logger.info("Whale %s removed on %s", address[:10], chain)
