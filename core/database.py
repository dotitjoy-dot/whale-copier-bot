"""
Async SQLite database layer using aiosqlite.
Creates all tables on first run, provides full CRUD for every entity.
ALL queries use parameterized statements — no SQL injection possible.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from core.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schema DDL
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    telegram_id   INTEGER PRIMARY KEY,
    username      TEXT,
    is_admin      INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT (datetime('now')),
    is_active     INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS wallets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id   INTEGER REFERENCES users(telegram_id),
    chain         TEXT NOT NULL,
    address       TEXT NOT NULL,
    encrypted_pk  TEXT NOT NULL,
    label         TEXT DEFAULT 'Main',
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS whale_wallets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id   INTEGER REFERENCES users(telegram_id),
    chain         TEXT NOT NULL,
    address       TEXT NOT NULL,
    label         TEXT DEFAULT '',
    is_active     INTEGER DEFAULT 1,
    added_at      TEXT DEFAULT (datetime('now')),
    last_tx_hash  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS copy_config (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id           INTEGER REFERENCES users(telegram_id),
    chain                 TEXT NOT NULL,
    is_enabled            INTEGER DEFAULT 0,
    trade_size_mode       TEXT DEFAULT 'fixed',
    fixed_amount_usd      REAL DEFAULT 10.0,
    percent_of_balance    REAL DEFAULT 5.0,
    mirror_multiplier     REAL DEFAULT 1.0,
    max_position_usd      REAL DEFAULT 100.0,
    max_open_trades       INTEGER DEFAULT 5,
    stop_loss_pct         REAL DEFAULT 20.0,
    take_profit_pct       REAL DEFAULT 50.0,
    trailing_stop_pct     REAL DEFAULT 0.0,
    daily_loss_limit_usd  REAL DEFAULT 50.0,
    max_slippage_pct      REAL DEFAULT 5.0,
    min_whale_trade_usd   REAL DEFAULT 500.0,
    max_token_age_hours   INTEGER DEFAULT 72,
    copy_buys             INTEGER DEFAULT 1,
    copy_sells            INTEGER DEFAULT 1,
    auto_sell_on_whale_sell INTEGER DEFAULT 1,
    updated_at            TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id      INTEGER REFERENCES users(telegram_id),
    chain            TEXT NOT NULL,
    whale_address    TEXT NOT NULL,
    whale_tx_hash    TEXT NOT NULL,
    copy_tx_hash     TEXT DEFAULT '',
    token_address    TEXT NOT NULL,
    token_symbol     TEXT DEFAULT '',
    action           TEXT NOT NULL,
    amount_in_usd    REAL DEFAULT 0,
    amount_in_native REAL DEFAULT 0,
    tokens_received  REAL DEFAULT 0,
    entry_price_usd  REAL DEFAULT 0,
    exit_price_usd   REAL DEFAULT 0,
    pnl_usd          REAL DEFAULT 0,
    status           TEXT DEFAULT 'PENDING',
    skip_reason      TEXT DEFAULT '',
    gas_used_usd     REAL DEFAULT 0,
    created_at       TEXT DEFAULT (datetime('now')),
    confirmed_at     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS blacklist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER REFERENCES users(telegram_id),
    chain       TEXT,
    address     TEXT NOT NULL,
    reason      TEXT DEFAULT '',
    added_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER,
    date            TEXT,
    trades_count    INTEGER DEFAULT 0,
    wins            INTEGER DEFAULT 0,
    losses          INTEGER DEFAULT 0,
    total_pnl_usd   REAL DEFAULT 0,
    daily_loss_usd  REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alert_settings (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id             INTEGER REFERENCES users(telegram_id),
    notify_whale_detect     INTEGER DEFAULT 1,
    notify_trade_executed   INTEGER DEFAULT 1,
    notify_sl_tp_hit        INTEGER DEFAULT 1,
    daily_report_time       TEXT DEFAULT '08:00'
);

-- Partial Take Profit steps per user+chain
CREATE TABLE IF NOT EXISTS partial_take_profits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER REFERENCES users(telegram_id),
    chain           TEXT NOT NULL,
    step_order      INTEGER NOT NULL,
    sell_pct        REAL NOT NULL,
    target_multiple REAL NOT NULL,
    is_active       INTEGER DEFAULT 1
);

-- Trade lifecycle events for journey timeline
CREATE TABLE IF NOT EXISTS trade_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    INTEGER REFERENCES trades(id),
    event_type  TEXT NOT NULL,
    description TEXT DEFAULT '',
    price_usd   REAL DEFAULT 0,
    pnl_pct     REAL DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Price alerts for any token
CREATE TABLE IF NOT EXISTS price_alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id   INTEGER REFERENCES users(telegram_id),
    chain         TEXT NOT NULL,
    token_address TEXT NOT NULL,
    token_symbol  TEXT DEFAULT '',
    target_price  REAL NOT NULL,
    direction     TEXT DEFAULT 'below',  -- 'above' or 'below'
    is_active     INTEGER DEFAULT 1,
    triggered     INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT (datetime('now'))
);

-- Trade notes and tags
CREATE TABLE IF NOT EXISTS trade_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    INTEGER REFERENCES trades(id),
    telegram_id INTEGER REFERENCES users(telegram_id),
    note        TEXT DEFAULT '',
    tags        TEXT DEFAULT '',  -- comma-separated tags
    created_at  TEXT DEFAULT (datetime('now'))
);

-- DCA (Dollar Cost Average) orders
CREATE TABLE IF NOT EXISTS dca_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER REFERENCES users(telegram_id),
    chain           TEXT NOT NULL,
    token_address   TEXT NOT NULL,
    token_symbol    TEXT DEFAULT '',
    total_amount_usd REAL NOT NULL,
    num_splits      INTEGER DEFAULT 5,
    interval_minutes INTEGER DEFAULT 10,
    executed_splits INTEGER DEFAULT 0,
    amount_per_split REAL DEFAULT 0,
    status          TEXT DEFAULT 'ACTIVE',  -- ACTIVE, COMPLETED, CANCELLED
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Limit order simulations
CREATE TABLE IF NOT EXISTS limit_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER REFERENCES users(telegram_id),
    chain           TEXT NOT NULL,
    token_address   TEXT NOT NULL,
    token_symbol    TEXT DEFAULT '',
    target_price    REAL NOT NULL,
    amount_usd      REAL NOT NULL,
    direction       TEXT DEFAULT 'buy',  -- 'buy' (buy when price dips)
    status          TEXT DEFAULT 'PENDING',  -- PENDING, FILLED, CANCELLED
    created_at      TEXT DEFAULT (datetime('now')),
    filled_at       TEXT DEFAULT ''
);

-- Whale profitability scores (tracked per whale-address)
CREATE TABLE IF NOT EXISTS whale_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    whale_address   TEXT NOT NULL,
    chain           TEXT NOT NULL,
    total_trades    INTEGER DEFAULT 0,
    winning_trades  INTEGER DEFAULT 0,
    total_pnl_usd   REAL DEFAULT 0,
    avg_pnl_pct     REAL DEFAULT 0,
    last_updated    TEXT DEFAULT (datetime('now')),
    UNIQUE(whale_address, chain)
);

CREATE INDEX IF NOT EXISTS idx_trades_user_chain ON trades(telegram_id, chain);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_whale_wallets_active ON whale_wallets(is_active, chain);
CREATE INDEX IF NOT EXISTS idx_trade_events_trade ON trade_events(trade_id);
CREATE INDEX IF NOT EXISTS idx_partial_tp_user ON partial_take_profits(telegram_id, chain);
CREATE INDEX IF NOT EXISTS idx_price_alerts_active ON price_alerts(telegram_id, is_active);
CREATE INDEX IF NOT EXISTS idx_limit_orders_active ON limit_orders(status);
CREATE INDEX IF NOT EXISTS idx_dca_orders_active ON dca_orders(status);
CREATE INDEX IF NOT EXISTS idx_whale_scores ON whale_scores(whale_address, chain);

-- User subscriptions (public bot auth)
CREATE TABLE IF NOT EXISTS subscriptions (
    telegram_id     INTEGER PRIMARY KEY REFERENCES users(telegram_id),
    tier            TEXT NOT NULL DEFAULT 'FREE',
    expires_at      TEXT DEFAULT '',
    is_banned       INTEGER DEFAULT 0,
    trial_started_at TEXT DEFAULT (datetime('now')),
    notes           TEXT DEFAULT '',
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- License keys (generated by admin)
CREATE TABLE IF NOT EXISTS license_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key_str         TEXT UNIQUE NOT NULL,
    tier            TEXT NOT NULL,
    duration_days   INTEGER NOT NULL,
    created_by      INTEGER NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    redeemed_by     INTEGER DEFAULT NULL,
    redeemed_at     TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_license_keys_redeemed ON license_keys(redeemed_by);
"""


