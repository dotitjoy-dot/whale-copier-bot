"""
Gas Manager — EIP-1559 gas parameter calculation for EVM chains
and Solana priority fee fetching.
Supports user-configured custom base gas and priority tip overrides.
"""

from __future__ import annotations

import asyncio
import statistics
from typing import Dict, Optional

import httpx
from web3 import AsyncWeb3

from core.logger import get_logger

logger = get_logger(__name__)


async def get_evm_gas_params(
    rpc_url: str,
    chain: str = "ETH",
    priority: str = "fast",
    custom_gas_gwei: float = 0,
    priority_tip_gwei: float = 0,
) -> Dict:
    """
    Fetch and calculate EIP-1559 gas parameters for an EVM transaction.

    If custom_gas_gwei > 0, uses that as the base maxFeePerGas.
    If priority_tip_gwei > 0, uses that as maxPriorityFeePerGas.
    Otherwise falls back to dynamic calculation.

    Priority modes (for dynamic):
        'fast'   → maxPriorityFeePerGas = 2x baseFee
        'normal' → maxPriorityFeePerGas = 1.5x baseFee
        'slow'   → maxPriorityFeePerGas = 1x baseFee

    Args:
        rpc_url: RPC endpoint to query.
        chain: Chain name for logging ('ETH' or 'BSC').
        priority: Speed priority — 'fast', 'normal', or 'slow'.
        custom_gas_gwei: User-configured base gas in gwei (0 = auto).
        priority_tip_gwei: User-configured priority tip in gwei (0 = auto).

    Returns:
        Dict with maxFeePerGas, maxPriorityFeePerGas, gas_limit_estimate (all in wei).
    """
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc_url))

    try:
        block = await w3.eth.get_block("latest")
        base_fee = block.get("baseFeePerGas", AsyncWeb3.to_wei(20, "gwei"))
    except Exception:
        base_fee = AsyncWeb3.to_wei(20, "gwei")

    # ── Custom Priority Tip Override ──
    if priority_tip_gwei > 0:
        max_priority_fee = AsyncWeb3.to_wei(priority_tip_gwei, "gwei")
        logger.debug(
            "%s: Using custom priority tip: %.2f gwei", chain, priority_tip_gwei
        )
    else:
        try:
            priority_fee_raw = await w3.eth.max_priority_fee
        except Exception:
            priority_fee_raw = AsyncWeb3.to_wei(2, "gwei")

        multipliers = {"fast": 2.0, "normal": 1.5, "slow": 1.0}
        multiplier = multipliers.get(priority, 2.0)
        max_priority_fee = int(max(priority_fee_raw, int(base_fee * 0.1)) * multiplier)

    # ── Custom Base Gas Override ──
    if custom_gas_gwei > 0:
        max_fee = AsyncWeb3.to_wei(custom_gas_gwei, "gwei") + max_priority_fee
        logger.debug(
            "%s: Using custom base gas: %.2f gwei → maxFee: %.2f gwei",
            chain, custom_gas_gwei,
            round(AsyncWeb3.from_wei(max_fee, "gwei"), 2),
        )
    else:
        max_fee = int(base_fee * 2 + max_priority_fee)

    logger.debug(
        "%s gas params: base=%s gwei, priority=%s gwei, max=%s gwei%s",
        chain,
        round(AsyncWeb3.from_wei(base_fee, "gwei"), 2),
        round(AsyncWeb3.from_wei(max_priority_fee, "gwei"), 2),
        round(AsyncWeb3.from_wei(max_fee, "gwei"), 2),
        " [CUSTOM]" if custom_gas_gwei > 0 or priority_tip_gwei > 0 else "",
    )

    return {
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority_fee,
        "gas_limit_estimate": 250_000,  # Conservative estimate for swaps
    }


async def get_solana_priority_fee(rpc_url: str, custom_fee: int = 0) -> int:
    """
    Fetch the 75th percentile recent prioritization fee for Solana transactions.
    If custom_fee > 0, uses the custom value instead.

    Args:
        rpc_url: Solana RPC endpoint URL.
        custom_fee: Custom priority fee in micro-lamports (0 = auto).

    Returns:
        Recommended priority fee in micro-lamports per compute unit.
    """
    if custom_fee > 0:
        logger.debug("SOL: Using custom priority fee: %d µ-lamports", custom_fee)
        return custom_fee

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getRecentPrioritizationFees",
        "params": [],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(rpc_url, json=payload)
            result = resp.json().get("result", [])

        fees = [int(r.get("prioritizationFee", 0)) for r in result if r.get("prioritizationFee")]

        if not fees:
            return 1_000  # Default 1000 micro-lamports

        fees.sort()
        p75_index = int(len(fees) * 0.75)
        p75_fee = fees[min(p75_index, len(fees) - 1)]

        logger.debug("SOL priority fee (75th pctile): %d µ-lamports", p75_fee)
        return max(p75_fee, 1_000)

    except Exception as exc:
        logger.warning("Failed to fetch Solana priority fees: %s — using default 1000", exc)
        return 1_000


async def get_gas_params(
    chain: str,
    rpc_url: str,
    priority: str = "fast",
    custom_gas_gwei: float = 0,
    priority_tip_gwei: float = 0,
) -> Dict:
    """
    Unified gas parameter fetcher for all chains.
    Supports user-configured custom gas and priority fee overrides.

    Args:
        chain: 'ETH', 'BSC', or 'SOL'.
        rpc_url: RPC endpoint URL.
        priority: Transaction speed priority.
        custom_gas_gwei: Custom base gas in gwei (EVM) or µ-lamports (SOL). 0 = auto.
        priority_tip_gwei: Custom priority tip in gwei (EVM). 0 = auto.

    Returns:
        Dict compatible with chain execute_buy/execute_sell gas_params argument.
    """
    if chain in ("ETH", "BSC"):
        params = await get_evm_gas_params(
            rpc_url, chain, priority,
            custom_gas_gwei=custom_gas_gwei,
            priority_tip_gwei=priority_tip_gwei,
        )
        return params
    elif chain == "SOL":
        custom_sol = int(custom_gas_gwei * 1000) if custom_gas_gwei > 0 else 0
        fee = await get_solana_priority_fee(rpc_url, custom_fee=custom_sol)
        return {"priority_fee_micro_lamports": fee}
    else:
        raise ValueError(f"Unsupported chain: {chain}")
