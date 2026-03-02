"""
Dynamic slippage calculator for DEX trade execution.
Adjusts slippage based on trade size relative to pool liquidity with a hard cap.
"""

from __future__ import annotations

from config.constants import MAX_SLIPPAGE_PCT
from core.logger import get_logger

logger = get_logger(__name__)


def calculate_slippage(
    amount_usd: float,
    max_slippage_pct: float,
    chain: str,
    token_liquidity_usd: float,
) -> float:
    """
    Calculate dynamic slippage percentage for a given trade.

    Base slippage = max_slippage_pct from user config.
    Increases if the trade is large relative to pool liquidity.
    Hard cap at MAX_SLIPPAGE_PCT (25%).

    Rules:
        - If amount_usd > 1% of token_liquidity_usd → add 2% extra slippage.
        - If token_liquidity_usd < $50,000           → add 3% extra slippage.
        - Hard cap at 25%.

    Args:
        amount_usd: USD value of trade to execute.
        max_slippage_pct: User's configured maximum slippage %.
        chain: Chain name (for future chain-specific rules).
        token_liquidity_usd: Token pool liquidity in USD (0 if unknown).

    Returns:
        Effective slippage percentage (capped at 25%).
    """
    slippage = float(max_slippage_pct)

    if token_liquidity_usd > 0:
        # Trade is more than 1% of available liquidity → price impact will be high
        if amount_usd > 0.01 * token_liquidity_usd:
            slippage += 2.0
            logger.debug(
                "Trade $%.2f > 1%% of liquidity $%.2f — adding 2%% slippage",
                amount_usd, token_liquidity_usd
            )

        # Low-liquidity token → extra caution
        if token_liquidity_usd < 50_000:
            slippage += 3.0
            logger.debug(
                "Low liquidity token ($%.0f) — adding 3%% slippage", token_liquidity_usd
            )
    else:
        # Unknown liquidity — assume worst case and use 5% extra
        slippage += 5.0
        logger.debug("Unknown token liquidity — adding 5%% precautionary slippage")

    # Hard cap
    capped = min(slippage, MAX_SLIPPAGE_PCT)
    if capped != slippage:
        logger.debug("Slippage capped from %.1f%% to %.1f%%", slippage, capped)

    return round(capped, 2)
