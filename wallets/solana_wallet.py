"""
Solana Wallet — handles SOL wallet operations:
balance queries, SPL token accounts, transaction signing, and broadcasting.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

import httpx

from config.constants import JUPITER_PRICE_URL
from config.settings import get_settings
from core.logger import get_logger

logger = get_logger(__name__)


class SolanaWallet:
    """
    Solana wallet operations.
    Handles SOL and SPL token balance queries and transaction signing.
    """

    def __init__(self, address: str) -> None:
        """
        Initialize a Solana wallet reference (read-only operations).

        Args:
            address: Solana base58 public key address.
        """
        self.address = address
        rpcs = get_settings().sol_rpc_list
        self._rpc_url = rpcs[0] if rpcs else ""

    async def _rpc_call(self, method: str, params: list) -> Dict:
        """
        Execute a raw JSON-RPC call against the Solana RPC endpoint.

        Args:
            method: RPC method name.
            params: Method parameters list.

        Returns:
            Parsed JSON response dict.

        Raises:
            RuntimeError: On RPC error or network failure.
        """
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        rpcs = get_settings().sol_rpc_list
        for rpc_url in rpcs:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(rpc_url, json=payload)
                    data = resp.json()
                    if "error" in data:
                        raise RuntimeError(f"RPC error: {data['error']}")
                    return data.get("result", {})
            except (httpx.RequestError, RuntimeError) as exc:
                logger.warning("RPC %s failed for %s: %s, trying fallback", method, rpc_url[:30], exc)
                self._rpc_url = rpcs[-1] if rpcs else "" # Try next
        raise RuntimeError(f"All Solana RPC endpoints failed for method: {method}")

    async def get_balance(self) -> Dict:
        """
        Fetch SOL native balance and SPL token accounts.

        Returns:
            Dict with native_balance, native_symbol, usd_value, tokens list.
        """
        try:
            result = await self._rpc_call(
                "getBalance", [self.address, {"commitment": "confirmed"}]
            )
            lamports = result.get("value", 0)
            sol_balance = lamports / 1_000_000_000  # 1 SOL = 1e9 lamports
        except Exception as exc:
            logger.error("Error fetching SOL balance: %s", exc)
            sol_balance = 0.0

        sol_price = await self.get_native_price_usd()
        usd_value = sol_balance * sol_price

        # Fetch SPL token accounts
        tokens = await self._get_token_accounts()

        return {
            "native_balance": sol_balance,
            "native_symbol": "SOL",
            "native_price_usd": sol_price,
            "usd_value": usd_value,
            "tokens": tokens,
        }

    async def _get_token_accounts(self) -> List[Dict]:
        """
        Fetch all SPL token accounts owned by this wallet.

        Returns:
            List of token account dicts with mint, balance, decimals.
        """
        try:
            result = await self._rpc_call(
                "getTokenAccountsByOwner",
                [
                    self.address,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed", "commitment": "confirmed"},
                ],
            )
            accounts = result.get("value", [])
            tokens = []
            for acct in accounts:
                info = acct.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                mint = info.get("mint", "")
                token_amount = info.get("tokenAmount", {})
                ui_amount = token_amount.get("uiAmount", 0) or 0
                if ui_amount > 0:
                    tokens.append({
                        "mint": mint,
                        "balance": ui_amount,
                        "decimals": token_amount.get("decimals", 9),
                    })
            return tokens
        except Exception as exc:
            logger.warning("Could not fetch SPL token accounts: %s", exc)
            return []

    async def get_native_price_usd(self) -> float:
        """
        Fetch SOL price in USD using Jupiter price API.

        Returns:
            SOL price in USD, or 0.0 on failure.
        """
        # Wrapped SOL mint
        SOL_MINT = "So11111111111111111111111111111111111111112"
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{SOL_MINT}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    return float(pairs[0].get("priceUsd", 0))
        except Exception as exc:
            logger.warning("Could not fetch SOL price: %s", exc)
        # Fallback to CoinGecko
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
                )
                return float(resp.json()["solana"]["usd"])
        except Exception:
            return 0.0

    async def get_token_price_usd(self, mint: str) -> float:
        """
        Fetch SPL token price in USD via Jupiter price API.

        Args:
            mint: SPL token mint address.

        Returns:
            Price in USD, or 0.0 if not found.
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    return float(pairs[0].get("priceUsd", 0))
        except Exception as exc:
            logger.warning("DexScreener price failed for %s: %s", mint[:10], exc)
            return 0.0

    @staticmethod
    def keypair_from_secret(secret_hex: str):
        """
        Reconstruct a Solana Keypair from a hex-encoded secret key.

        Args:
            secret_hex: 32 or 64 byte secret as hex string.

        Returns:
            solders Keypair instance.
        """
        from solders.keypair import Keypair  # type: ignore
        secret_bytes = bytes.fromhex(secret_hex)
        if len(secret_bytes) == 32:
            return Keypair.from_seed(secret_bytes)
        elif len(secret_bytes) == 64:
            return Keypair.from_bytes(secret_bytes)
        raise ValueError(f"Invalid secret key length: {len(secret_bytes)}")
