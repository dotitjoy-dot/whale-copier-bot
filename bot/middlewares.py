"""
Auth middleware, rate limiter, and auto-lock for the Telegram bot.
- Whitelist check: only allowed user IDs can interact.
- Rate limiter: max N commands per minute per user.
- Auto-lock: session locks after inactivity timeout.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, Set

from telegram import Update
from telegram.ext import ContextTypes

from core.logger import get_logger

logger = get_logger(__name__)


class AuthMiddleware:
    """
    Telegram bot middleware that gates all interaction behind:
    1. User whitelist (ALLOWED_USER_IDS)
    2. Rate limiting (max commands per minute)
    3. Session auto-lock (passphrase re-entry after timeout)
    """

    def __init__(
        self,
        allowed_ids: Set[int],
        admin_id: int,
        rate_limit: int = 30,
        auto_lock_minutes: int = 10,
    ) -> None:
        """
        Initialize the auth middleware.

        Args:
            allowed_ids: Set of authorized Telegram user IDs.
            admin_id: Admin user's Telegram ID.
            rate_limit: Max commands per minute per user.
            auto_lock_minutes: Minutes of inactivity before session locks.
        """
        self._allowed = allowed_ids
        self._admin_id = admin_id
        self._rate_limit = rate_limit
        self._auto_lock_seconds = auto_lock_minutes * 60
        self._cmd_timestamps: Dict[int, list] = defaultdict(list)
        self._last_activity: Dict[int, float] = {}
        self._sessions: Dict[int, str] = {}  # telegram_id → passphrase (in-memory only)

    def is_authorized(self, user_id: int) -> bool:
        """
        Check if a user ID is in the allowed whitelist.

        Args:
            user_id: Telegram user ID.

        Returns:
            True if authorized.
        """
        return user_id in self._allowed

    def is_admin(self, user_id: int) -> bool:
        """
        Check if a user is the admin.

        Args:
            user_id: Telegram user ID.

        Returns:
            True if this is the admin user.
        """
        return user_id == self._admin_id

    def check_rate_limit(self, user_id: int) -> bool:
        """
        Check and enforce rate limiting for a user.
        Cleans up timestamps older than 60 seconds.

        Args:
            user_id: Telegram user ID.

        Returns:
            True if within rate limit, False if exceeded.
        """
        now = time.time()
        timestamps = self._cmd_timestamps[user_id]
        # Prune old entries
        timestamps[:] = [ts for ts in timestamps if now - ts < 60]
        if len(timestamps) >= self._rate_limit:
            logger.warning("Rate limit exceeded for user %d (%d/min)", user_id, len(timestamps))
            return False
        timestamps.append(now)
        return True

    def touch_activity(self, user_id: int) -> None:
        """
        Record a user activity timestamp (resets auto-lock timer).

        Args:
            user_id: Telegram user ID.
        """
        self._last_activity[user_id] = time.time()

    def is_session_locked(self, user_id: int) -> bool:
        """
        Check if the user's session is locked due to inactivity.

        Args:
            user_id: Telegram user ID.

        Returns:
            True if the session has expired and user must re-enter passphrase.
        """
        last = self._last_activity.get(user_id, 0)
        if last == 0:
            return True  # Never active → locked
        elapsed = time.time() - last
        if elapsed > self._auto_lock_seconds:
            self.clear_session(user_id)
            return True
        return False

    def set_session_passphrase(self, user_id: int, passphrase: str) -> None:
        """
        Store passphrase in-memory session (never persisted to disk).

        Args:
            user_id: Telegram user ID.
            passphrase: User's wallet passphrase.
        """
        self._sessions[user_id] = passphrase
        self.touch_activity(user_id)

    def get_session_passphrase(self, user_id: int) -> str:
        """
        Retrieve the stored session passphrase.

        Args:
            user_id: Telegram user ID.

        Returns:
            Passphrase string, or empty string if not set / session locked.
        """
        if self.is_session_locked(user_id):
            return ""
        self.touch_activity(user_id)
        return self._sessions.get(user_id, "")

    def clear_session(self, user_id: int) -> None:
        """
        Clear/zero the session passphrase for a user.

        Args:
            user_id: Telegram user ID.
        """
        if user_id in self._sessions:
            # Zero-fill the passphrase string before removing
            self._sessions[user_id] = "\x00" * len(self._sessions[user_id])
            del self._sessions[user_id]
        self._last_activity.pop(user_id, None)


async def auth_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Convenience function to run auth + rate limit checks at the top of any handler.
    Returns True if authorized and within rate limit. Sends error message if not.

    Args:
        update: Telegram Update object.
        context: Bot context.

    Returns:
        True if the user can proceed, False otherwise.
    """
    user_id = update.effective_user.id if update.effective_user else 0
    from core.auth_manager import AuthManager
    auth: AuthManager = context.bot_data.get("auth")

    if not auth:
        return False

    if not auth.is_authorized(user_id):
        msg = update.effective_message
        if msg:
            await msg.reply_text("⛔ You are not authorized to use this bot.")
        return False

    if not auth.check_rate_limit(user_id):
        msg = update.effective_message
        if msg:
            await msg.reply_text("⚠️ Rate limit exceeded. Please wait a moment.")
        return False

    auth.touch_activity(user_id)
    return True
