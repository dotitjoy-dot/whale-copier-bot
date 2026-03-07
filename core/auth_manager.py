"""
AuthManager — full public-bot authentication system.

Features:
  - License Key system (admin generates keys, users redeem them)
  - Subscription tiers: FREE, PRO, ELITE
  - Expiry dates per user
  - User ban / unban
  - Trial mode (N-day free trial on first /start)
  - Per-user usage limits based on tier
  - Full audit log for admin
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

from core.logger import get_logger

logger = get_logger(__name__)

# ── Subscription Tiers ────────────────────────────────────────────────────────
TIERS = {
    "FREE":  {"label": "🆓 Free Trial",   "max_whales": 2,  "max_trades": 5,  "features": []},
    "PRO":   {"label": "⭐ Pro",           "max_whales": 10, "max_trades": 50, "features": ["dca", "alerts", "limit_orders"]},
    "ELITE": {"label": "💎 Elite",         "max_whales": 50, "max_trades": 500,"features": ["dca", "alerts", "limit_orders", "sniper", "pnl_cards"]},
}

TRIAL_DAYS = 7   # Days of free trial before requiring a license key


class LicenseKey:
    """Represents a generated license key with a tier and duration."""

    def __init__(self, key: str, tier: str, duration_days: int, created_by: int):
        self.key = key
        self.tier = tier
        self.duration_days = duration_days
        self.created_by = created_by
        self.created_at = datetime.utcnow()
        self.redeemed_by: Optional[int] = None
        self.redeemed_at: Optional[datetime] = None

    @property
    def is_redeemed(self) -> bool:
        return self.redeemed_by is not None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "tier": self.tier,
            "duration_days": self.duration_days,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "redeemed_by": self.redeemed_by,
            "redeemed_at": self.redeemed_at.isoformat() if self.redeemed_at else None,
        }


class UserSubscription:
    """Tracks a single user's subscription state."""

    def __init__(
        self,
        telegram_id: int,
        tier: str = "FREE",
        expires_at: Optional[datetime] = None,
        is_banned: bool = False,
        trial_started_at: Optional[datetime] = None,
        notes: str = "",
    ):
        self.telegram_id = telegram_id
        self.tier = tier
        self.expires_at = expires_at
        self.is_banned = is_banned
        self.trial_started_at = trial_started_at or datetime.utcnow()
        self.notes = notes

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_trial_active(self) -> bool:
        if self.tier != "FREE":
            return False
        cutoff = self.trial_started_at + timedelta(days=TRIAL_DAYS)
        return datetime.utcnow() < cutoff

    @property
    def is_active(self) -> bool:
        """User can use the bot if: not banned, AND (trial active OR subscription not expired)."""
        if self.is_banned:
            return False
        if self.tier != "FREE" and not self.is_expired:
            return True
        if self.tier == "FREE" and self.is_trial_active:
            return True
        return False

    @property
    def days_remaining(self) -> int:
        if self.is_expired or self.expires_at is None:
            if self.tier == "FREE" and self.is_trial_active:
                cutoff = self.trial_started_at + timedelta(days=TRIAL_DAYS)
                return max(0, (cutoff - datetime.utcnow()).days)
            return 0
        return max(0, (self.expires_at - datetime.utcnow()).days)

    def tier_info(self) -> dict:
        return TIERS.get(self.tier, TIERS["FREE"])

    def to_dict(self) -> dict:
        return {
            "telegram_id": self.telegram_id,
            "tier": self.tier,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_banned": self.is_banned,
            "trial_started_at": self.trial_started_at.isoformat(),
            "notes": self.notes,
            "is_active": self.is_active,
            "days_remaining": self.days_remaining,
        }


