"""
TX Classifier — classifies raw blockchain transactions into TxEvents.
Handles both EVM (Ethereum/BSC) and Solana transaction formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from chains.base_chain import RawTx, TxEvent
from config.constants import (
    BUY_SIGNATURES,
    BSC_DEX_ROUTERS,
    ETH_DEX_ROUTERS,
    SELL_SIGNATURES,
    SOLANA_DEX_PROGRAMS,
    WBNB_ADDRESS,
    WETH_ADDRESS,
)
from core.logger import get_logger

logger = get_logger(__name__)


def classify_evm_tx(tx: RawTx, known_routers: Dict[str, str]) -> Optional[dict]:
    """
    Classify an EVM transaction as a DEX swap buy or sell.
    Returns a partial dict with action and token_address for further enrichment.

    Args:
        tx: Raw EVM transaction.
        known_routers: Map of router_address.lower() → dex_name.

    Returns:
        Dict with 'action' ('BUY'/'SELL') and 'token_address' if matched, else None.
    """
    if not tx.to_address:
        return None

    to_lower = tx.to_address.lower()
    if to_lower not in known_routers:
        return None

    input_data = tx.input_data
    if len(input_data) < 10:
        return None

    method_sig = input_data[:10].lower()

    if method_sig in BUY_SIGNATURES:
        action = "BUY"
        # Path array: last element is the output token
        # We extract raw path positions from calldata
        token_address = _extract_token_from_path(input_data, position="last")
    elif method_sig in SELL_SIGNATURES:
        action = "SELL"
        # Path array: first element is the input token
        token_address = _extract_token_from_path(input_data, position="first")
    else:
        return None

    if not token_address:
        return None

    # Filter out wrapped native tokens
    if token_address.lower() in (WETH_ADDRESS.lower(), WBNB_ADDRESS.lower()):
        return None

    return {"action": action, "token_address": token_address}


def _extract_token_from_path(input_data: str, position: str) -> Optional[str]:
    """
    Attempt to extract a token address from Uniswap V2 calldata using offset parsing.
    This is a best-effort extraction without full ABI decoding.

    Args:
        input_data: Hex-encoded transaction input (with or without 0x prefix).
        position: 'first' or 'last' element of the path array.

    Returns:
        Hex token address or None.
    """
    raw = input_data[2:] if input_data.startswith("0x") else input_data
    try:
        # Skip 4-byte selector
        data = bytes.fromhex(raw[8:])
        # Try to read 32-byte words and find addresses (20 bytes padded to 32)
        # Addresses are right-aligned in 32-byte slots
        addresses = []
        for i in range(0, len(data) - 31, 32):
            word = data[i:i+32]
            # Check if first 12 bytes are zero (padded address)
            if word[:12] == b"\x00" * 12:
                addr_bytes = word[12:]
                if any(b != 0 for b in addr_bytes):
                    addresses.append("0x" + addr_bytes.hex())

        if not addresses:
            return None

        if position == "first":
            return addresses[0]
        else:
            return addresses[-1]
    except Exception:
        return None


def classify_solana_tx(parsed_tx: Dict, whale_address: str) -> Optional[dict]:
    """
    Classify a parsed Solana transaction as a DEX swap buy or sell.

    Args:
        parsed_tx: Full parsed transaction dict from getTransaction RPC.
        whale_address: The whale wallet public key.

    Returns:
        Dict with 'action', 'token_mint', 'amount_tokens' if matched, else None.
    """
    if not parsed_tx:
        return None

    transaction = parsed_tx.get("transaction") or {}
    message = transaction.get("message") or {}
    instructions = message.get("instructions") or []

    involved_programs = set()
    for ix in instructions:
        prog_id = ix.get("programId", "")
        involved_programs.add(prog_id)

    # Also scan inner instructions
    for inner_group in parsed_tx.get("meta", {}).get("innerInstructions") or []:
        for ix in inner_group.get("instructions", []):
            involved_programs.add(ix.get("programId", ""))

    # Must involve a known DEX program
    dex_hit = any(p in SOLANA_DEX_PROGRAMS for p in involved_programs)
    if not dex_hit:
        return None

    # Analyze token balance changes
    meta = parsed_tx.get("meta") or {}
    pre_balances = {
        b["mint"]: float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
        for b in (meta.get("preTokenBalances") or [])
        if b.get("owner") == whale_address
    }
    post_balances = {
        b["mint"]: float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
        for b in (meta.get("postTokenBalances") or [])
        if b.get("owner") == whale_address
    }

    SOL_MINT = "So11111111111111111111111111111111111111112"

    for mint, post_amt in post_balances.items():
        if mint == SOL_MINT:
            continue
        pre_amt = pre_balances.get(mint, 0)
        delta = post_amt - pre_amt
        if abs(delta) < 0.000001:
            continue
        if delta > 0:
            return {"action": "BUY", "token_mint": mint, "amount_tokens": delta}
        else:
            return {"action": "SELL", "token_mint": mint, "amount_tokens": abs(delta)}

    return None
