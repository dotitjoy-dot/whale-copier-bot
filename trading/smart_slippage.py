"""
Smart Slippage — dynamically adjusts slippage based on on-chain pool volatility.
Queries DexScreener price history to measure recent volatility and scales slippage
accordingly. Falls back to the standard liquidity-based slippage if volatility
data is unavailable.
"""

from __future__ import annotations

import statistics
from typing import Optional

import httpx

from config.constants import DEXSCREENER_TOKEN_URL, MAX_SLIPPAGE_PCT
from core.logger import get_logger
from trading.slippage import calculate_slippage

logger = get_logger(__name__)

# Volatility thresholds and their slippage additions
# (max_volatility_pct, extra_slippage_pct)
_VOLATILITY_BANDS = [
    (2.0,  0.0),   # <2% vol → no extra slippage
    (5.0,  1.5),   # 2-5% vol → +1.5%
    (10.0, 3.0),   # 5-10% vol → +3%
    (20.0, 5.0),   # 10-20% vol → +5%
    (50.0, 8.0),   # 20-50% vol → +8%
    (float("inf"), 12.0),  # >50% → +12%
]


async def _fetch_volatility_pct(token_address: str, chain: str) -> Optional[float]:
    """
    Fetch recent price volatility for a token from DexScreener.

    Measures the coefficient of variation (stdev/mean * 100) of the
    5-minute price changes over the last hour.

    Args:
        token_address: Token contract address / mint.
        chain: Chain name ('ETH', 'BSC', 'SOL').

    Returns:
        Volatility percentage, or None if data unavailable.
    """
    url = DEXSCREENER_TOKEN_URL.format(address=token_address)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url)
            data = resp.json()

        pairs = data.get("pairs", [])
        if not pairs:
            return None

        # Use the most liquid pair
        pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))

        # Extract price change metrics from DexScreener
        price_change = pair.get("priceChange", {})
        h1_change = abs(float(price_change.get("h1", 0) or 0))
        m5_change = abs(float(price_change.get("m5", 0) or 0))
        h6_change = abs(float(price_change.get("h6", 0) or 0))

        # Estimate volatility from the available data points
        # Weight recent changes more heavily
        if m5_change > 0 or h1_change > 0:
            # Project m5 volatility to per-hour scale (sqrt-time scaling)
            m5_hourly = m5_change * (12 ** 0.5)  # 12 five-min periods per hour
            volatility = max(m5_hourly, h1_change, h6_change / 3)
            logger.debug(
                "Token %s volatility: m5=%.2f%%, h1=%.2f%%, h6=%.2f%% → est=%.2f%%",
                token_address[:10], m5_change, h1_change, h6_change, volatility,
            )
            return volatility

        return None

    except Exception as exc:
        logger.debug("Smart slippage volatility fetch failed for %s: %s", token_address[:10], exc)
        return None


def _volatility_to_extra_slippage(volatility_pct: float) -> float:
    """Map a volatility percentage to extra slippage using predefined bands."""
    for max_vol, extra in _VOLATILITY_BANDS:
        if volatility_pct <= max_vol:
            return extra
    return _VOLATILITY_BANDS[-1][1]


async def calculate_smart_slippage(
    amount_usd: float,
    max_slippage_pct: float,
    chain: str,
    token_address: str,
    token_liquidity_usd: float,
    smart_enabled: bool = True,
) -> float:
    """
    Calculate dynamic slippage adjusted for on-chain pool volatility.

    If smart slippage is disabled or volatility data is unavailable,
    falls back to the standard liquidity-based slippage calculation.

    Args:
        amount_usd: USD value of the trade.
        max_slippage_pct: User's configured maximum slippage %.
        chain: Chain name.
        token_address: Token contract address.
        token_liquidity_usd: Pool liquidity in USD.
        smart_enabled: Whether smart slippage is enabled for this user.

    Returns:
        Effective slippage percentage (capped at MAX_SLIPPAGE_PCT).
    """
    # Start with the base liquidity-based slippage
    base_slippage = calculate_slippage(
        amount_usd, max_slippage_pct, chain, token_liquidity_usd
    )

    if not smart_enabled:
        return base_slippage

    # Fetch on-chain volatility
    volatility = await _fetch_volatility_pct(token_address, chain)

    if volatility is None:
        logger.debug("No volatility data — using base slippage %.1f%%", base_slippage)
        return base_slippage

    extra = _volatility_to_extra_slippage(volatility)

    smart_slippage = base_slippage + extra
    capped = min(smart_slippage, MAX_SLIPPAGE_PCT)

    if extra > 0:
        logger.info(
            "Smart slippage: vol=%.1f%% → +%.1f%% extra → final=%.1f%% (base=%.1f%%)",
            volatility, extra, capped, base_slippage,
        )

    return round(capped, 2)
