"""
Main entry point for VoteFlux QA automation bot.

Initializes bot, scheduler, and handles graceful shutdown.
Subscription-based broadcast model — no hardcoded TG_CHAT_ID required.
"""

# ── Early-boot diagnostic: print to stdout BEFORE any imports ──────────────
# If nothing appears in Runtime Logs at all, Python itself fails to start
import sys as _sys
print("=== VoteFlux QA Bot: Python interpreter started ===", flush=True, file=_sys.stdout)

# ── Now import stdlib and third-party packages, catching any failure ───────
try:
    import asyncio
    import logging
    import signal
    from typing import Optional
    print("=== stdlib imports OK ===", flush=True)
except Exception as _e:
    print(f"=== FATAL: stdlib import failed: {_e} ===", flush=True)
    _sys.exit(1)

try:
    from telegram import BotCommand
    print("=== python-telegram-bot import OK ===", flush=True)
except ImportError as _e:
    print(f"=== FATAL: python-telegram-bot not found: {_e} ===", flush=True)
    _sys.exit(1)

try:
    from config import settings
    from bot.app import create_bot
    from scheduler.scheduler import TaskScheduler
    from storage.report_store import ReportStore
    from storage.schedule_store import ScheduleStore
    from storage.platform_store import PlatformStore
    from storage.subscriber_store import SubscriberStore
    print("=== all local module imports OK ===", flush=True)
except Exception as _e:
    print(f"=== FATAL: local module import failed: {_e} ===", flush=True)
    import traceback
    traceback.print_exc()
    _sys.exit(1)

# Configure logging — always log to stdout; file logging is optional
_log_handlers = [logging.StreamHandler(sys.stdout)]
try:
    _log_handlers.append(logging.FileHandler("bot.log"))
except Exception:
    pass  # container may not have a writable working directory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=_log_handlers,
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
            subscriber_store = SubscriberStore(settings.SUBSCRIBER_STORE_PATH)
            logger.info(f"Loaded {platform_store.count()} platforms")
            logger.info(f"Loaded {subscriber_store.count()} subscribers")

            # Create bot application
            logger.info("Creating bot application...")
            self.app = create_bot(settings.TG_BOT_TOKEN)

            # Store shared resources in bot_data
            self.app.bot_data["report_store"] = report_store
            self.app.bot_data["schedule_store"] = schedule_store
            self.app.bot_data["platform_store"] = platform_store
            self.app.bot_data["subscriber_store"] = subscriber_store
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

                # Set Telegram command menu (shows in chat UI)
                await self._set_bot_commands()
                logger.info("Bot commands menu set")

                # Start polling
                logger.info("Starting polling...")
                await self.app.updater.start_polling(
                    allowed_updates=[],
                    error_callback=self._on_polling_error,
                )

                logger.info("=" * 60)
                logger.info("Bot is running and ready!")
                logger.info(f"  Subscribers: {subscriber_store.count()}")
                logger.info(f"  Platforms: {platform_store.count()}")
                logger.info(f"  Schedule: {settings.CRON_SCHEDULE}")
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
        """Gracefully stop the bot and scheduler."""
        logger.info("Received shutdown signal")
        self._shutdown_event.set()

    def _validate_settings(self) -> None:
        """
        Validate required environment variables.

        Only TG_BOT_TOKEN is required now (no TG_CHAT_ID needed).

        Raises:
            ValueError: If required settings are missing
        """
        if not settings.TG_BOT_TOKEN:
            raise ValueError(
                "TG_BOT_TOKEN environment variable is required"
            )

        logger.info("Settings validated")
        logger.info(f"  REPORTS_DIR: {settings.REPORTS_DIR}")
        logger.info(f"  PLATFORM_STORE: {settings.PLATFORM_STORE_PATH}")
        logger.info(f"  SUBSCRIBER_STORE: {settings.SUBSCRIBER_STORE_PATH}")
        logger.info(f"  CRON_SCHEDULE: {settings.CRON_SCHEDULE}")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def _set_bot_commands(self) -> None:
        """
        Set Telegram bot command menu.

        This registers the command list in Telegram so users see
        available commands when they tap the '/' button in chat.
        """
        commands = [
            BotCommand("start",          "🤖 開始使用 / 查看介紹"),
            BotCommand("subscribe",      "📬 訂閱自動分析報告"),
            BotCommand("unsubscribe",    "🔕 取消訂閱"),
            BotCommand("mystatus",       "🔍 查看我的訂閱狀態"),
            BotCommand("run",            "▶️ 立即執行競品分析"),
            BotCommand("status",         "📊 查看機器人狀態"),
            BotCommand("history",        "📜 查看歷史報告"),
            BotCommand("report",         "📄 取得指定版本報告"),
            BotCommand("schedule",       "⏱️ 查看/設定定時排程"),
            BotCommand("platforms",      "🌐 查看分析平台清單"),
            BotCommand("add_platform",   "➕ 新增分析平台"),
            BotCommand("remove_platform","➖ 移除分析平台"),
            BotCommand("help",           "❓ 顯示完整指令說明"),
        ]
        try:
            await self.app.bot.set_my_commands(commands)
            logger.info(f"Set {len(commands)} bot commands in Telegram menu")
        except Exception as e:
            logger.warning(f"Failed to set bot commands: {e}")

    def _on_polling_error(self, error: Exception) -> None:
        """Handle polling-level errors (network issues, timeouts, etc.)."""
        logger.error(f"Polling error: {error}", exc_info=error)


async def main() -> None:
    """Main entry point."""
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
