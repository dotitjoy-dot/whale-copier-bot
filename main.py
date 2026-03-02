"""
main.py — Entry point for the Whale Copy Trading Bot.
"""

from __future__ import annotations

import os
import sys
import warnings
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

# Ensure the working directory is the project directory (fixes System32 issue on Windows)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
try:
    os.chdir(PROJECT_ROOT)
except Exception:
    pass
sys.path.insert(0, PROJECT_ROOT)

from telegram.ext import Application

from bot.application import post_init, post_shutdown, build_conversation_handler
from config.settings import Settings
from core.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    """
    Build and run the Telegram bot application.
    Reads config from .env, initializes all subsystems, and enters polling loop.
    """
    # Load settings
    settings = Settings()
    logger.info("Settings loaded — Bot starting...")

    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set! Add it to .env")
        sys.exit(1)

    # Build application
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Inject settings
    app.bot_data["settings"] = settings

    # Register conversation handler
    conv_handler = build_conversation_handler()
    app.add_handler(conv_handler)

    # Start polling
    logger.info(
        "🐋 Whale Copy Trading Bot started! Allowed users: %s",
        settings.allowed_user_ids
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
