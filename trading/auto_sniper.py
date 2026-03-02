"""
Auto-Sniper — polls DEX Screener for trending new token pairs and
auto-buys tokens matching user-configured filters.
Runs as a scheduled job alongside the whale tracker.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Set

import httpx

from core.database import Database
from core.logger import get_logger

logger = get_logger(__name__)

# DEX Screener endpoints
DEXSCREENER_TRENDING_URL = "https://api.dexscreener.com/token-boosts/top/v1"
DEXSCREENER_LATEST_URL = "https://api.dexscreener.com/token-profiles/latest/v1"

# Chain ID mapping for DEX Screener
_CHAIN_MAP = {
    "ethereum": "ETH",
    "bsc": "BSC",
    "solana": "SOL",
}

_REVERSE_CHAIN_MAP = {v: k for k, v in _CHAIN_MAP.items()}


class AutoSniper:
    """
    Auto-Sniper that polls DEX Screener trending/new token lists and
    auto-buys tokens that match user-configurable filters.

    Filters:
        - Minimum liquidity USD
        - Maximum pair age (minutes)
        - User has sniper enabled + amount configured
    """

    def __init__(self, db: Database, event_queue: asyncio.Queue) -> None:
        """
        Initialize the auto-sniper.

        Args:
            db: Database instance.
            event_queue: Queue to push buy events (same as whale tracker).
        """
        self._db = db
        self._queue = event_queue
        self._running = False
        self._seen_pairs: Set[str] = set()  # pair addresses already processed
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the sniper polling loop."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("AutoSniper started")

    async def stop(self) -> None:
        """Stop the sniper."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AutoSniper stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop — runs every 30 seconds."""
        while self._running:
            try:
                await self._poll_trending()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("AutoSniper poll error: %s", exc)
            await asyncio.sleep(30)

    async def _poll_trending(self) -> None:
        """Fetch trending tokens from DEX Screener and process them."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(DEXSCREENER_TRENDING_URL)
                tokens = resp.json()
        except Exception as exc:
            logger.debug("Failed to fetch DEX Screener trending: %s", exc)
            return

        if not isinstance(tokens, list):
            return

        for token_data in tokens[:20]:  # Process top 20 trending
            try:
                await self._process_trending_token(token_data)
            except Exception as exc:
                logger.debug("Sniper token processing error: %s", exc)

    async def _process_trending_token(self, token_data: Dict) -> None:
        """Process a single trending token and check if it should be sniped."""
        chain_id = token_data.get("chainId", "")
        token_address = token_data.get("tokenAddress", "")

        if not chain_id or not token_address:
            return

        chain = _CHAIN_MAP.get(chain_id)
        if not chain:
            return

        pair_key = f"{chain}:{token_address}"
        if pair_key in self._seen_pairs:
            return

        # Fetch pair details for filtering
        pair_info = await self._fetch_pair_info(token_address)
        if not pair_info:
            self._seen_pairs.add(pair_key)
            return

        liquidity_usd = float(pair_info.get("liquidity", {}).get("usd", 0) or 0)
        pair_created = int(pair_info.get("pairCreatedAt", 0) or 0)
        age_minutes = (time.time() * 1000 - pair_created) / 60000 if pair_created > 0 else 9999
        token_symbol = pair_info.get("baseToken", {}).get("symbol", "???")
        token_name = pair_info.get("baseToken", {}).get("name", "Unknown")
        price_usd = float(pair_info.get("priceUsd", 0) or 0)

        # Check each user's sniper config
        # We need to get all users with sniper enabled for this chain
        from chains.base_chain import TxEvent

        # Get all copy configs with sniper enabled
        configs = await self._db._fetchall(
            """SELECT cc.*, u.telegram_id
               FROM copy_config cc
               JOIN users u ON u.telegram_id = cc.telegram_id
               WHERE cc.chain=? AND cc.sniper_enabled=1 AND u.is_active=1""",
            (chain,),
        )

        for config in configs:
            min_liq = float(config.get("sniper_min_liquidity_usd", 10000))
            max_age = int(config.get("sniper_max_age_minutes", 30))
            sniper_amount = float(config.get("sniper_amount_usd", 10.0))

            if liquidity_usd < min_liq:
                continue

            if age_minutes > max_age:
                continue

            # Create a synthetic TxEvent for the copy engine
            event = TxEvent(
                chain=chain,
                whale_address="AUTO_SNIPER",
                tx_hash=f"sniper_{int(time.time())}_{token_address[:8]}",
                action="BUY",
                token_address=token_address,
                token_symbol=token_symbol,
                token_name=token_name,
                amount_native=0,
                amount_usd=sniper_amount,
                timestamp=int(time.time()),
                token_liquidity_usd=liquidity_usd,
            )

            logger.info(
                "🎯 SNIPER: New trending token %s ($%s) on %s — "
                "Liq: $%.0f — Age: %.0f min — Buying $%.2f for user %d",
                token_symbol, token_address[:10], chain,
                liquidity_usd, age_minutes, sniper_amount,
                config["telegram_id"],
            )

            await self._queue.put(event)

        self._seen_pairs.add(pair_key)

        # Prevent unbounded memory growth
        if len(self._seen_pairs) > 5000:
            self._seen_pairs = set(list(self._seen_pairs)[-2000:])

    async def _fetch_pair_info(self, token_address: str) -> Optional[Dict]:
        """Fetch pair details from DEX Screener for a token address."""
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url)
                data = resp.json()

            pairs = data.get("pairs", [])
            if pairs:
                # Return the most liquid pair
                return max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            return None
        except Exception:
            return None