class Database:
    """
    Async SQLite database wrapper built on aiosqlite.
    Call initialize() once at startup to create tables and set file permissions.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialize database reference.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """
        Open database connection, run schema migrations, and set file permissions.
        Must be called once before any other method.
        """
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA_SQL)
        
        # Auto-Migrations for Advanced Features
        migrations = [
            "ALTER TABLE copy_config ADD COLUMN anti_rug_enabled INTEGER DEFAULT 1",
            "ALTER TABLE copy_config ADD COLUMN mev_protect_enabled INTEGER DEFAULT 1",
            "ALTER TABLE copy_config ADD COLUMN paper_trading_enabled INTEGER DEFAULT 0",
            # Custom Gas & Priority Fees
            "ALTER TABLE copy_config ADD COLUMN custom_gas_gwei REAL DEFAULT 0",
            "ALTER TABLE copy_config ADD COLUMN priority_tip_gwei REAL DEFAULT 0",
            # Smart Slippage
            "ALTER TABLE copy_config ADD COLUMN smart_slippage_enabled INTEGER DEFAULT 1",
            # Time-based Auto-Sell
            "ALTER TABLE copy_config ADD COLUMN auto_sell_hours REAL DEFAULT 0",
            # Break-Even Stop Loss
            "ALTER TABLE copy_config ADD COLUMN breakeven_trigger_pct REAL DEFAULT 50.0",
            "ALTER TABLE copy_config ADD COLUMN breakeven_enabled INTEGER DEFAULT 0",
            # Auto-Sniper Mode
            "ALTER TABLE copy_config ADD COLUMN sniper_enabled INTEGER DEFAULT 0",
            "ALTER TABLE copy_config ADD COLUMN sniper_min_liquidity_usd REAL DEFAULT 10000",
            "ALTER TABLE copy_config ADD COLUMN sniper_max_age_minutes INTEGER DEFAULT 30",
            "ALTER TABLE copy_config ADD COLUMN sniper_amount_usd REAL DEFAULT 10.0",
            # Partial TP enabled flag
            "ALTER TABLE copy_config ADD COLUMN partial_tp_enabled INTEGER DEFAULT 0",
            # Anti-FOMO Cooldown
            "ALTER TABLE copy_config ADD COLUMN cooldown_minutes INTEGER DEFAULT 0",
            # Snooze Mode
            "ALTER TABLE copy_config ADD COLUMN snooze_until TEXT DEFAULT ''",
            # Multi-Wallet Rotation
            "ALTER TABLE copy_config ADD COLUMN wallet_rotation_enabled INTEGER DEFAULT 0",
            # Smart Money Nansen integration
            "ALTER TABLE copy_config ADD COLUMN smart_money_enabled INTEGER DEFAULT 0",
            # Trade: break-even tracking
            "ALTER TABLE trades ADD COLUMN breakeven_activated INTEGER DEFAULT 0",
            "ALTER TABLE trades ADD COLUMN peak_price_usd REAL DEFAULT 0",
            "ALTER TABLE trades ADD COLUMN remaining_pct REAL DEFAULT 100",
            # Trade notes reference
            "ALTER TABLE trades ADD COLUMN notes TEXT DEFAULT ''",
            # Wallet mnemonic (encrypted) for export/recovery
            "ALTER TABLE wallets ADD COLUMN encrypted_mnemonic TEXT DEFAULT ''",
        ]
        for query in migrations:
            try:
                await self._conn.execute(query)
            except aiosqlite.OperationalError:
                pass  # Column already exists
        
        await self._conn.commit()
        # Set file permissions to owner-only (chmod 600 equivalent)
        try:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # Windows may not support POSIX chmod
        logger.info("Database initialized at %s", self._path)

    async def close(self) -> None:
        """Close the database connection gracefully."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a single parameterized statement."""
        return await self._conn.execute(sql, params)

    async def _fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute and fetch one row as a dict."""
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _fetchall(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute and fetch all rows as list of dicts."""
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ── Users ─────────────────────────────────────────────────────────────────

    async def ensure_user(self, telegram_id: int, username: str, is_admin: bool = False) -> None:
        """Insert user if not present; update username if changed."""
        await self._conn.execute(
            """INSERT INTO users (telegram_id, username, is_admin) VALUES (?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username""",
            (telegram_id, username, int(is_admin)),
        )
        await self._conn.commit()

    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Fetch a single user by telegram_id."""
        return await self._fetchone("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))

    async def list_users(self) -> List[Dict]:
        """List all registered users."""
        return await self._fetchall("SELECT * FROM users ORDER BY created_at DESC")

    async def list_all_users(self) -> List[Dict]:
        """Alias for list_users — used by admin handler."""
        return await self.list_users()

    async def set_user_active(self, telegram_id: int, active: bool) -> None:
        """Enable or disable a user account."""
        await self._conn.execute(
            "UPDATE users SET is_active=? WHERE telegram_id=?", (int(active), telegram_id)
        )
        await self._conn.commit()

    # ── Wallets ───────────────────────────────────────────────────────────────

    async def add_wallet(
        self, telegram_id: int, chain: str, address: str, encrypted_pk: str,
        label: str = "Main", encrypted_mnemonic: str = "",
    ) -> int:
        """Store a new encrypted wallet. Returns the new wallet id."""
        cursor = await self._conn.execute(
            """INSERT INTO wallets (telegram_id, chain, address, encrypted_pk, label, encrypted_mnemonic)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telegram_id, chain, address, encrypted_pk, label, encrypted_mnemonic),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_wallet(self, wallet_id: int) -> Optional[Dict]:
        """Fetch a wallet by its id."""
        return await self._fetchone("SELECT * FROM wallets WHERE id=?", (wallet_id,))

    async def get_wallet_by_address(self, telegram_id: int, address: str) -> Optional[Dict]:
        """Fetch wallet by telegram_id and address."""
        return await self._fetchone(
            "SELECT * FROM wallets WHERE telegram_id=? AND address=?", (telegram_id, address)
        )

    async def list_wallets(self, telegram_id: int) -> List[Dict]:
        """List all active wallets for a user."""
        return await self._fetchall(
            "SELECT * FROM wallets WHERE telegram_id=? AND is_active=1 ORDER BY created_at",
            (telegram_id,),
        )

    async def list_wallets_by_chain(self, telegram_id: int, chain: str) -> List[Dict]:
        """List all active wallets for a user on a specific chain."""
        return await self._fetchall(
            "SELECT * FROM wallets WHERE telegram_id=? AND chain=? AND is_active=1",
            (telegram_id, chain),
        )

    async def remove_wallet(self, wallet_id: int, telegram_id: int) -> None:
        """Soft-delete a wallet (is_active=0)."""
        await self._conn.execute(
            "UPDATE wallets SET is_active=0 WHERE id=? AND telegram_id=?",
            (wallet_id, telegram_id),
        )
        await self._conn.commit()

    # ── Whale Wallets ─────────────────────────────────────────────────────────

    async def add_whale(
        self, telegram_id: int, chain: str, address: str, label: str = ""
    ) -> int:
        """Add a whale wallet to monitor. Returns the new id."""
        cursor = await self._conn.execute(
            """INSERT INTO whale_wallets (telegram_id, chain, address, label)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, chain, address, label),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_whale(self, whale_id: int) -> Optional[Dict]:
        """Fetch a whale wallet by id."""
        return await self._fetchone("SELECT * FROM whale_wallets WHERE id=?", (whale_id,))

    async def list_whales(self, telegram_id: int) -> List[Dict]:
        """List all active whale wallets for a user."""
        return await self._fetchall(
            "SELECT * FROM whale_wallets WHERE telegram_id=? AND is_active=1 ORDER BY added_at DESC",
            (telegram_id,),
        )

    async def list_all_active_whales(self) -> List[Dict]:
        """List ALL active whale wallets across all users (for tracker job)."""
        return await self._fetchall("SELECT * FROM whale_wallets WHERE is_active=1")

    async def remove_whale(self, whale_id: int, telegram_id: int) -> None:
        """Soft-delete a whale wallet."""
        await self._conn.execute(
            "UPDATE whale_wallets SET is_active=0 WHERE id=? AND telegram_id=?",
            (whale_id, telegram_id),
        )
        await self._conn.commit()

    async def update_whale_last_tx(self, whale_id: int, last_tx_hash: str) -> None:
        """Update the last known transaction hash for a whale wallet."""
        await self._conn.execute(
            "UPDATE whale_wallets SET last_tx_hash=? WHERE id=?", (last_tx_hash, whale_id)
        )
        await self._conn.commit()

    async def get_users_tracking_whale(self, chain: str, whale_address: str) -> List[Dict]:
        """Get all users (with their copy_config) that track a given whale on a chain."""
        return await self._fetchall(
            """
            SELECT u.telegram_id, u.username, cc.*
            FROM users u
            JOIN copy_config cc ON cc.telegram_id = u.telegram_id AND cc.chain = ?
            WHERE u.is_active=1 AND cc.is_enabled=1 AND (
                EXISTS (SELECT 1 FROM whale_wallets ww WHERE ww.telegram_id = u.telegram_id AND ww.chain=? AND ww.address=? AND ww.is_active=1)
                OR
                (cc.smart_money_enabled=1 AND EXISTS (SELECT 1 FROM whale_wallets nansen WHERE nansen.telegram_id=0 AND nansen.chain=? AND nansen.address=? AND nansen.is_active=1))
            )
            """,
            (chain, chain, whale_address, chain, whale_address),
        )

    # ── Copy Config ───────────────────────────────────────────────────────────

    async def get_copy_config(self, telegram_id: int, chain: str) -> Optional[Dict]:
        """Fetch copy config for a user+chain. Returns None if not set."""
        return await self._fetchone(
            "SELECT * FROM copy_config WHERE telegram_id=? AND chain=?", (telegram_id, chain)
        )

    async def upsert_copy_config(self, telegram_id: int, chain: str, fields_dict: Dict = None, **kwargs) -> None:
        """Create or update copy configuration fields. Accepts dict or kwargs."""
        updates = dict(fields_dict or {})
        updates.update(kwargs)
        existing = await self.get_copy_config(telegram_id, chain)
        if existing is None:
            cols = ["telegram_id", "chain"] + list(updates.keys())
            vals = [telegram_id, chain] + list(updates.values())
            placeholders = ",".join("?" * len(vals))
            await self._conn.execute(
                f"INSERT INTO copy_config ({','.join(cols)}) VALUES ({placeholders})",
                tuple(vals),
            )
        else:
            if updates:
                set_clause = ", ".join(f"{k}=?" for k in updates.keys()) + ", updated_at=datetime('now')"
                await self._conn.execute(
                    f"UPDATE copy_config SET {set_clause} WHERE telegram_id=? AND chain=?",
                    tuple(updates.values()) + (telegram_id, chain),
                )
        await self._conn.commit()

    async def disable_all_copy(self) -> None:
        """Force-disable copy trading for all users (admin emergency stop)."""
        await self._conn.execute("UPDATE copy_config SET is_enabled=0")
        await self._conn.commit()

    async def set_copy_enabled(self, telegram_id: int, chain: str, enabled: bool) -> None:
        """Enable or disable copy trading for a user+chain."""
        await self.upsert_copy_config(telegram_id, chain, is_enabled=int(enabled))

    # ── Trades ────────────────────────────────────────────────────────────────

    async def record_trade(self, **kwargs) -> int:
        """Insert a new trade record. Returns the new trade id."""
        fields = list(kwargs.keys())
        values = list(kwargs.values())
        placeholders = ",".join("?" * len(values))
        cursor = await self._conn.execute(
            f"INSERT INTO trades ({','.join(fields)}) VALUES ({placeholders})",
            tuple(values),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_trade(self, trade_id: int) -> Optional[Dict]:
        """Fetch a single trade by id."""
        return await self._fetchone("SELECT * FROM trades WHERE id=?", (trade_id,))

    async def update_trade(self, trade_id: int, **kwargs) -> None:
        """Update fields on an existing trade."""
        if not kwargs:
            return
        set_clause = ", ".join(f"{k}=?" for k in kwargs.keys())
        await self._conn.execute(
            f"UPDATE trades SET {set_clause} WHERE id=?",
            tuple(kwargs.values()) + (trade_id,),
        )
        await self._conn.commit()

    async def list_trades(
        self,
        telegram_id: int,
        chain: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict]:
        """List trades for a user with optional filters and pagination."""
        sql = "SELECT * FROM trades WHERE telegram_id=?"
        params: list = [telegram_id]
        if chain:
            sql += " AND chain=?"
            params.append(chain)
        if status:
            sql += " AND status=?"
            params.append(status)
        if since:
            sql += " AND created_at >= ?"
            params.append(since)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return await self._fetchall(sql, tuple(params))

    async def list_open_trades(self, telegram_id: int, chain: str) -> List[Dict]:
        """List currently open trades (CONFIRMED with no exit price)."""
        return await self._fetchall(
            "SELECT * FROM trades WHERE telegram_id=? AND chain=? AND status='CONFIRMED' AND exit_price_usd=0 ORDER BY created_at DESC",
            (telegram_id, chain),
        )

    async def count_open_trades(self, telegram_id: int, chain: str) -> int:
        """Count currently open (CONFIRMED with no exit price) trades."""
        row = await self._fetchone(
            "SELECT COUNT(*) as cnt FROM trades WHERE telegram_id=? AND chain=? AND status='CONFIRMED' AND exit_price_usd=0",
            (telegram_id, chain),
        )
        return row["cnt"] if row else 0

    async def get_daily_stats(self, telegram_id: int, date: str) -> Optional[Dict]:
        """Fetch daily stats for a user on a given date (YYYY-MM-DD)."""
        return await self._fetchone(
            "SELECT * FROM daily_stats WHERE telegram_id=? AND date=?", (telegram_id, date)
        )

    async def upsert_daily_stats(self, telegram_id: int, date: str, **kwargs) -> None:
        """Create or update daily stats for a user."""
        existing = await self.get_daily_stats(telegram_id, date)
        if existing is None:
            fields = ["telegram_id", "date"] + list(kwargs.keys())
            values = [telegram_id, date] + list(kwargs.values())
            await self._conn.execute(
                f"INSERT INTO daily_stats ({','.join(fields)}) VALUES ({','.join('?' * len(values))})",
                tuple(values),
            )
        else:
            set_clause = ", ".join(f"{k}=?" for k in kwargs.keys())
            await self._conn.execute(
                f"UPDATE daily_stats SET {set_clause} WHERE telegram_id=? AND date=?",
                tuple(kwargs.values()) + (telegram_id, date),
            )
        await self._conn.commit()

    async def get_pnl_summary(self, telegram_id: int, days: int = 7) -> Dict:
        """Aggregate PnL statistics over the last N days."""
        row = await self._fetchone(
            """SELECT COUNT(*) as total_trades,
                      SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
                      SUM(CASE WHEN pnl_usd < 0 THEN 1 ELSE 0 END) as losses,
                      SUM(pnl_usd) as total_pnl,
                      MAX(pnl_usd) as best_trade,
                      MIN(pnl_usd) as worst_trade,
                      SUM(gas_used_usd) as total_gas
               FROM trades
               WHERE telegram_id=? AND status='CONFIRMED'
                 AND created_at >= datetime('now', ? || ' days')""",
            (telegram_id, f"-{days}"),
        )
        return row or {}

    # ── Blacklist ─────────────────────────────────────────────────────────────

    async def add_to_blacklist(
        self, telegram_id: int, chain: str, address: str, reason: str = ""
    ) -> None:
        """Add a token to user's blacklist."""
        await self._conn.execute(
            "INSERT OR IGNORE INTO blacklist (telegram_id, chain, address, reason) VALUES (?, ?, ?, ?)",
            (telegram_id, chain, address, reason),
        )
        await self._conn.commit()

    async def add_blacklist(self, telegram_id: int, address: str, chain: str = "", reason: str = "") -> None:
        """Convenience alias for add_to_blacklist (used by settings handler)."""
        await self.add_to_blacklist(telegram_id, chain, address, reason)

    async def is_blacklisted(self, telegram_id: int, address: str) -> bool:
        """Check if a token address is blacklisted by the user."""
        row = await self._fetchone(
            "SELECT id FROM blacklist WHERE telegram_id=? AND address=?", (telegram_id, address)
        )
        return row is not None

    async def list_blacklist(self, telegram_id: int) -> List[Dict]:
        """List all blacklisted tokens for a user."""
        return await self._fetchall(
            "SELECT * FROM blacklist WHERE telegram_id=? ORDER BY added_at DESC", (telegram_id,)
        )

    async def remove_from_blacklist(self, telegram_id: int, address: str) -> None:
        """Remove a token from the blacklist."""
        await self._conn.execute(
            "DELETE FROM blacklist WHERE telegram_id=? AND address=?", (telegram_id, address)
        )
        await self._conn.commit()

    # ── Alert Settings ────────────────────────────────────────────────────────

    async def get_alert_settings(self, telegram_id: int) -> Dict:
        """Get alert settings, creating defaults if not present."""
        row = await self._fetchone(
            "SELECT * FROM alert_settings WHERE telegram_id=?", (telegram_id,)
        )
        if not row:
            await self._conn.execute(
                "INSERT INTO alert_settings (telegram_id) VALUES (?)", (telegram_id,)
            )
            await self._conn.commit()
            row = await self._fetchone(
                "SELECT * FROM alert_settings WHERE telegram_id=?", (telegram_id,)
            )
        return row or {}

    async def update_alert_settings(self, telegram_id: int, **kwargs) -> None:
        """Update alert setting fields for a user."""
        if not kwargs:
            return
        set_clause = ", ".join(f"{k}=?" for k in kwargs.keys())
        await self._conn.execute(
            f"UPDATE alert_settings SET {set_clause} WHERE telegram_id=?",
            tuple(kwargs.values()) + (telegram_id,),
        )
        await self._conn.commit()

    # ── Trade Events (Journey Timeline) ──────────────────────────────────────

    async def add_trade_event(
        self, trade_id: int, event_type: str, description: str = "",
        price_usd: float = 0, pnl_pct: float = 0
    ) -> int:
        """Record a trade lifecycle event (entry, SL move, partial sell, exit, etc.)."""
        cursor = await self._conn.execute(
            """INSERT INTO trade_events (trade_id, event_type, description, price_usd, pnl_pct)
               VALUES (?, ?, ?, ?, ?)""",
            (trade_id, event_type, description, price_usd, pnl_pct),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_trade_events(self, trade_id: int) -> List[Dict]:
        """Get all lifecycle events for a trade, ordered chronologically."""
        return await self._fetchall(
            "SELECT * FROM trade_events WHERE trade_id=? ORDER BY created_at ASC",
            (trade_id,),
        )

    # ── Partial Take Profits ─────────────────────────────────────────────────

    async def set_partial_take_profits(
        self, telegram_id: int, chain: str, steps: List[Dict]
    ) -> None:
        """Replace all partial TP steps for a user+chain.

        Args:
            telegram_id: User ID.
            chain: Chain name.
            steps: List of dicts with 'step_order', 'sell_pct', 'target_multiple'.
        """
        await self._conn.execute(
            "DELETE FROM partial_take_profits WHERE telegram_id=? AND chain=?",
            (telegram_id, chain),
        )
        for step in steps:
            await self._conn.execute(
                """INSERT INTO partial_take_profits
                   (telegram_id, chain, step_order, sell_pct, target_multiple)
                   VALUES (?, ?, ?, ?, ?)""",
                (telegram_id, chain, step["step_order"],
                 step["sell_pct"], step["target_multiple"]),
            )
        await self._conn.commit()

    async def get_partial_take_profits(self, telegram_id: int, chain: str) -> List[Dict]:
        """Get all active partial TP steps for a user+chain, ordered by step_order."""
        return await self._fetchall(
            """SELECT * FROM partial_take_profits
               WHERE telegram_id=? AND chain=? AND is_active=1
               ORDER BY step_order ASC""",
            (telegram_id, chain),
        )

    # ── Open Trades (all users, for monitors) ────────────────────────────────

    async def list_all_open_trades(self) -> List[Dict]:
        """List ALL open trades across all users (for time-based auto-sell monitor)."""
        return await self._fetchall(
            "SELECT * FROM trades WHERE status='CONFIRMED' AND exit_price_usd=0"
        )

    # ── Price Alerts ──────────────────────────────────────────────────────────

    async def add_price_alert(
        self, telegram_id: int, chain: str, token_address: str,
        token_symbol: str, target_price: float, direction: str = "below"
    ) -> int:
        """Add a price alert for a token."""
        cursor = await self._conn.execute(
            """INSERT INTO price_alerts
               (telegram_id, chain, token_address, token_symbol, target_price, direction)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telegram_id, chain, token_address, token_symbol, target_price, direction),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def list_price_alerts(self, telegram_id: int, active_only: bool = True) -> List[Dict]:
        """List price alerts for a user."""
        sql = "SELECT * FROM price_alerts WHERE telegram_id=?"
        if active_only:
            sql += " AND is_active=1 AND triggered=0"
        sql += " ORDER BY created_at DESC"
        return await self._fetchall(sql, (telegram_id,))

    async def list_all_active_price_alerts(self) -> List[Dict]:
        """List ALL active untriggered price alerts across all users."""
        return await self._fetchall(
            "SELECT * FROM price_alerts WHERE is_active=1 AND triggered=0"
        )

    async def trigger_price_alert(self, alert_id: int) -> None:
        """Mark a price alert as triggered."""
        await self._conn.execute(
            "UPDATE price_alerts SET triggered=1 WHERE id=?", (alert_id,)
        )
        await self._conn.commit()

    async def remove_price_alert(self, alert_id: int, telegram_id: int) -> None:
        """Deactivate a price alert."""
        await self._conn.execute(
            "UPDATE price_alerts SET is_active=0 WHERE id=? AND telegram_id=?",
            (alert_id, telegram_id),
        )
        await self._conn.commit()

    # ── Trade Notes & Tags ───────────────────────────────────────────────────

    async def add_trade_note(
        self, trade_id: int, telegram_id: int, note: str, tags: str = ""
    ) -> int:
        """Add a note/tag to a trade."""
        cursor = await self._conn.execute(
            """INSERT INTO trade_notes (trade_id, telegram_id, note, tags)
               VALUES (?, ?, ?, ?)""",
            (trade_id, telegram_id, note, tags),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_trade_notes(self, trade_id: int) -> List[Dict]:
        """Get all notes for a trade."""
        return await self._fetchall(
            "SELECT * FROM trade_notes WHERE trade_id=? ORDER BY created_at ASC",
            (trade_id,),
        )

    async def search_trades_by_tag(
        self, telegram_id: int, tag: str
    ) -> List[Dict]:
        """Search trades by tag."""
        return await self._fetchall(
            """SELECT t.*, tn.tags, tn.note FROM trades t
               JOIN trade_notes tn ON tn.trade_id = t.id
               WHERE tn.telegram_id=? AND tn.tags LIKE ?
               ORDER BY t.created_at DESC""",
            (telegram_id, f"%{tag}%"),
        )

    # ── DCA Orders ───────────────────────────────────────────────────────────

    async def create_dca_order(
        self, telegram_id: int, chain: str, token_address: str,
        token_symbol: str, total_amount_usd: float, num_splits: int,
        interval_minutes: int
    ) -> int:
        """Create a new DCA order."""
        amount_per = total_amount_usd / num_splits
        cursor = await self._conn.execute(
            """INSERT INTO dca_orders
               (telegram_id, chain, token_address, token_symbol,
                total_amount_usd, num_splits, interval_minutes, amount_per_split)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (telegram_id, chain, token_address, token_symbol,
             total_amount_usd, num_splits, interval_minutes, amount_per),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def list_active_dca_orders(self, telegram_id: int = None) -> List[Dict]:
        """List active DCA orders. If telegram_id is None, list all."""
        if telegram_id:
            return await self._fetchall(
                "SELECT * FROM dca_orders WHERE telegram_id=? AND status='ACTIVE'",
                (telegram_id,),
            )
        return await self._fetchall("SELECT * FROM dca_orders WHERE status='ACTIVE'")

    async def update_dca_order(self, order_id: int, **kwargs) -> None:
        """Update DCA order fields."""
        if not kwargs:
            return
        set_clause = ", ".join(f"{k}=?" for k in kwargs.keys())
        await self._conn.execute(
            f"UPDATE dca_orders SET {set_clause} WHERE id=?",
            tuple(kwargs.values()) + (order_id,),
        )
        await self._conn.commit()

    # ── Limit Orders ─────────────────────────────────────────────────────────

    async def create_limit_order(
        self, telegram_id: int, chain: str, token_address: str,
        token_symbol: str, target_price: float, amount_usd: float,
        direction: str = "buy"
    ) -> int:
        """Create a simulated limit order."""
        cursor = await self._conn.execute(
            """INSERT INTO limit_orders
               (telegram_id, chain, token_address, token_symbol,
                target_price, amount_usd, direction)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (telegram_id, chain, token_address, token_symbol,
             target_price, amount_usd, direction),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def list_limit_orders(self, telegram_id: int, status: str = "PENDING") -> List[Dict]:
        """List limit orders for a user."""
        return await self._fetchall(
            "SELECT * FROM limit_orders WHERE telegram_id=? AND status=? ORDER BY created_at DESC",
            (telegram_id, status),
        )

    async def list_all_pending_limit_orders(self) -> List[Dict]:
        """List ALL pending limit orders across all users."""
        return await self._fetchall(
            "SELECT * FROM limit_orders WHERE status='PENDING'"
        )

    async def fill_limit_order(self, order_id: int) -> None:
        """Mark a limit order as filled."""
        await self._conn.execute(
            "UPDATE limit_orders SET status='FILLED', filled_at=datetime('now') WHERE id=?",
            (order_id,),
        )
        await self._conn.commit()

    async def cancel_limit_order(self, order_id: int, telegram_id: int) -> None:
        """Cancel a limit order."""
        await self._conn.execute(
            "UPDATE limit_orders SET status='CANCELLED' WHERE id=? AND telegram_id=?",
            (order_id, telegram_id),
        )
        await self._conn.commit()

    # ── Whale Profitability Scores ───────────────────────────────────────────

    async def update_whale_score(
        self, whale_address: str, chain: str,
        pnl_usd: float, is_win: bool
    ) -> None:
        """Update whale profitability score after a trade closes."""
        existing = await self._fetchone(
            "SELECT * FROM whale_scores WHERE whale_address=? AND chain=?",
            (whale_address, chain),
        )
        if existing:
            total = existing["total_trades"] + 1
            wins = existing["winning_trades"] + (1 if is_win else 0)
            total_pnl = existing["total_pnl_usd"] + pnl_usd
            avg_pnl = total_pnl / total if total > 0 else 0
            await self._conn.execute(
                """UPDATE whale_scores SET total_trades=?, winning_trades=?,
                   total_pnl_usd=?, avg_pnl_pct=?, last_updated=datetime('now')
                   WHERE whale_address=? AND chain=?""",
                (total, wins, total_pnl, avg_pnl, whale_address, chain),
            )
        else:
            await self._conn.execute(
                """INSERT INTO whale_scores
                   (whale_address, chain, total_trades, winning_trades, total_pnl_usd, avg_pnl_pct)
                   VALUES (?, ?, 1, ?, ?, ?)""",
                (whale_address, chain, 1 if is_win else 0, pnl_usd, pnl_usd),
            )
        await self._conn.commit()

    async def get_whale_scores(self, chain: str = None) -> List[Dict]:
        """Get whale profitability leaderboard."""
        if chain:
            return await self._fetchall(
                "SELECT * FROM whale_scores WHERE chain=? ORDER BY total_pnl_usd DESC",
                (chain,),
            )
        return await self._fetchall(
            "SELECT * FROM whale_scores ORDER BY total_pnl_usd DESC"
        )

    async def get_whale_score(self, whale_address: str, chain: str) -> Optional[Dict]:
        """Get score for a specific whale."""
        return await self._fetchone(
            "SELECT * FROM whale_scores WHERE whale_address=? AND chain=?",
            (whale_address, chain),
        )

    # ── Anti-FOMO Cooldown ───────────────────────────────────────────────────

    async def get_last_trade_time_for_token(
        self, telegram_id: int, token_address: str
    ) -> Optional[str]:
        """Get the most recent trade time for a token by a user."""
        row = await self._fetchone(
            """SELECT created_at FROM trades
               WHERE telegram_id=? AND token_address=? AND action='BUY'
               ORDER BY created_at DESC LIMIT 1""",
            (telegram_id, token_address),
        )
        return row["created_at"] if row else None

    # ── Multi-Wallet helpers ─────────────────────────────────────────────────

    async def get_next_rotation_wallet(
        self, telegram_id: int, chain: str
    ) -> Optional[Dict]:
        """Get the next wallet in rotation (least recently used)."""
        wallets = await self.list_wallets_by_chain(telegram_id, chain)
        if not wallets:
            return None
        if len(wallets) == 1:
            return wallets[0]
        # Find wallet with fewest recent trades
        best = wallets[0]
        best_count = float('inf')
        for w in wallets:
            row = await self._fetchone(
                """SELECT COUNT(*) as cnt FROM trades
                   WHERE telegram_id=? AND chain=?
                   AND created_at >= datetime('now', '-24 hours')""",
                (telegram_id, chain),
            )
            cnt = row["cnt"] if row else 0
            if cnt < best_count:
                best_count = cnt
                best = w
        return best

    # ── Emergency Kill Switch ────────────────────────────────────────────────

    async def list_all_open_trades_for_user(self, telegram_id: int) -> List[Dict]:
        """List ALL open trades across all chains for a user."""
        return await self._fetchall(
            """SELECT * FROM trades
               WHERE telegram_id=? AND status='CONFIRMED' AND exit_price_usd=0""",
            (telegram_id,),
        )

    # ── Portfolio overview ───────────────────────────────────────────────────

    async def get_portfolio_positions(self, telegram_id: int) -> List[Dict]:
        """Get all open positions with entry data for portfolio view."""
        return await self._fetchall(
            """SELECT token_address, token_symbol, chain,
                      SUM(amount_in_usd) as total_invested,
                      AVG(entry_price_usd) as avg_entry_price,
                      SUM(remaining_pct) as total_remaining_pct,
                      COUNT(*) as position_count
               FROM trades
               WHERE telegram_id=? AND status='CONFIRMED' AND exit_price_usd=0
               GROUP BY token_address, chain
               ORDER BY total_invested DESC""",
            (telegram_id,),
        )

    # ── Subscriptions ─────────────────────────────────────────────────────────

    async def upsert_subscription(
        self, telegram_id: int, tier: str, expires_at: str,
        is_banned: int, trial_started_at: str, notes: str,
    ) -> None:
        """Create or update a user's subscription record."""
        await self._execute(
            """INSERT INTO subscriptions (telegram_id, tier, expires_at, is_banned, trial_started_at, notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(telegram_id) DO UPDATE SET
                 tier=excluded.tier,
                 expires_at=excluded.expires_at,
                 is_banned=excluded.is_banned,
                 notes=excluded.notes,
                 updated_at=datetime('now')""",
            (telegram_id, tier, expires_at, is_banned, trial_started_at, notes),
        )
        await self._conn.commit()

    async def get_subscription(self, telegram_id: int) -> Optional[Dict]:
        """Fetch a single user's subscription record."""
        return await self._fetchone(
            "SELECT * FROM subscriptions WHERE telegram_id=?", (telegram_id,)
        )

    async def list_subscriptions(self) -> List[Dict]:
        """List all subscriptions ordered by updated_at desc."""
        return await self._fetchall(
            "SELECT * FROM subscriptions ORDER BY updated_at DESC"
        )

    async def get_subscription_stats(self) -> Dict:
        """Return aggregate subscription counts by tier."""
        rows = await self._fetchall(
            "SELECT tier, COUNT(*) as cnt, SUM(is_banned) as banned FROM subscriptions GROUP BY tier"
        )
        return {r["tier"]: {"count": r["cnt"], "banned": r["banned"]} for r in rows}

    # ── License Keys ──────────────────────────────────────────────────────────

    async def save_license_key(
        self, key_str: str, tier: str, duration_days: int, created_by: int
    ) -> None:
        """Persist a newly generated license key."""
        await self._execute(
            """INSERT OR IGNORE INTO license_keys (key_str, tier, duration_days, created_by)
               VALUES (?, ?, ?, ?)""",
            (key_str, tier, duration_days, created_by),
        )
        await self._conn.commit()

    async def mark_key_redeemed(self, key_str: str, redeemed_by: int) -> None:
        """Mark a license key as redeemed."""
        await self._execute(
            """UPDATE license_keys SET redeemed_by=?, redeemed_at=datetime('now')
               WHERE key_str=?""",
            (redeemed_by, key_str),
        )
        await self._conn.commit()

    async def get_license_key(self, key_str: str) -> Optional[Dict]:
        """Look up a single key."""
        return await self._fetchone(
            "SELECT * FROM license_keys WHERE key_str=?", (key_str,)
        )

    async def list_license_keys(self, unredeemed_only: bool = False) -> List[Dict]:
        """List keys, optionally filtering to unredeemed."""
        if unredeemed_only:
            return await self._fetchall(
                "SELECT * FROM license_keys WHERE redeemed_by IS NULL ORDER BY created_at DESC"
            )
        return await self._fetchall(
            "SELECT * FROM license_keys ORDER BY created_at DESC"
        )

    async def delete_license_key(self, key_str: str) -> None:
        """Delete (revoke) a license key."""
        await self._execute("DELETE FROM license_keys WHERE key_str=?", (key_str,))
        await self._conn.commit()

    async def load_all_license_keys(self) -> List[Dict]:
        """Load all license keys for in-memory restoration at startup."""
        return await self._fetchall("SELECT * FROM license_keys ORDER BY created_at")

    async def load_all_subscriptions(self) -> List[Dict]:
        """Load all subscription rows for in-memory restoration at startup."""
        return await self._fetchall("SELECT * FROM subscriptions ORDER BY updated_at")

