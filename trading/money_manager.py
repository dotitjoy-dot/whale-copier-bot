"""
Money Manager — calculates trade size based on user's copy_config.
Supports fixed USD amount, percent of balance, and mirror (whale proportional) modes.
"""

from __future__ import annotations

from typing import Dict

from config.constants import MIN_TRADE_USD
from core.logger import get_logger

logger = get_logger(__name__)


def size_trade(
    config: Dict,
    whale_amount_usd: float,
    user_balance_usd: float,
) -> float:
    """
    Calculate the USD amount to trade based on user's money management config.

    Modes:
        'fixed'   → min(config.fixed_amount_usd, config.max_position_usd)
        'percent' → min(user_balance_usd * config.percent_of_balance / 100,
                        config.max_position_usd)
        'mirror'  → min(whale_amount_usd * config.mirror_multiplier,
                        config.max_position_usd)

    Always returns 0 if the calculated amount is below the minimum viable trade ($1).

    Args:
        config: copy_config dict from the database (with all fields).
        whale_amount_usd: USD value of the whale's detected trade.
        user_balance_usd: User's current portfolio balance in USD.

    Returns:
        Trade size in USD, or 0.0 if below minimum or invalid mode.
    """
    mode = config.get("trade_size_mode", "fixed")
    max_pos = float(config.get("max_position_usd", 100.0))

    if mode == "fixed":
        amount = min(float(config.get("fixed_amount_usd", 10.0)), max_pos)

    elif mode == "percent":
        pct = float(config.get("percent_of_balance", 5.0))
        if user_balance_usd <= 0:
            logger.warning("User balance is 0, cannot calculate percent-mode trade size")
            return 0.0
        amount = min(user_balance_usd * pct / 100.0, max_pos)

    elif mode == "mirror":
        multiplier = float(config.get("mirror_multiplier", 1.0))
        if whale_amount_usd <= 0:
            logger.warning("Whale trade amount is 0, cannot mirror")
            return 0.0
        amount = min(whale_amount_usd * multiplier, max_pos)

    else:
        logger.error("Unknown trade_size_mode: %s", mode)
        return 0.0

    if amount < MIN_TRADE_USD:
        logger.debug(
            "Calculated trade size $%.2f is below minimum viable $%.2f — skipping",
            amount, MIN_TRADE_USD
        )
        return 0.0

    return round(amount, 6)
