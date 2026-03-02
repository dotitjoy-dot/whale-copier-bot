"""
Unit tests for the Whale Copy Bot.
Covers encryption, database CRUD, money manager, slippage, risk checks, and gas manager.
Run with: pytest tests/test_core.py -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────────────────────
# Encryption Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEncryption:
    """Test AES-256-GCM encryption/decryption of private keys."""

    def test_encrypt_decrypt_roundtrip(self):
        from core.encryption import encrypt_private_key, decrypt_private_key

        passphrase = "test_passphrase_123!"
        private_key = "0x4c0883a69102937d6231471b5dbb6204fe512961708279f3c4e1b3a4f4e912ab"

        encrypted = encrypt_private_key(private_key, passphrase)
        assert encrypted != private_key
        assert len(encrypted) > 20  # Base64 encoded should be substantial

        decrypted = decrypt_private_key(encrypted, passphrase)
        assert decrypted == private_key

    def test_wrong_passphrase_fails(self):
        from core.encryption import encrypt_private_key, decrypt_private_key

        encrypted = encrypt_private_key("my_secret_key", "correct_pass")
        with pytest.raises(Exception):
            decrypt_private_key(encrypted, "wrong_pass")

    def test_different_passphrases_different_output(self):
        from core.encryption import encrypt_private_key

        key = "0xabc123"
        e1 = encrypt_private_key(key, "pass1")
        e2 = encrypt_private_key(key, "pass2")
        assert e1 != e2


# ─────────────────────────────────────────────────────────────────────────────
# Database Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabase:
    """Test database CRUD operations using a temporary SQLite file."""

    @pytest.fixture
    async def db(self):
        from core.database import Database

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        db = Database(db_path)
        await db.initialize()
        yield db
        await db.close()
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_ensure_and_get_user(self, db):
        await db.ensure_user(12345, "testuser", False)
        user = await db.get_user(12345)
        assert user is not None
        assert user["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_add_and_list_wallets(self, db):
        await db.ensure_user(12345, "test")
        wid = await db.add_wallet(12345, "ETH", "0xabc", "encrypted_pk", "My Wallet")
        assert wid > 0

        wallets = await db.list_wallets(12345)
        assert len(wallets) == 1
        assert wallets[0]["chain"] == "ETH"
        assert wallets[0]["label"] == "My Wallet"

    @pytest.mark.asyncio
    async def test_add_and_list_whales(self, db):
        await db.ensure_user(12345, "test")
        whale_id = await db.add_whale(12345, "ETH", "0xwhale", "Smart Money")
        assert whale_id > 0

        whales = await db.list_whales(12345)
        assert len(whales) == 1
        assert whales[0]["label"] == "Smart Money"

    @pytest.mark.asyncio
    async def test_remove_whale(self, db):
        await db.ensure_user(12345, "test")
        whale_id = await db.add_whale(12345, "ETH", "0xwhale")
        await db.remove_whale(whale_id, 12345)
        whales = await db.list_whales(12345)
        assert len(whales) == 0

    @pytest.mark.asyncio
    async def test_copy_config_upsert(self, db):
        await db.ensure_user(12345, "test")
        # First upsert creates the record
        await db.upsert_copy_config(12345, "ETH", is_enabled=1, fixed_amount_usd=25.0)
        config = await db.get_copy_config(12345, "ETH")
        assert config is not None
        assert config["is_enabled"] == 1
        assert config["fixed_amount_usd"] == 25.0

        # Second upsert updates
        await db.upsert_copy_config(12345, "ETH", fixed_amount_usd=50.0)
        config = await db.get_copy_config(12345, "ETH")
        assert config["fixed_amount_usd"] == 50.0

    @pytest.mark.asyncio
    async def test_record_and_list_trades(self, db):
        await db.ensure_user(12345, "test")
        tid = await db.record_trade(
            telegram_id=12345, chain="ETH", whale_address="0xwhale",
            whale_tx_hash="0xtx", token_address="0xtoken", token_symbol="MEME",
            action="BUY", amount_in_usd=25.0, status="CONFIRMED",
        )
        assert tid > 0

        trades = await db.list_trades(12345, "ETH")
        assert len(trades) == 1
        assert trades[0]["token_symbol"] == "MEME"

    @pytest.mark.asyncio
    async def test_blacklist(self, db):
        await db.ensure_user(12345, "test")
        await db.add_to_blacklist(12345, "ETH", "0xbadtoken")

        assert await db.is_blacklisted(12345, "0xbadtoken") is True
        assert await db.is_blacklisted(12345, "0xgoodtoken") is False

        bl = await db.list_blacklist(12345)
        assert len(bl) == 1

    @pytest.mark.asyncio
    async def test_daily_stats(self, db):
        await db.ensure_user(12345, "test")
        await db.upsert_daily_stats(12345, "2026-01-01", trades_count=5, wins=3)
        stats = await db.get_daily_stats(12345, "2026-01-01")
        assert stats is not None
        assert stats["trades_count"] == 5
        assert stats["wins"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# Money Manager Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestMoneyManager:
    """Test trade size calculation."""

    def test_fixed_mode(self):
        from trading.money_manager import size_trade

        config = {"trade_size_mode": "fixed", "fixed_amount_usd": 25.0, "max_position_usd": 100.0}
        result = size_trade(config, 1000.0, 500.0)
        assert result == 25.0

    def test_fixed_mode_capped_by_max(self):
        from trading.money_manager import size_trade

        config = {"trade_size_mode": "fixed", "fixed_amount_usd": 200.0, "max_position_usd": 100.0}
        result = size_trade(config, 1000.0, 500.0)
        assert result == 100.0

    def test_percent_mode(self):
        from trading.money_manager import size_trade

        config = {"trade_size_mode": "percent", "percent_of_balance": 10.0, "max_position_usd": 1000.0}
        result = size_trade(config, 1000.0, 500.0)
        assert result == 50.0  # 10% of 500

    def test_mirror_mode(self):
        from trading.money_manager import size_trade

        config = {"trade_size_mode": "mirror", "mirror_multiplier": 0.5, "max_position_usd": 1000.0}
        result = size_trade(config, 200.0, 500.0)
        assert result == 100.0  # 0.5 × 200

    def test_below_minimum_returns_zero(self):
        from trading.money_manager import size_trade

        config = {"trade_size_mode": "fixed", "fixed_amount_usd": 0.5, "max_position_usd": 100.0}
        result = size_trade(config, 1000.0, 500.0)
        assert result == 0.0  # Below MIN_TRADE_USD ($1)


# ─────────────────────────────────────────────────────────────────────────────
# Slippage Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSlippage:
    """Test dynamic slippage calculator."""

    def test_base_slippage(self):
        from trading.slippage import calculate_slippage

        result = calculate_slippage(10.0, 5.0, "ETH", 1_000_000)
        assert result == 5.0  # No adjustments needed

    def test_large_trade_adds_slippage(self):
        from trading.slippage import calculate_slippage

        # Trade > 1% of liquidity
        result = calculate_slippage(600, 5.0, "ETH", 50_000)
        assert result > 5.0

    def test_unknown_liquidity_adds_extra(self):
        from trading.slippage import calculate_slippage

        result = calculate_slippage(10.0, 5.0, "ETH", 0)
        assert result == 10.0  # 5 + 5 for unknown

    def test_hard_cap_at_25(self):
        from trading.slippage import calculate_slippage

        result = calculate_slippage(10000, 20.0, "ETH", 100)
        assert result == 25.0


# ─────────────────────────────────────────────────────────────────────────────
# TX Classifier Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTxClassifier:
    """Test EVM transaction classification."""

    def test_non_router_tx_returns_none(self):
        from monitor.tx_classifier import classify_evm_tx
        from chains.base_chain import RawTx

        tx = RawTx(
            chain="ETH", tx_hash="0x123", block_number=1,
            from_address="0xwhale", to_address="0xrandom",
            value=0, input_data="0x12345678" + "00" * 64,
            timestamp=100,
        )
        result = classify_evm_tx(tx, {"0xrouter": "Uniswap"})
        assert result is None

    def test_empty_input_returns_none(self):
        from monitor.tx_classifier import classify_evm_tx
        from chains.base_chain import RawTx

        tx = RawTx(
            chain="ETH", tx_hash="0x123", block_number=1,
            from_address="0xwhale", to_address="0xrouter",
            value=0, input_data="0x",
            timestamp=100,
        )
        result = classify_evm_tx(tx, {"0xrouter": "Uniswap"})
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Auth Middleware Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAuthMiddleware:
    """Test auth middleware logic."""

    def test_authorized_user(self):
        from bot.middlewares import AuthMiddleware

        auth = AuthMiddleware(allowed_ids={111, 222}, admin_id=111)
        assert auth.is_authorized(111) is True
        assert auth.is_authorized(999) is False

    def test_admin_check(self):
        from bot.middlewares import AuthMiddleware

        auth = AuthMiddleware(allowed_ids={111}, admin_id=111)
        assert auth.is_admin(111) is True
        assert auth.is_admin(222) is False

    def test_rate_limit(self):
        from bot.middlewares import AuthMiddleware

        auth = AuthMiddleware(allowed_ids={111}, admin_id=111, rate_limit=3)
        assert auth.check_rate_limit(111) is True
        assert auth.check_rate_limit(111) is True
        assert auth.check_rate_limit(111) is True
        assert auth.check_rate_limit(111) is False  # 4th should fail

    def test_session_passphrase(self):
        from bot.middlewares import AuthMiddleware

        auth = AuthMiddleware(allowed_ids={111}, admin_id=111, auto_lock_minutes=30)
        auth.set_session_passphrase(111, "my_pass")
        assert auth.get_session_passphrase(111) == "my_pass"

    def test_session_clear(self):
        from bot.middlewares import AuthMiddleware

        auth = AuthMiddleware(allowed_ids={111}, admin_id=111)
        auth.set_session_passphrase(111, "my_pass")
        auth.clear_session(111)
        assert auth.get_session_passphrase(111) == ""
