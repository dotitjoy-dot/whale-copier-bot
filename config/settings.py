"""
Pydantic settings model for Whale Copy Bot.
Loads all configuration from environment variables / .env file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────
    telegram_bot_token: str
    allowed_user_ids: str  # Comma-separated, parsed below
    admin_telegram_id: int

    # ── Database ──────────────────────────────
    db_path: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "whale_bot.db")

    # ── Encryption ────────────────────────────
    encryption_secret: str = ""

    # ── RPC Endpoints ─────────────────────────
    eth_rpc_urls: str = "https://eth.llamarpc.com,https://rpc.ankr.com/eth"
    bsc_rpc_urls: str = "https://bsc-dataseed.binance.org,https://rpc.ankr.com/bsc"
    sol_rpc_urls: str = "https://api.mainnet-beta.solana.com,https://rpc.ankr.com/solana"

    # ── Optional API Keys ─────────────────────
    etherscan_api_key: str = ""
    bscscan_api_key: str = ""

    # ── Bot Settings ──────────────────────────
    poll_interval_seconds: int = 15
    auto_lock_minutes: int = 10
    rate_limit_per_minute: int = 30

    # ── Logging ───────────────────────────────
    log_level: str = "INFO"
    log_file: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "whale_bot.log")

    @property
    def allowed_user_ids_list(self) -> List[int]:
        """Parse comma-separated allowed user IDs into a list of integers."""
        return [int(uid.strip()) for uid in self.allowed_user_ids.split(",") if uid.strip()]

    @property
    def eth_rpc_list(self) -> List[str]:
        """Parse ETH RPC URLs into a list."""
        return [url.strip() for url in self.eth_rpc_urls.split(",") if url.strip()]

    @property
    def bsc_rpc_list(self) -> List[str]:
        """Parse BSC RPC URLs into a list."""
        return [url.strip() for url in self.bsc_rpc_urls.split(",") if url.strip()]

    @property
    def sol_rpc_list(self) -> List[str]:
        """Parse Solana RPC URLs into a list."""
        return [url.strip() for url in self.sol_rpc_urls.split(",") if url.strip()]

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return _settings


# Module-level singleton — load once at import
_settings = Settings()
