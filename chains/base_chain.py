"""
Abstract base class and shared dataclasses for all chain implementations.
Every chain (ETH, BSC, SOL) must implement BaseChain completely.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RawTx:
    """
    Raw transaction data as fetched from a blockchain node,
    before classification.
    """

    chain: str
    tx_hash: str
    block_number: int
    from_address: str
    to_address: str
    value: int            # Native value in smallest unit (wei / lamport)
    input_data: str       # Hex-encoded calldata (EVM) or base64 (SOL)
    timestamp: int        # Unix timestamp
    receipt: Optional[Dict] = None  # EVM receipt dict


@dataclass
class TokenInfo:
    """Metadata for a token fetched from the chain."""

    address: str
    symbol: str
    name: str
    decimals: int
    price_usd: float = 0.0
    liquidity_usd: float = 0.0
    created_timestamp: int = 0


@dataclass
class TxEvent:
    """
    Classified transaction event emitted by the whale tracker.
    Represents a detected buy or sell action by a whale wallet.
    """

    chain: str
    whale_address: str
    tx_hash: str
    action: str           # 'BUY' | 'SELL'
    token_address: str
    token_symbol: str
    token_name: str
    amount_native: float
    amount_usd: float
    timestamp: int
    token_liquidity_usd: float = 0.0


class BaseChain(ABC):
    """
    Abstract interface that every chain implementation must satisfy.
    Provides a uniform API for transaction monitoring and trade execution.
    """

    @abstractmethod
    async def get_recent_txs(self, address: str, since_tx_hash: str = "") -> List[RawTx]:
        """
        Fetch recent transactions for an address.

        Args:
            address: Wallet address to query.
            since_tx_hash: If provided, return only transactions newer than this hash.

        Returns:
            List of RawTx objects, newest first.
        """
        ...

    @abstractmethod
    async def classify_tx(self, tx: RawTx) -> Optional[TxEvent]:
        """
        Classify a raw transaction as a buy, sell, or None (irrelevant).

        Args:
            tx: Raw transaction to classify.

        Returns:
            TxEvent if the transaction is a DEX swap, None otherwise.
        """
        ...

    @abstractmethod
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
        Execute a buy swap (native → token).

        Args:
            token_addr: Token to buy.
            amount_in_native: Amount of native coin to spend.
            wallet_address: Buyer wallet address.
            private_key: Wallet private key (never logged).
            slippage_pct: Max acceptable slippage percentage.
            gas_params: Gas configuration dict.

        Returns:
            Transaction hash string.
        """
        ...

    @abstractmethod
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
        Execute a sell swap (token → native).

        Args:
            token_addr: Token to sell.
            amount_tokens: Amount of tokens to sell.
            wallet_address: Seller wallet address.
            private_key: Wallet private key (never logged).
            slippage_pct: Max acceptable slippage percentage.
            gas_params: Gas configuration dict.

        Returns:
            Transaction hash string.
        """
        ...

    @abstractmethod
    async def get_token_price_usd(self, token_addr: str) -> float:
        """
        Get the current USD price of a token.

        Args:
            token_addr: Token address / mint.

        Returns:
            Price in USD, or 0.0 if unknown.
        """
        ...

    @abstractmethod
    async def get_native_price_usd(self) -> float:
        """
        Get the current USD price of the chain's native coin.

        Returns:
            Price in USD, or 0.0 on failure.
        """
        ...

    @abstractmethod
    async def get_token_info(self, token_addr: str) -> TokenInfo:
        """
        Fetch metadata for a token.

        Args:
            token_addr: Token address / mint.

        Returns:
            TokenInfo dataclass.
        """
        ...
