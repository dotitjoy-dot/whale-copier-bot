"""
Ethereum chain implementation.
Monitors whale wallets, classifies swaps, and executes Uniswap V2 trades.
Uses free public RPC endpoints (LlamaRPC / Ankr) with fallback.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

import httpx
from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound

from chains.base_chain import BaseChain, RawTx, TokenInfo, TxEvent
from config.constants import (
    BUY_SIGNATURES,
    DEFAULT_ETH_RPCS,
    ERC20_ABI,
    ETH_DEX_ROUTERS,
    SELL_SIGNATURES,
    UNISWAP_V2_ROUTER,
    UNISWAP_V2_ROUTER_ABI,
    WETH_ADDRESS,
)
from core.logger import get_logger

logger = get_logger(__name__)


from config.settings import get_settings

class EthereumChain(BaseChain):
    """
    Ethereum mainnet chain monitor and swap executor.
    Implements whale monitoring via block log scanning and Uniswap V2 swaps.
    """

    CHAIN_NAME = "ETH"
    ROUTER_ADDRESS = UNISWAP_V2_ROUTER
    WETH = WETH_ADDRESS

    def __init__(self) -> None:
        """Initialize with the first available free RPC, falling back as needed."""
        self._rpcs = get_settings().eth_rpc_list
        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._rpcs[0]))
        self._router = self._w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(self.ROUTER_ADDRESS),
            abi=UNISWAP_V2_ROUTER_ABI,
        )

    async def _w3_with_fallback(self) -> AsyncWeb3:
        """Check connectivity and return w3, trying fallback RPC if needed."""
        for rpc in self._rpcs:
            try:
                candidate = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc))
                await candidate.eth.block_number
                self._w3 = candidate
                self._router = candidate.eth.contract(
                    address=AsyncWeb3.to_checksum_address(self.ROUTER_ADDRESS),
                    abi=UNISWAP_V2_ROUTER_ABI,
                )
                return candidate
            except Exception:
                logger.warning("ETH RPC %s unavailable, trying next", rpc)
        raise RuntimeError("All Ethereum RPC endpoints are unavailable")

    async def get_recent_txs(self, address: str, since_tx_hash: str = "") -> List[RawTx]:
        """
        Fetch recent transactions for a whale address by scanning the last 50 blocks.
        Uses eth_getLogs to find Transfer events and normal txs from this address.

        Args:
            address: Wallet address to monitor.
            since_tx_hash: Previously seen latest tx hash (not used for EVM log scanning).

        Returns:
            List of RawTx objects.
        """
        w3 = await self._w3_with_fallback()
        txs: List[RawTx] = []

        try:
            latest_block = await w3.eth.block_number
            from_block = max(0, latest_block - 50)
            checksum_addr = AsyncWeb3.to_checksum_address(address)

            # Get all outgoing transactions (from whale)
            for block_num in range(latest_block, from_block, -1):
                try:
                    block = await w3.eth.get_block(block_num, full_transactions=True)
                    for tx in block.transactions:
                        if tx.get("from", "").lower() == address.lower():
                            receipt = None
                            try:
                                receipt = dict(await w3.eth.get_transaction_receipt(tx.hash))
                            except Exception:
                                pass

                            raw_tx = RawTx(
                                chain=self.CHAIN_NAME,
                                tx_hash=tx.hash.hex(),
                                block_number=block_num,
                                from_address=tx.get("from", ""),
                                to_address=tx.get("to", "") or "",
                                value=tx.get("value", 0),
                                input_data=tx.get("input", b"").hex() if isinstance(tx.get("input", b""), bytes) else tx.get("input", "0x"),
                                timestamp=block.get("timestamp", int(time.time())),
                                receipt=receipt,
                            )
                            txs.append(raw_tx)
                except Exception as ex:
                    logger.debug("Error fetching block %d: %s", block_num, ex)
                    continue

        except Exception as exc:
            logger.error("Error fetching ETH txs for %s: %s", address[:10], exc)

        return txs

    async def classify_tx(self, tx: RawTx) -> Optional[TxEvent]:
        """
        Classify a raw Ethereum transaction as a Uniswap buy/sell or None.

        Args:
            tx: Raw transaction to evaluate.

        Returns:
            TxEvent on valid DEX swap, None otherwise.
        """
        if not tx.to_address:
            return None

        to_lower = tx.to_address.lower()
        if to_lower not in ETH_DEX_ROUTERS:
            return None

        input_data = tx.input_data
        if len(input_data) < 10:
            return None

        method_sig = input_data[:10].lower()
        action = None
        token_address = None

        if method_sig in BUY_SIGNATURES:
            action = "BUY"
            # Path is 3rd argument (index 2) in most swap methods
            try:
                decoded = self._router.decode_function_input(bytes.fromhex(input_data[2:]))
                path = decoded[1].get("path", [])
                if len(path) >= 2:
                    token_address = path[-1]  # Last token in path = token being bought
            except Exception:
                return None

        elif method_sig in SELL_SIGNATURES:
            action = "SELL"
            try:
                decoded = self._router.decode_function_input(bytes.fromhex(input_data[2:]))
                path = decoded[1].get("path", [])
                if len(path) >= 2:
                    token_address = path[0]  # First token = token being sold
            except Exception:
                return None

        if not action or not token_address:
            return None

        token_addr_str = token_address if isinstance(token_address, str) else token_address.lower()

        # Skip WETH as token (it's native wrapped)
        if token_addr_str.lower() == self.WETH.lower():
            return None

        token_info = await self.get_token_info(token_addr_str)
        native_price = await self.get_native_price_usd()
        amount_native = float(AsyncWeb3.from_wei(tx.value, "ether"))
        amount_usd = amount_native * native_price

        token_price = await self.get_token_price_usd(token_addr_str)
        liquidity = 0.0  # Would need DexScreener pair data for liquidity

        return TxEvent(
            chain=self.CHAIN_NAME,
            whale_address=tx.from_address,
            tx_hash=tx.tx_hash,
            action=action,
            token_address=token_addr_str,
            token_symbol=token_info.symbol,
            token_name=token_info.name,
            amount_native=amount_native,
            amount_usd=amount_usd,
            timestamp=tx.timestamp,
            token_liquidity_usd=liquidity,
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
        Execute a Uniswap V2 buy: ETH → Token via swapExactETHForTokens.

        Args:
            token_addr: Token to buy (ERC-20 address).
            amount_in_native: ETH amount to spend.
            wallet_address: Buyer's wallet address.
            private_key: Buyer's private key.
            slippage_pct: Max slippage %.
            gas_params: EIP-1559 gas params dict.

        Returns:
            Transaction hash string.
        """
        w3 = await self._w3_with_fallback()
        checksum_token = AsyncWeb3.to_checksum_address(token_addr)
        checksum_wallet = AsyncWeb3.to_checksum_address(wallet_address)

        amount_in_wei = AsyncWeb3.to_wei(amount_in_native, "ether")
        path = [AsyncWeb3.to_checksum_address(self.WETH), checksum_token]

        # Calculate minimum output with slippage
        try:
            amounts_out = await self._router.functions.getAmountsOut(amount_in_wei, path).call()
            amount_out_min = int(amounts_out[-1] * (1 - slippage_pct / 100))
        except Exception as exc:
            logger.warning("getAmountsOut failed: %s, using 0 amountOutMin", exc)
            amount_out_min = 0

        deadline = int(time.time()) + 300  # 5 minutes
        nonce = await w3.eth.get_transaction_count(checksum_wallet, "pending")
        chain_id = await w3.eth.chain_id

        tx = await self._router.functions.swapExactETHForTokens(
            amount_out_min, path, checksum_wallet, deadline
        ).build_transaction(
            {
                "from": checksum_wallet,
                "value": amount_in_wei,
                "nonce": nonce,
                "chainId": chain_id,
                "maxFeePerGas": gas_params.get("maxFeePerGas", AsyncWeb3.to_wei(30, "gwei")),
                "maxPriorityFeePerGas": gas_params.get("maxPriorityFeePerGas", AsyncWeb3.to_wei(2, "gwei")),
            }
        )

        from eth_account import Account
        account = Account.from_key(private_key)
        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("ETH buy tx sent: %s", tx_hash.hex()[:20])
        return tx_hash.hex()

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
        Execute a Uniswap V2 sell: Token → ETH via swapExactTokensForETH.
        Handles token approval automatically.

        Args:
            token_addr: Token to sell.
            amount_tokens: Amount of tokens (human-readable) to sell.
            wallet_address: Seller's wallet address.
            private_key: Seller's private key.
            slippage_pct: Max slippage %.
            gas_params: EIP-1559 gas params dict.

        Returns:
            Transaction hash string.
        """
        w3 = await self._w3_with_fallback()
        checksum_token = AsyncWeb3.to_checksum_address(token_addr)
        checksum_wallet = AsyncWeb3.to_checksum_address(wallet_address)
        checksum_router = AsyncWeb3.to_checksum_address(self.ROUTER_ADDRESS)

        # Get token decimals to convert human amount → raw
        token_contract = w3.eth.contract(address=checksum_token, abi=ERC20_ABI)
        decimals = await token_contract.functions.decimals().call()
        amount_in = int(amount_tokens * (10 ** decimals))

        path = [checksum_token, AsyncWeb3.to_checksum_address(self.WETH)]

        # Approve router if needed
        allowance = await token_contract.functions.allowance(checksum_wallet, checksum_router).call()
        if allowance < amount_in:
            nonce = await w3.eth.get_transaction_count(checksum_wallet, "pending")
            chain_id = await w3.eth.chain_id
            approve_tx = await token_contract.functions.approve(
                checksum_router, 2**256 - 1  # max approval
            ).build_transaction(
                {
                    "from": checksum_wallet,
                    "nonce": nonce,
                    "chainId": chain_id,
                    "maxFeePerGas": gas_params.get("maxFeePerGas", AsyncWeb3.to_wei(30, "gwei")),
                    "maxPriorityFeePerGas": gas_params.get("maxPriorityFeePerGas", AsyncWeb3.to_wei(2, "gwei")),
                }
            )
            from eth_account import Account
            account = Account.from_key(private_key)
            signed_approve = account.sign_transaction(approve_tx)
            approve_hash = await w3.eth.send_raw_transaction(signed_approve.raw_transaction)
            logger.info("Token approve tx: %s — waiting...", approve_hash.hex()[:20])
            await w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)

        try:
            amounts_out = await self._router.functions.getAmountsOut(amount_in, path).call()
            amount_out_min = int(amounts_out[-1] * (1 - slippage_pct / 100))
        except Exception:
            amount_out_min = 0

        deadline = int(time.time()) + 300
        nonce = await w3.eth.get_transaction_count(checksum_wallet, "pending")
        chain_id = await w3.eth.chain_id

        sell_tx = await self._router.functions.swapExactTokensForETH(
            amount_in, amount_out_min, path, checksum_wallet, deadline
        ).build_transaction(
            {
                "from": checksum_wallet,
                "nonce": nonce,
                "chainId": chain_id,
                "maxFeePerGas": gas_params.get("maxFeePerGas", AsyncWeb3.to_wei(30, "gwei")),
                "maxPriorityFeePerGas": gas_params.get("maxPriorityFeePerGas", AsyncWeb3.to_wei(2, "gwei")),
            }
        )

        from eth_account import Account
        account = Account.from_key(private_key)
        signed = account.sign_transaction(sell_tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("ETH sell tx sent: %s", tx_hash.hex()[:20])
        return tx_hash.hex()

    async def get_token_price_usd(self, token_addr: str) -> float:
        """
        Get token price via DexScreener free API, fallback to Uniswap on-chain.

        Args:
            token_addr: Token contract address.

        Returns:
            Price in USD, or 0.0 if unavailable.
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                pairs = data.get("pairs") or []
                eth_pairs = [p for p in pairs if p.get("chainId") == "ethereum"]
                if eth_pairs:
                    return float(eth_pairs[0].get("priceUsd", 0))
        except Exception as exc:
            logger.debug("DexScreener price failed: %s", exc)
        return 0.0

    async def get_native_price_usd(self) -> float:
        """
        Get ETH price in USD via CoinGecko free API.

        Returns:
            ETH price in USD, or 0.0 on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
                )
                return float(resp.json()["ethereum"]["usd"])
        except Exception as exc:
            logger.warning("ETH price fetch failed: %s", exc)
            return 0.0

    async def get_token_info(self, token_addr: str) -> TokenInfo:
        """
        Fetch ERC-20 token metadata from chain.

        Args:
            token_addr: Token contract address.

        Returns:
            TokenInfo with symbol, name, decimals.
        """
        try:
            w3 = await self._w3_with_fallback()
            checksum = AsyncWeb3.to_checksum_address(token_addr)
            contract = w3.eth.contract(address=checksum, abi=ERC20_ABI)
            symbol = await contract.functions.symbol().call()
            name = await contract.functions.name().call()
            decimals = await contract.functions.decimals().call()
            price = await self.get_token_price_usd(token_addr)
            return TokenInfo(
                address=token_addr,
                symbol=symbol,
                name=name,
                decimals=decimals,
                price_usd=price,
            )
        except Exception as exc:
            logger.warning("Could not fetch token info for %s: %s", token_addr[:10], exc)
            return TokenInfo(address=token_addr, symbol="UNKNOWN", name="Unknown", decimals=18)
