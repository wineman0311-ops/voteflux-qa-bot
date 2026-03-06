"""
Main entry point for VoteFlux QA automation bot.

Initializes bot, scheduler, and handles graceful shutdown.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from config import settings
from bot.app import create_bot
from scheduler.scheduler import TaskScheduler
from storage.report_store import ReportStore
from storage.schedule_store import ScheduleStore
from storage.platform_store import PlatformStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


class BotManager:
    """
    Manages bot lifecycle and graceful shutdown.

    Coordinates bot startup, scheduler initialization, and shutdown procedures.
    """

    def __init__(self):
        """Initialize BotManager."""
        self.app = None
        self.scheduler = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """
        Start the bot and scheduler.

        Validates environment variables, initializes stores, creates bot,
        sets up scheduler, and starts polling.
        """
        logger.info("=" * 60)
        logger.info("VoteFlux QA Automation Bot Starting")
        logger.info("=" * 60)

        try:
            # Validate required environment variables
            self._validate_settings()

            # Initialize storage
            logger.info("Initializing storage...")
            report_store = ReportStore(settings.REPORTS_DIR)
            schedule_store = ScheduleStore()
            platform_store = PlatformStore(settings.PLATFORM_STORE_PATH)
            logger.info(f"Loaded {platform_store.count()} platforms")

            # Create bot application
            logger.info("Creating bot application...")
            self.app = create_bot(settings.TG_BOT_TOKEN)

            # Store shared resources in bot_data
            self.app.bot_data["report_store"] = report_store
            self.app.bot_data["schedule_store"] = schedule_store
            self.app.bot_data["platform_store"] = platform_store
            self.app.bot_data["is_running"] = False

            # Initialize and start scheduler
            logger.info("Initializing scheduler...")
            self.scheduler = TaskScheduler(
                self.app,
                report_store,
                schedule_store,
            )
            self.app.bot_data["scheduler"] = self.scheduler

            # Setup signal handlers
            self._setup_signal_handlers()

            # Start bot with polling
            logger.info("Starting bot application...")
            async with self.app:
                # Start scheduler
                self.scheduler.start()
                logger.info("Scheduler started")

                # Start bot
                await self.app.start()
                logger.info("Bot started")

                # Start polling
                logger.info("Starting polling...")
                await self.app.updater.start_polling(
                    allowed_updates=[],
                    error_callback=self._polling_error_handler,
                )

                logger.info("=" * 60)
                logger.info("Bot is running and ready!")
                logger.info("=" * 60)

                # Wait for shutdown signal
                await self._shutdown_event.wait()

                logger.info("Shutting down...")
                await self.app.updater.stop()
                await self.app.stop()

        except Exception as e:
            logger.error(f"Fatal error during startup: {str(e)}", exc_info=True)
            raise

        finally:
            if self.scheduler and self.scheduler.scheduler.running:
                self.scheduler.stop()
            logger.info("Bot shutdown complete")

    async def stop(self) -> None:
        """
        Gracefully stop the bot and scheduler.

        Signals the shutdown event to wake up the waiting task.
        """
        logger.info("Received shutdown signal")
        self._shutdown_event.set()

    def _validate_settings(self) -> None:
        """
        Validate required environment variables.

        Raises:
            ValueError: If required settings are missing
        """
        if not settings.TG_BOT_TOKEN:
            raise ValueError(
                "TG_BOT_TOKEN environment variable is required"
            )

        if not settings.TG_CHAT_ID:
            raise ValueError(
                "TG_CHAT_ID environment variable is required"
            )

        logger.info(f"Settings validated")
        logger.info(f"  REPORTS_DIR: {settings.REPORTS_DIR}")
        logger.info(f"  PLATFORM_STORE: {settings.PLATFORM_STORE_PATH}")
        logger.info(f"  CRON_SCHEDULE: {settings.CRON_SCHEDULE}")
        logger.info(f"  TG_CHAT_ID: {settings.TG_CHAT_ID}")

    def _setup_signal_handlers(self) -> None:
        """
        Setup signal handlers for graceful shutdown.

        Handles SIGINT (Ctrl+C) and SIGTERM signals.
        """
        loop = asyncio.get_event_loop()

        def signal_handler(signum, frame):
            """Handle shutdown signals."""
            logger.info(f"Received signal {signum}")
            asyncio.create_task(self.stop())

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def _polling_error_handler(self, update, context) -> None:
        """
        Handle polling errors.

        Args:
            update: Update object
            context: CallbackContext object
        """
        logger.error(f"Polling error: {context.error}", exc_info=context.error)


async def main() -> None:
    """
    Main entry point.

    Creates and starts the bot manager.
    """
    manager = BotManager()

    try:
        await manager.start()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
        await manager.stop()
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
        sys.exit(0)
