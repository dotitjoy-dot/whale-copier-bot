"""
Solana chain implementation.
Monitors whale wallets via getSignaturesForAddress polling.
Classifies Raydium/Jupiter swaps and executes via Jupiter V6 free public API.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Dict, List, Optional

import httpx

from chains.base_chain import BaseChain, RawTx, TokenInfo, TxEvent
from config.constants import (
    DEFAULT_SOL_RPCS,
    JUPITER_PRICE_URL,
    JUPITER_QUOTE_URL,
    JUPITER_SWAP_URL,
    SOLANA_DEX_PROGRAMS,
    JUPITER_V6_PROGRAM_ID,
    RAYDIUM_AMM_PROGRAM_ID,
)
from core.logger import get_logger

logger = get_logger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"  # Wrapped SOL


from config.settings import get_settings

class SolanaChain(BaseChain):
    """
    Solana mainnet chain monitor and swap executor.
    Uses free Solana public RPC for monitoring and Jupiter V6 for swaps.
    """

    CHAIN_NAME = "SOL"

    def __init__(self) -> None:
        """Initialize with list of free Solana RPC endpoints."""
        self._rpcs = get_settings().sol_rpc_list

    async def _rpc_call(self, method: str, params: list) -> Dict:
        """
        Execute a JSON-RPC call across available Solana endpoints with fallback.

        Args:
            method: Solana RPC method name.
            params: Method parameters.

        Returns:
            Result portion of the JSON-RPC response.

        Raises:
            RuntimeError: If all endpoints fail.
        """
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        for rpc_url in self._rpcs:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(rpc_url, json=payload)
                    data = resp.json()
                    if "error" in data:
                        raise RuntimeError(f"RPC error: {data['error']}")
                    return data.get("result", {})
            except (httpx.RequestError, RuntimeError) as exc:
                logger.warning("SOL RPC %s failed: %s", rpc_url[:30], exc)
        raise RuntimeError("All Solana RPC endpoints failed")

    async def get_recent_txs(self, address: str, since_tx_hash: str = "") -> List[RawTx]:
        """
        Fetch recent signature list for a Solana address and retrieve transaction details.

        Args:
            address: Solana wallet public key (base58).
            since_tx_hash: Previously seen latest transaction signature.

        Returns:
            List of RawTx objects (newest first).
        """
        txs: List[RawTx] = []
        try:
            params: list = [address, {"limit": 10, "commitment": "confirmed"}]
            if since_tx_hash:
                params[1]["until"] = since_tx_hash

            result = await self._rpc_call("getSignaturesForAddress", params)
            sigs = result if isinstance(result, list) else []

            for sig_info in sigs:
                sig = sig_info.get("signature", "")
                if not sig:
                    continue
                try:
                    tx_result = await self._rpc_call(
                        "getTransaction",
                        [sig, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}],
                    )
                    if not tx_result:
                        continue
                    block_time = tx_result.get("blockTime") or int(time.time())
                    slot = tx_result.get("slot", 0)
                    raw_tx = RawTx(
                        chain=self.CHAIN_NAME,
                        tx_hash=sig,
                        block_number=slot,
                        from_address=address,
                        to_address="",
                        value=0,
                        input_data=str(tx_result),  # Full parsed tx as string
                        timestamp=block_time,
                        receipt=tx_result,
                    )
                    txs.append(raw_tx)
                except Exception as exc:
                    logger.debug("Error fetching SOL tx %s: %s", sig[:10], exc)
        except Exception as exc:
            logger.error("Error fetching SOL txs for %s: %s", address[:10], exc)
        return txs

    async def classify_tx(self, tx: RawTx) -> Optional[TxEvent]:
        """
        Classify a Solana transaction as a DEX swap (Raydium / Jupiter) or None.

        Args:
            tx: Raw transaction with parsed JSON in receipt field.

        Returns:
            TxEvent or None.
        """
        if not tx.receipt:
            return None

        parsed = tx.receipt
        transaction = parsed.get("transaction") or {}
        message = transaction.get("message") or {}
        instructions = message.get("instructions") or []
        inner_ixs = parsed.get("meta", {}).get("innerInstructions") or []

        # Collect all program IDs that executed
        involved_programs = set()
        for ix in instructions:
            prog_id = ix.get("programId", "")
            involved_programs.add(prog_id)

        # Check inner instructions
        for inner_group in inner_ixs:
            for ix in inner_group.get("instructions", []):
                involved_programs.add(ix.get("programId", ""))

        # Check if any known DEX program was called
        dex_match = None
        for prog in involved_programs:
            if prog in SOLANA_DEX_PROGRAMS:
                dex_match = prog
                break

        if not dex_match:
            return None

        # Determine buy vs sell from pre/post token balances
        meta = parsed.get("meta") or {}
        pre_balances = meta.get("preTokenBalances") or []
        post_balances = meta.get("postTokenBalances") or []

        # Find token mint that changed balance for this wallet
        token_mint = None
        action = "BUY"
        amount_native = 0.0

        pre_map = {b.get("mint"): float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                   for b in pre_balances if b.get("owner") == tx.from_address}
        post_map = {b.get("mint"): float(b.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                    for b in post_balances if b.get("owner") == tx.from_address}

        for mint, post_amt in post_map.items():
            if mint == SOL_MINT:
                continue
            pre_amt = pre_map.get(mint, 0)
            if post_amt > pre_amt:
                token_mint = mint
                action = "BUY"
                amount_native = post_amt - pre_amt
                break
            elif post_amt < pre_amt:
                token_mint = mint
                action = "SELL"
                amount_native = pre_amt - post_amt
                break

        if not token_mint:
            return None

        token_info = await self.get_token_info(token_mint)
        token_price = await self.get_token_price_usd(token_mint)
        native_price = await self.get_native_price_usd()
        amount_usd = amount_native * token_price

        return TxEvent(
            chain=self.CHAIN_NAME,
            whale_address=tx.from_address,
            tx_hash=tx.tx_hash,
            action=action,
            token_address=token_mint,
            token_symbol=token_info.symbol,
            token_name=token_info.name,
            amount_native=amount_native,
            amount_usd=amount_usd,
            timestamp=tx.timestamp,
        )

    async def execute_buy(
        self,
        token_addr: str,
        amount_in_native: float,
        wallet_address: str,
        private_key: str,
        slippage_pct: float,
        gas_params: Dict,
    ) -> str:
        """
        Execute a Solana buy via Jupiter V6 Quote + Swap API (free public).
        SOL → Target Token.

        Args:
            token_addr: Target SPL token mint address.
            amount_in_native: SOL amount to spend.
            wallet_address: Buyer Solana public key.
            private_key: Hex-encoded secret key.
            slippage_pct: Max slippage in percent.
            gas_params: Priority fee config (from gas_manager).

        Returns:
            Transaction signature string.
        """
        amount_lamports = int(amount_in_native * 1_000_000_000)
        slippage_bps = int(slippage_pct * 100)

        # Step 1: Get Quote
        async with httpx.AsyncClient(timeout=15) as client:
            quote_resp = await client.get(
                JUPITER_QUOTE_URL,
                params={
                    "inputMint": SOL_MINT,
                    "outputMint": token_addr,
                    "amount": amount_lamports,
                    "slippageBps": slippage_bps,
                },
            )
            quote = quote_resp.json()

        if "error" in quote:
            raise RuntimeError(f"Jupiter quote error: {quote['error']}")

        # Step 2: Get swap transaction
        priority_fee = gas_params.get("priority_fee_micro_lamports", 1000)
        async with httpx.AsyncClient(timeout=15) as client:
            swap_resp = await client.post(
                JUPITER_SWAP_URL,
                json={
                    "quoteResponse": quote,
                    "userPublicKey": wallet_address,
                    "wrapAndUnwrapSol": True,
                    "prioritizationFeeLamports": priority_fee,
                },
            )
            swap_data = swap_resp.json()

        if "swapTransaction" not in swap_data:
            raise RuntimeError(f"Jupiter swap error: {swap_data}")

        # Step 3: Sign and send
        from wallets.solana_wallet import SolanaWallet
        from solders.transaction import VersionedTransaction  # type: ignore

        keypair = SolanaWallet.keypair_from_secret(private_key)
        raw_tx_bytes = base64.b64decode(swap_data["swapTransaction"])
        versioned_tx = VersionedTransaction.from_bytes(raw_tx_bytes)
        signed_tx = keypair.sign_message(bytes(versioned_tx.message))

        # Send via RPC
        result = await self._rpc_call(
            "sendTransaction",
            [
                base64.b64encode(bytes(versioned_tx)).decode(),
                {"encoding": "base64", "preflightCommitment": "confirmed"},
            ],
        )

        sig = result if isinstance(result, str) else str(result)
        logger.info("SOL buy tx submitted: %s", sig[:20])
        return sig

    async def execute_sell(
        self,
        token_addr: str,
        amount_tokens: float,
        wallet_address: str,
        private_key: str,
        slippage_pct: float,
        gas_params: Dict,
    ) -> str:
        """
        Execute a Solana sell via Jupiter V6: Target Token → SOL.

        Args:
            token_addr: SPL token mint to sell.
            amount_tokens: Amount of tokens (human-readable) to sell.
            wallet_address: Seller Solana public key.
            private_key: Hex-encoded secret key.
            slippage_pct: Max slippage in percent.
            gas_params: Priority fee config.

        Returns:
            Transaction signature string.
        """
        token_info = await self.get_token_info(token_addr)
        decimals = token_info.decimals
        amount_raw = int(amount_tokens * (10 ** decimals))
        slippage_bps = int(slippage_pct * 100)

        async with httpx.AsyncClient(timeout=15) as client:
            quote_resp = await client.get(
                JUPITER_QUOTE_URL,
                params={
                    "inputMint": token_addr,
                    "outputMint": SOL_MINT,
                    "amount": amount_raw,
                    "slippageBps": slippage_bps,
                },
            )
            quote = quote_resp.json()

        if "error" in quote:
            raise RuntimeError(f"Jupiter quote error: {quote['error']}")

        priority_fee = gas_params.get("priority_fee_micro_lamports", 1000)
        async with httpx.AsyncClient(timeout=15) as client:
            swap_resp = await client.post(
                JUPITER_SWAP_URL,
                json={
                    "quoteResponse": quote,
                    "userPublicKey": wallet_address,
                    "wrapAndUnwrapSol": True,
                    "prioritizationFeeLamports": priority_fee,
                },
            )
            swap_data = swap_resp.json()

        if "swapTransaction" not in swap_data:
            raise RuntimeError(f"Jupiter swap error: {swap_data}")

        from wallets.solana_wallet import SolanaWallet
        from solders.transaction import VersionedTransaction  # type: ignore

        keypair = SolanaWallet.keypair_from_secret(private_key)
        raw_tx_bytes = base64.b64decode(swap_data["swapTransaction"])
        versioned_tx = VersionedTransaction.from_bytes(raw_tx_bytes)

        result = await self._rpc_call(
            "sendTransaction",
            [
                base64.b64encode(bytes(versioned_tx)).decode(),
                {"encoding": "base64", "preflightCommitment": "confirmed"},
            ],
        )

        sig = result if isinstance(result, str) else str(result)
        logger.info("SOL sell tx submitted: %s", sig[:20])
        return sig

    async def get_token_price_usd(self, token_addr: str) -> float:
        """
        Get SPL token price via Jupiter price API (free public).

        Args:
            token_addr: SPL token mint address.

        Returns:
            Price in USD, or 0.0 if unavailable.
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    return float(pairs[0].get("priceUsd", 0))
                return 0.0
        except Exception as exc:
            logger.warning("DexScreener price failed for %s: %s", token_addr[:10], exc)
            return 0.0

    async def get_native_price_usd(self) -> float:
        """
        Get SOL price in USD via Jupiter price API.

        Returns:
            SOL price in USD, or 0.0 on failure.
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{SOL_MINT}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    return float(pairs[0].get("priceUsd", 0))
                return 0.0
        except Exception:
            return 0.0

    async def get_token_info(self, token_addr: str) -> TokenInfo:
        """
        Fetch SPL token metadata via Jupiter token list API.

        Args:
            token_addr: SPL token mint address.

        Returns:
            TokenInfo with symbol, name, decimals.
        """
        try:
            url = f"https://token.jup.ag/strict"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                tokens = resp.json()
                for t in tokens:
                    if t.get("address") == token_addr:
                        return TokenInfo(
                            address=token_addr,
                            symbol=t.get("symbol", "UNKNOWN"),
                            name=t.get("name", "Unknown"),
                            decimals=t.get("decimals", 9),
                            price_usd=await self.get_token_price_usd(token_addr),
                        )
        except Exception as exc:
            logger.warning("Could not fetch SOL token info for %s: %s", token_addr[:10], exc)

        return TokenInfo(
            address=token_addr,
            symbol="UNKNOWN",
            name="Unknown Solana Token",
            decimals=9,
        )
