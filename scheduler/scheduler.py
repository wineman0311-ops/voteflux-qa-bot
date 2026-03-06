"""
Task scheduler using APScheduler for automated analysis runs.

Manages scheduling of periodic QA analysis and report generation.
Broadcasts reports to all subscribers instead of a single chat ID.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from analyzers.orchestrator import AnalysisOrchestrator
from config.platforms import PlatformData, CountryNews
from report.generator import ReportGenerator
from storage.report_store import ReportStore
from storage.schedule_store import ScheduleStore

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Manages scheduled execution of QA analysis.

    Uses APScheduler's AsyncIOScheduler to run periodic analysis based on
    cron expressions. Results are broadcast to all subscribers.
    """

    def __init__(
        self,
        bot_app,
        report_store: ReportStore,
        schedule_store: ScheduleStore,
    ) -> None:
        """
        Initialize TaskScheduler.

        Args:
            bot_app: Telegram Application instance
            report_store: ReportStore instance
            schedule_store: ScheduleStore instance
        """
        self.bot_app = bot_app
        self.report_store = report_store
        self.schedule_store = schedule_store

        # Initialize APScheduler
        self.scheduler = AsyncIOScheduler()
        self._job_id = "scheduled_analysis_job"

    def start(self) -> None:
        """
        Start the scheduler with current cron schedule.
        """
        try:
            if self.scheduler.running:
                logger.warning("Scheduler already running")
                return

            cron_expr = self.schedule_store.get_schedule()
            logger.info(f"Starting scheduler with cron: {cron_expr}")

            self.scheduler.start()
            self._add_scheduled_job(cron_expr)

            logger.info("Scheduler started successfully")

        except Exception as e:
            logger.error(f"Failed to start scheduler: {str(e)}", exc_info=True)
            raise

    def stop(self) -> None:
        """Shutdown the scheduler gracefully."""
        try:
            if not self.scheduler.running:
                logger.warning("Scheduler not running")
                return

            logger.info("Stopping scheduler")
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

        except Exception as e:
            logger.error(f"Error stopping scheduler: {str(e)}", exc_info=True)

    def update_schedule(self, cron_expr: str) -> bool:
        """
        Update the schedule with a new cron expression.

        Args:
            cron_expr: New cron expression

        Returns:
            True if schedule was updated successfully, False otherwise
        """
        try:
            logger.info(f"Updating schedule to: {cron_expr}")

            if not self.schedule_store.set_schedule(cron_expr):
                logger.error(f"Invalid cron expression: {cron_expr}")
                return False

            if self.scheduler.running:
                try:
                    self.scheduler.remove_job(self._job_id)
                    logger.info("Removed old scheduled job")
                except Exception as e:
                    logger.warning(f"Could not remove old job: {str(e)}")

                self._add_scheduled_job(cron_expr)

            logger.info("Schedule updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to update schedule: {str(e)}", exc_info=True)
            return False

    def get_next_runs(self, count: int = 3) -> List[datetime]:
        """Get the next scheduled run times."""
        try:
            cron_expr = self.schedule_store.get_schedule()
            from croniter import croniter
            base = datetime.now()
            cron = croniter(cron_expr, base)
            return [cron.get_next(datetime) for _ in range(count)]
        except Exception as e:
            logger.error(f"Error calculating next runs: {str(e)}")
            return []

    def _add_scheduled_job(self, cron_expr: str) -> None:
        """Add scheduled analysis job to scheduler."""
        try:
            parts = cron_expr.split()
            if len(parts) != 5:
                raise ValueError(f"Invalid cron expression: {cron_expr}")

            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )

            self.scheduler.add_job(
                self._scheduled_job,
                trigger=trigger,
                id=self._job_id,
                name="VoteFlux QA Analysis",
                replace_existing=True,
            )

            next_run = self.scheduler.get_job(self._job_id).next_run_time
            logger.info(f"Scheduled job added, next run: {next_run}")

        except Exception as e:
            logger.error(f"Failed to add scheduled job: {str(e)}", exc_info=True)
            raise

    async def _scheduled_job(self) -> None:
        """
        The scheduled job that runs analysis and broadcasts to all subscribers.

        This async method is called by the scheduler at the specified time.
        """
        logger.info("Scheduled job triggered")
        version = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Get subscriber store from bot_data
        subscriber_store = self.bot_app.bot_data.get("subscriber_store")
        if not subscriber_store:
            logger.error("No subscriber_store in bot_data")
            return

        chat_ids = subscriber_store.get_all_chat_ids()
        if not chat_ids:
            logger.info("No subscribers — skipping broadcast")
            return

        # Notify subscribers: analysis starting
        for chat_id in chat_ids:
            try:
                await self.bot_app.bot.send_message(
                    chat_id=chat_id,
                    text="🔄 定時分析開始\n\n請稍候...",
                )
            except Exception as e:
                logger.warning(f"Failed to notify {chat_id} of start: {e}")

        try:
            # Run analysis in thread
            report_path, summary_text, error_msg = await asyncio.to_thread(
                self._run_analysis_sync, version
            )

            if error_msg:
                for chat_id in chat_ids:
                    try:
                        await self.bot_app.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                "❌ 定時分析失敗\n\n"
                                f"錯誤: {error_msg}\n\n"
                                "請檢查日誌"
                            ),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to notify {chat_id} of error: {e}")
                logger.error(f"Scheduled analysis failed: {error_msg}")
                return

            # Broadcast report to all subscribers
            success_count = 0
            for chat_id in chat_ids:
                try:
                    await self.bot_app.bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ 定時分析完成\n\n{summary_text}",
                    )
                    if report_path:
                        with open(report_path, "rb") as report_file:
                            await self.bot_app.bot.send_document(
                                chat_id=chat_id,
                                document=report_file,
                                caption=f"VoteFlux QA 報告 - {version}",
                                filename=f"VoteFlux_Analysis_Report_{version}.html",
                            )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send to subscriber {chat_id}: {e}")

            logger.info(
                f"Scheduled job done. Notified {success_count}/{len(chat_ids)} subscribers. "
                f"Version: {version}"
            )

        except Exception as e:
            logger.error(f"Error in scheduled job: {str(e)}", exc_info=True)
            for chat_id in chat_ids:
                try:
                    await self.bot_app.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "❌ 定時分析執行失敗\n\n"
                            f"詳情: {str(e)}\n\n"
                            "請檢查日誌"
                        ),
                    )
                except Exception:
                    pass

    def _run_analysis_sync(self, version: str = "") -> tuple:
        """Run analysis synchronously (called in thread)."""
        try:
            logger.info(f"Running analysis, version: {version}")

            orchestrator = AnalysisOrchestrator(version=version)

            # TODO: Load actual scraped data
            platforms_data = []
            countries_data = []

            result = orchestrator.run_analysis(platforms_data, countries_data)

            generator = ReportGenerator()
            html_content = generator.generate(result)

            report_path = str(self.report_store.save_report(html_content, version))
            logger.info(f"Report saved: {report_path}")

            summary_parts = [
                f"✅ 分析完成 v{version}",
                f"📊 平台數量: {len(result.platforms)}",
                f"📈 成功爬取: {sum(1 for p in result.platforms if p.status == 'success')}/{len(result.platforms)}",
            ]

            if result.alerts:
                summary_parts.append(f"⚠️ 警報: {len(result.alerts)} 個")
            if result.recommendations:
                summary_parts.append(f"💡 建議: {len(result.recommendations)} 個")

            return report_path, "\n".join(summary_parts), None

        except Exception as e:
            logger.error(f"Analysis sync failed: {str(e)}", exc_info=True)
            return None, None, str(e)
