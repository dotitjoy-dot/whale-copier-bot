"""
EVM Wallet — handles ETH and BSC wallet operations:
signing, balance fetching, nonce management, EIP-1559 gas estimation.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import AsyncWeb3
from web3.middleware import geth_poa_middleware

from config.constants import (
    CHAIN_INFO,
    ERC20_ABI,
    DEXSCREENER_TOKEN_URL,
    COINGECKO_ETH_URL,
    COINGECKO_BNB_URL,
    WETH_ADDRESS,
    WBNB_ADDRESS,
)
from config.settings import get_settings
from core.logger import get_logger

logger = get_logger(__name__)


def _get_w3(chain: str) -> AsyncWeb3:
    """Build an AsyncWeb3 instance for the given chain using the first available RPC."""
    settings = get_settings()
    rpcs = settings.eth_rpc_list if chain == "ETH" else settings.bsc_rpc_list
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpcs[0] if rpcs else ""))
    if chain == "BSC":
        # BSC uses Proof-of-Authority
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3


class EVMWallet:
    """
    EVM wallet operations for ETH and BSC chains.
    Handles balance queries, transaction signing, and gas estimation.
    """

    def __init__(self, chain: str, address: str) -> None:
        """
        Initialize an EVM wallet reference.

        Args:
            chain: 'ETH' or 'BSC'.
            address: Checksum or lowercase wallet address.
        """
        self.chain = chain
        self.address = AsyncWeb3.to_checksum_address(address)
        self._w3 = _get_w3(chain)
        self._native_symbol = CHAIN_INFO[chain]["native"]
        self._explorer = CHAIN_INFO[chain]["explorer"]

    async def get_balance(self) -> Dict:
        """
        Fetch native balance and top ERC-20 token balances.

        Returns:
            Dict containing native_balance, native_symbol, usd_value, tokens list.
        """
        try:
            native_wei = await self._w3.eth.get_balance(self.address)
            native_balance = float(AsyncWeb3.from_wei(native_wei, "ether"))
        except Exception as exc:
            logger.error("Error fetching native balance: %s", exc)
            native_balance = 0.0

        # Get native price in USD
        usd_value = 0.0
        native_price = await self.get_native_price_usd()
        usd_value = native_balance * native_price

        return {
            "native_balance": native_balance,
            "native_symbol": self._native_symbol,
            "native_price_usd": native_price,
            "usd_value": usd_value,
            "tokens": [],  # Extended token list would require an indexer API
        }

    async def get_native_price_usd(self) -> float:
        """
        Fetch native coin price in USD from CoinGecko free API.

        Returns:
            Price in USD, or 0.0 on failure.
        """
        url = COINGECKO_ETH_URL if self.chain == "ETH" else COINGECKO_BNB_URL
        key = "ethereum" if self.chain == "ETH" else "binancecoin"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                return float(data[key]["usd"])
        except Exception as exc:
            logger.warning("Could not fetch %s price: %s", self._native_symbol, exc)
            return 0.0

    async def get_token_price_usd(self, token_address: str) -> float:
        """
        Fetch token price in USD from DexScreener API.

        Args:
            token_address: ERC-20 token contract address.

        Returns:
            Price in USD, or 0.0 if not found.
        """
        chain_id = "ethereum" if self.chain == "ETH" else "bsc"
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                pairs = data.get("pairs") or []
                for pair in pairs:
                    if pair.get("chainId") == chain_id:
                        return float(pair.get("priceUsd", 0))
        except Exception as exc:
            logger.warning("DexScreener price fetch failed for %s: %s", token_address, exc)
        return 0.0

    async def get_token_balance(self, token_address: str) -> float:
        """
        Fetch ERC-20 token balance for this wallet.

        Args:
            token_address: ERC-20 token contract address.

        Returns:
            Token balance as a human-readable float (divided by decimals).
        """
        try:
            checksum = AsyncWeb3.to_checksum_address(token_address)
            contract = self._w3.eth.contract(address=checksum, abi=ERC20_ABI)
            raw = await contract.functions.balanceOf(self.address).call()
            decimals = await contract.functions.decimals().call()
            return raw / (10 ** decimals)
        except Exception as exc:
            logger.error("Error fetching token balance for %s: %s", token_address[:10], exc)
            return 0.0

    async def get_nonce(self) -> int:
        """
        Fetch the current nonce (transaction count) for this address.

        Returns:
            Current nonce as integer.
        """
        return await self._w3.eth.get_transaction_count(self.address, "pending")

    async def get_token_info(self, token_address: str) -> Dict:
        """
        Fetch symbol, name, and decimals for an ERC-20 token.

        Args:
            token_address: Token contract address.

        Returns:
            Dict with symbol, name, decimals.
        """
        try:
            checksum = AsyncWeb3.to_checksum_address(token_address)
            contract = self._w3.eth.contract(address=checksum, abi=ERC20_ABI)
            symbol = await contract.functions.symbol().call()
            name = await contract.functions.name().call()
            decimals = await contract.functions.decimals().call()
            return {"symbol": symbol, "name": name, "decimals": decimals}
        except Exception as exc:
            logger.warning("Could not fetch token info for %s: %s", token_address[:10], exc)
            return {"symbol": "UNKNOWN", "name": "Unknown Token", "decimals": 18}

    def sign_transaction(self, tx_dict: Dict, private_key: str) -> bytes:
        """
        Sign a transaction dictionary with the provided private key.

        Args:
            tx_dict: Transaction dict (to, value, gas, nonce, etc.).
            private_key: Hex private key string.

        Returns:
            Raw signed transaction bytes.
        """
        account: LocalAccount = Account.from_key(private_key)
        signed = account.sign_transaction(tx_dict)
        return signed.raw_transaction

    async def send_raw_transaction(self, raw_tx: bytes) -> str:
        """
        Broadcast a signed raw transaction to the network.

        Args:
            raw_tx: Signed transaction bytes.

        Returns:
            Transaction hash as hex string.
        """
        tx_hash = await self._w3.eth.send_raw_transaction(raw_tx)
        return tx_hash.hex()

    async def wait_for_receipt(self, tx_hash: str, timeout: int = 120) -> Dict:
        """
        Wait for a transaction to be confirmed on-chain.

        Args:
            tx_hash: Hex transaction hash.
            timeout: Max seconds to wait.

        Returns:
            Transaction receipt dict.
        """
        receipt = await self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=timeout
        )
        return dict(receipt)

    async def approve_token(
        self,
        token_address: str,
        spender: str,
        amount: int,
        private_key: str,
        gas_params: Dict,
    ) -> str:
        """
        Approve a spender (DEX router) to spend tokens on behalf of this wallet.

        Args:
            token_address: ERC-20 token to approve.
            spender: Spender address (router).
            amount: Amount in raw (wei) units.
            private_key: Wallet private key.
            gas_params: Dict with maxFeePerGas, maxPriorityFeePerGas.

        Returns:
            Transaction hash.
        """
        checksum_token = AsyncWeb3.to_checksum_address(token_address)
        checksum_spender = AsyncWeb3.to_checksum_address(spender)
        contract = self._w3.eth.contract(address=checksum_token, abi=ERC20_ABI)

        current_allowance = await contract.functions.allowance(
            self.address, checksum_spender
        ).call()
        if current_allowance >= amount:
            logger.debug("Token already approved, skipping approve tx")
            return ""

        nonce = await self.get_nonce()
        chain_id = await self._w3.eth.chain_id

        approve_tx = await contract.functions.approve(
            checksum_spender, amount
        ).build_transaction(
            {
                "from": self.address,
                "nonce": nonce,
                "chainId": chain_id,
                "maxFeePerGas": gas_params.get("maxFeePerGas", AsyncWeb3.to_wei(30, "gwei")),
                "maxPriorityFeePerGas": gas_params.get("maxPriorityFeePerGas", AsyncWeb3.to_wei(2, "gwei")),
            }
        )

        raw_tx = self.sign_transaction(approve_tx, private_key)
        tx_hash = await self.send_raw_transaction(raw_tx)
        logger.info("Approve tx sent: %s", tx_hash[:20])
        return tx_hash

    @property
    def w3(self) -> AsyncWeb3:
        """Expose the underlying AsyncWeb3 instance."""
        return self._w3