class AuthManager:
    """
    Central authentication and license key manager for public bot deployment.

    Stores everything in-memory backed by the database for persistence.
    """

    def __init__(self, admin_id: int, db=None):
        self._admin_id = admin_id
        self._db = db

        # In-memory caches
        self._subscriptions: Dict[int, UserSubscription] = {}
        self._license_keys: Dict[str, LicenseKey] = {}

        # Session management (passphrase cache, rate limiting)
        self._sessions: Dict[int, str] = {}   # user_id → passphrase
        self._last_activity: Dict[int, float] = {}
        self._cmd_timestamps: Dict[int, list] = {}

        self._auto_lock_seconds = 10 * 60  # 10 minutes default
        self._rate_limit = 30  # commands/minute

    # ── Admin checks ─────────────────────────────────────────────────────────

    def is_admin(self, user_id: int) -> bool:
        return user_id == self._admin_id

    # ── Subscription management ───────────────────────────────────────────────

    def get_subscription(self, user_id: int) -> UserSubscription:
        """Get or create a subscription for a user (defaults to FREE trial)."""
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = UserSubscription(user_id)
        return self._subscriptions[user_id]

    def load_subscription(self, sub: UserSubscription) -> None:
        """Load a subscription record (called when restoring from DB)."""
        self._subscriptions[sub.telegram_id] = sub

    def is_authorized(self, user_id: int) -> bool:
        """Returns True if user can access the bot right now."""
        if self.is_admin(user_id):
            return True
        sub = self.get_subscription(user_id)
        return sub.is_active

    def ban_user(self, user_id: int, notes: str = "") -> None:
        sub = self.get_subscription(user_id)
        sub.is_banned = True
        sub.notes = notes
        self.clear_session(user_id)
        logger.warning("User %d BANNED. Notes: %s", user_id, notes)

    def unban_user(self, user_id: int) -> None:
        sub = self.get_subscription(user_id)
        sub.is_banned = False
        logger.info("User %d UNBANNED.", user_id)

    def set_subscription(
        self, user_id: int, tier: str, duration_days: int, notes: str = ""
    ) -> UserSubscription:
        """Grant or upgrade a user's subscription."""
        sub = self.get_subscription(user_id)
        sub.tier = tier.upper()
        sub.expires_at = datetime.utcnow() + timedelta(days=duration_days)
        if notes:
            sub.notes = notes
        logger.info("User %d upgraded to %s for %d days.", user_id, tier, duration_days)
        return sub

    def revoke_subscription(self, user_id: int) -> None:
        """Immediately expire a user's subscription."""
        sub = self.get_subscription(user_id)
        sub.tier = "FREE"
        sub.expires_at = datetime.utcnow() - timedelta(seconds=1)
        sub.trial_started_at = datetime.utcnow() - timedelta(days=TRIAL_DAYS + 1)
        logger.info("User %d subscription REVOKED.", user_id)

    # ── License Key system ────────────────────────────────────────────────────

    def generate_key(
        self, tier: str, duration_days: int, admin_id: int, prefix: str = ""
    ) -> LicenseKey:
        """Generate a new license key."""
        raw = secrets.token_hex(12).upper()
        # Format: TIER-XXXX-XXXX-XXXX
        chunks = [raw[i:i+4] for i in range(0, 12, 4)]
        tier_tag = (prefix or tier[:3]).upper()
        key_str = f"{tier_tag}-{'-'.join(chunks)}"

        lk = LicenseKey(key_str, tier.upper(), duration_days, admin_id)
        self._license_keys[key_str] = lk
        logger.info("License key generated: %s (%s, %dd)", key_str, tier, duration_days)
        return lk

    def redeem_key(self, user_id: int, key_str: str) -> tuple[bool, str]:
        """
        Attempt to redeem a license key.
        Returns (success: bool, message: str).
        """
        key_str = key_str.strip().upper()
        lk = self._license_keys.get(key_str)

        if not lk:
            return False, "❌ Invalid license key. Please check and try again."
        if lk.is_redeemed:
            return False, "❌ This key has already been used."

        # Apply subscription
        sub = self.set_subscription(user_id, lk.tier, lk.duration_days)
        lk.redeemed_by = user_id
        lk.redeemed_at = datetime.utcnow()

        tier_info = TIERS.get(lk.tier, {})
        msg = (
            f"✅ Key redeemed successfully!\n"
            f"🎯 Tier: {tier_info.get('label', lk.tier)}\n"
            f"📅 Valid for: {lk.duration_days} days\n"
            f"⏳ Expires: {sub.expires_at.strftime('%Y-%m-%d')}"
        )
        logger.info("User %d redeemed key %s (%s).", user_id, key_str, lk.tier)
        return True, msg

    def revoke_key(self, key_str: str) -> bool:
        """Delete a license key (mark as unusable)."""
        key_str = key_str.strip().upper()
        if key_str in self._license_keys:
            del self._license_keys[key_str]
            return True
        return False

    def list_keys(self, show_redeemed: bool = False) -> list[LicenseKey]:
        """List all keys, optionally filtering to unredeemed only."""
        keys = list(self._license_keys.values())
        if not show_redeemed:
            keys = [k for k in keys if not k.is_redeemed]
        return sorted(keys, key=lambda k: k.created_at, reverse=True)

    def list_subscriptions(self) -> list[UserSubscription]:
        """List all subscriptions."""
        return list(self._subscriptions.values())

    # ── Session management ────────────────────────────────────────────────────

    def set_auto_lock(self, minutes: int) -> None:
        self._auto_lock_seconds = minutes * 60

    def is_session_locked(self, user_id: int) -> bool:
        last = self._last_activity.get(user_id, 0)
        if last == 0:
            return True
        if time.time() - last > self._auto_lock_seconds:
            self.clear_session(user_id)
            return True
        return False

    def set_session_passphrase(self, user_id: int, passphrase: str) -> None:
        self._sessions[user_id] = passphrase
        self._last_activity[user_id] = time.time()

    def get_session_passphrase(self, user_id: int) -> str:
        if self.is_session_locked(user_id):
            return ""
        self._last_activity[user_id] = time.time()
        return self._sessions.get(user_id, "")

    def clear_session(self, user_id: int) -> None:
        if user_id in self._sessions:
            self._sessions[user_id] = "\x00" * len(self._sessions[user_id])
            del self._sessions[user_id]
        self._last_activity.pop(user_id, None)

    def touch_activity(self, user_id: int) -> None:
        self._last_activity[user_id] = time.time()

    def check_rate_limit(self, user_id: int) -> bool:
        now = time.time()
        if user_id not in self._cmd_timestamps:
            self._cmd_timestamps[user_id] = []
        ts = self._cmd_timestamps[user_id]
        ts[:] = [t for t in ts if now - t < 60]
        if len(ts) >= self._rate_limit:
            return False
        ts.append(now)
        return True
