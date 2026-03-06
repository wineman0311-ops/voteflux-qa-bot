"""
Telegram bot application setup and configuration.

Initializes the python-telegram-bot Application with all command handlers.
"""

import logging
from typing import Optional

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.handlers import (
    start_handler,
    run_handler,
    status_handler,
    schedule_handler,
    history_handler,
    report_handler,
    help_handler,
    platforms_handler,
    add_platform_handler,
    remove_platform_handler,
    subscribe_handler,
    unsubscribe_handler,
    mystatus_handler,
    unknown_message_handler,
)

logger = logging.getLogger(__name__)


def create_bot(token: str) -> Application:
    """
    Create and configure the Telegram bot Application.

    Registers all command handlers and a catch-all message handler.

    Args:
        token: Telegram Bot API token

    Returns:
        Configured Application instance

    Raises:
        ValueError: If token is empty or invalid
    """
    if not token or not isinstance(token, str):
        raise ValueError("Invalid bot token: must be a non-empty string")

    # Create Application with token
    app = Application.builder().token(token).build()

    logger.info("Registering command handlers")

    # Subscription commands
    app.add_handler(CommandHandler("subscribe", subscribe_handler))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_handler))
    app.add_handler(CommandHandler("mystatus", mystatus_handler))

    # Core commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("run", run_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("schedule", schedule_handler))
    app.add_handler(CommandHandler("history", history_handler))
    app.add_handler(CommandHandler("report", report_handler))
    app.add_handler(CommandHandler("help", help_handler))

    # Platform management commands
    app.add_handler(CommandHandler("platforms", platforms_handler))
    app.add_handler(CommandHandler("add_platform", add_platform_handler))
    app.add_handler(CommandHandler("remove_platform", remove_platform_handler))

    # Catch-all: handle plain text messages (non-commands)
    # Must be added LAST so command handlers take priority
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message_handler)
    )

    logger.info("Bot application created successfully with 14 handlers")
    return app
