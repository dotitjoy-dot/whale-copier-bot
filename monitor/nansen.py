import asyncio
import logging
import time
from typing import Dict, List
import aiohttp
from core.database import Database

logger = logging.getLogger(__name__)

# Nansen System User ID
NANSEN_SYSTEM_ID = 0

class NansenSmartMoneyUpdater:
    """
    Background job to periodically fetch Smart Money DEX trades from Nansen API,
    and update the whale_wallets table for telegram_id=NANSEN_SYSTEM_ID (System user).
    Users can then auto-trade these wallets if they toggle 'Copy Smart Money' in settings.
    """
    def __init__(self, db: Database, api_key: str = ""):
        self.db = db
        self.api_key = api_key.strip()
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("Nansen Smart Money Updater Started (API Key: %s)", "SET" if self.api_key else "NOT SET")
        asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        logger.info("Nansen Smart Money Updater Stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.update_smart_money()
            except Exception as e:
                logger.error("Nansen API Sync Error: %s", e)
            
            # The Nansen API limit is 3 times a day.
            # We sleep for 8 hours between updates.
            logger.info("Nansen Smart Money sleeping for 8 hours...")
            for _ in range(8 * 3600):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def update_smart_money(self) -> None:
        """Fetch latest Smart Money DEX trades and populate the DB"""
        
        # We need an active user for telegram_id=0 to satisfy DB foreign keys.
        await self.db.ensure_user(NANSEN_SYSTEM_ID, "nansen_system_bot", is_admin=False)

        if not self.api_key:
            logger.warning("No Nansen API key provided. Skipping real sync.")
            # For demonstration without an API key, we don't drop real wallets.
            return

        # Nansen DEX Trades endpoint (Smart Money)
        # Note: Exact endpoint path should be verified against Nansen's docs.
        # This is a conceptual implementation of their standard Smart Money endpoint.
        url = "https://pro-api.nansen.ai/v1/smart-money/dex-trades"
        headers = {
            "api-key": self.api_key,
            "accept": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                logger.info("Fetching Smart Money feeds from Nansen...")
                async with session.get(url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        trades = data.get("data", {}).get("trades", [])
                        
                        count_added = 0
                        for trade in trades[:100]:  # Take top 100 recent smart money trades
                            address = trade.get("sender_address", "")
                            nansen_chain = trade.get("blockchain", "ethereum").lower()
                            
                            # Map Nansen chains to our internal chain names
                            chain = "ETH"
                            if "solana" in nansen_chain: chain = "SOL"
                            elif "binance" in nansen_chain or "bsc" in nansen_chain: chain = "BSC"
                            
                            if address and chain:
                                # Overwrite/add as a system whale
                                await self.db.add_whale(NANSEN_SYSTEM_ID, chain, address, "Smart Money Feed")
                                count_added += 1
                        
                        logger.info("Successfully synced %d Smart Money wallets from Nansen.", count_added)
                    else:
                        resp_text = await resp.text()
                        logger.error("Nansen API Error %d: %s", resp.status, resp_text)
        except Exception as e:
            logger.error("Failed to connect to Nansen API: %s", e)

