"""
BSC (BNB Chain) implementation — inherits EthereumChain logic,
overrides router to PancakeSwap V2 and uses BSC RPC endpoints.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import httpx
from web3 import AsyncWeb3
from web3.middleware import geth_poa_middleware

from chains.base_chain import RawTx, TokenInfo, TxEvent
from chains.ethereum import EthereumChain
from config.constants import (
    BSC_DEX_ROUTERS,
    DEFAULT_BSC_RPCS,
    PANCAKESWAP_V2_ROUTER,
    UNISWAP_V2_ROUTER_ABI,
    WBNB_ADDRESS,
)
from core.logger import get_logger

logger = get_logger(__name__)


from config.settings import get_settings

class BSCChain(EthereumChain):
    """
    BNB Smart Chain implementation.
    Uses PancakeSwap V2 router; otherwise identical swap logic to Ethereum.
    BSC is Proof-of-Authority, so we inject ExtraDataToPOAMiddleware.
    """

    CHAIN_NAME = "BSC"
    ROUTER_ADDRESS = PANCAKESWAP_V2_ROUTER
    WETH = WBNB_ADDRESS  # Wrapped BNB on BSC

    def __init__(self) -> None:
        """Initialize with BSC RPC endpoints and PancakeSwap router."""
        self._rpcs = get_settings().bsc_rpc_list
        w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._rpcs[0]))
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self._w3 = w3
        self._router = w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(self.ROUTER_ADDRESS),
            abi=UNISWAP_V2_ROUTER_ABI,
        )

    async def _w3_with_fallback(self) -> AsyncWeb3:
        """Check BSC RPC connectivity and fall back if needed."""
        for rpc in self._rpcs:
            try:
                candidate = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc))
                candidate.middleware_onion.inject(geth_poa_middleware, layer=0)
                await candidate.eth.block_number
                self._w3 = candidate
                self._router = candidate.eth.contract(
                    address=AsyncWeb3.to_checksum_address(self.ROUTER_ADDRESS),
                    abi=UNISWAP_V2_ROUTER_ABI,
                )
                return candidate
            except Exception:
                logger.warning("BSC RPC %s unavailable, trying next", rpc)
        raise RuntimeError("All BSC RPC endpoints are unavailable")

    async def classify_tx(self, tx: RawTx) -> Optional[TxEvent]:
        """
        Classify a BSC transaction as a PancakeSwap buy/sell.
        Overrides to use BSC_DEX_ROUTERS for router detection.

        Args:
            tx: Raw transaction to classify.

        Returns:
            TxEvent or None.
        """
        if not tx.to_address:
            return None
        to_lower = tx.to_address.lower()
        if to_lower not in BSC_DEX_ROUTERS:
            return None

        # Reuse parent classification logic (same ABI, same method signatures)
        return await super().classify_tx(tx)

    async def get_token_price_usd(self, token_addr: str) -> float:
        """
        Get BSC token price from DexScreener (BSC chain filter).

        Args:
            token_addr: BEP-20 token address.

        Returns:
            Price in USD or 0.0.
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                pairs = data.get("pairs") or []
                bsc_pairs = [p for p in pairs if p.get("chainId") == "bsc"]
                if bsc_pairs:
                    return float(bsc_pairs[0].get("priceUsd", 0))
        except Exception as exc:
            logger.debug("DexScreener BSC price failed: %s", exc)
        return 0.0

    async def get_native_price_usd(self) -> float:
        """
        Get BNB price in USD via CoinGecko free API.

        Returns:
            BNB price in USD, or 0.0 on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=binancecoin&vs_currencies=usd"
                )
                return float(resp.json()["binancecoin"]["usd"])
        except Exception as exc:
            logger.warning("BNB price fetch failed: %s", exc)
            return 0.0
