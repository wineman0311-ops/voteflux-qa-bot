"""
Task scheduler using APScheduler for automated analysis runs.

Manages scheduling of periodic QA analysis and report generation.
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
    cron expressions. Results are sent to Telegram chat.
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

        Reads cron expression from schedule_store and starts the scheduler.
        """
        try:
            if self.scheduler.running:
                logger.warning("Scheduler already running")
                return

            cron_expr = self.schedule_store.get_schedule()
            logger.info(f"Starting scheduler with cron: {cron_expr}")

            # Start the scheduler
            self.scheduler.start()

            # Add job for scheduled analysis
            self._add_scheduled_job(cron_expr)

            logger.info("Scheduler started successfully")

        except Exception as e:
            logger.error(f"Failed to start scheduler: {str(e)}", exc_info=True)
            raise

    def stop(self) -> None:
        """
        Shutdown the scheduler gracefully.

        Removes jobs and shuts down the scheduler.
        """
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

        Removes the old job and creates a new one with the updated schedule.

        Args:
            cron_expr: New cron expression

        Returns:
            True if schedule was updated successfully, False otherwise
        """
        try:
            logger.info(f"Updating schedule to: {cron_expr}")

            # Validate and save new schedule
            if not self.schedule_store.set_schedule(cron_expr):
                logger.error(f"Invalid cron expression: {cron_expr}")
                return False

            # Remove old job if exists
            if self.scheduler.running:
                try:
                    self.scheduler.remove_job(self._job_id)
                    logger.info("Removed old scheduled job")
                except Exception as e:
                    logger.warning(f"Could not remove old job: {str(e)}")

                # Add new job
                self._add_scheduled_job(cron_expr)

            logger.info("Schedule updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to update schedule: {str(e)}", exc_info=True)
            return False

    def get_next_runs(self, count: int = 3) -> List[datetime]:
        """
        Get the next scheduled run times.

        Args:
            count: Number of next runs to return

        Returns:
            List of datetime objects for next scheduled runs
        """
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
        """
        Add scheduled analysis job to scheduler.

        Args:
            cron_expr: Cron expression for scheduling
        """
        try:
            # Parse cron expression (minute, hour, day, month, day_of_week)
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
        The scheduled job that runs analysis and sends results.

        This async method is called by the scheduler at the specified time.
        It runs analysis in a thread to avoid blocking the scheduler.
        """
        try:
            logger.info("Scheduled job triggered")

            # Generate version
            version = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Get TG_CHAT_ID from settings
            from config.settings import TG_CHAT_ID

            if not TG_CHAT_ID:
                logger.error("TG_CHAT_ID not configured")
                return

            # Send initial message
            await self.bot_app.bot.send_message(
                chat_id=TG_CHAT_ID,
                text="🔄 定時分析開始\n\n請稍候...",
            )

            # Run analysis in thread
            report_path, summary_text, error_msg = await asyncio.to_thread(
                self._run_analysis_sync, version
            )

            if error_msg:
                # Send error message
                error_message = (
                    "❌ 定時分析失敗\n\n"
                    f"錯誤: {error_msg}\n\n"
                    "請檢查日誌"
                )
                await self.bot_app.bot.send_message(
                    chat_id=TG_CHAT_ID,
                    text=error_message,
                )
                logger.error(f"Scheduled analysis failed: {error_msg}")
                return

            # Send summary
            summary_message = f"✅ 定時分析完成\n\n{summary_text}"
            await self.bot_app.bot.send_message(
                chat_id=TG_CHAT_ID,
                text=summary_message,
            )

            # Send report
            if report_path:
                with open(report_path, "rb") as report_file:
                    await self.bot_app.bot.send_document(
                        chat_id=TG_CHAT_ID,
                        document=report_file,
                        caption=f"VoteFlux QA 報告 - {version}",
                        filename=f"VoteFlux_Analysis_Report_{version}.html",
                    )

            logger.info(f"Scheduled job completed successfully, version: {version}")

        except Exception as e:
            logger.error(
                f"Error in scheduled job: {str(e)}", exc_info=True
            )

            # Try to send error notification
            try:
                from config.settings import TG_CHAT_ID

                await self.bot_app.bot.send_message(
                    chat_id=TG_CHAT_ID,
                    text=(
                        "❌ 定時分析執行失敗\n\n"
                        f"詳情: {str(e)}\n\n"
                        "請檢查日誌"
                    ),
                )
            except Exception as notify_error:
                logger.error(f"Failed to send error notification: {notify_error}")

    def _run_analysis_sync(self, version: str = "") -> tuple:
        """
        Run analysis synchronously (called in thread from async context).

        Args:
            version: Version string for this analysis

        Returns:
            Tuple of (report_path, summary_text, error_msg)
        """
        try:
            logger.info(f"Running analysis, version: {version}")

            # Initialize orchestrator
            orchestrator = AnalysisOrchestrator(version=version)

            # TODO: Load actual scraped data
            # For now, use empty data to avoid errors
            platforms_data = []
            countries_data = []

            # Run analysis
            result = orchestrator.run_analysis(platforms_data, countries_data)

            # Generate HTML report
            generator = ReportGenerator()
            html_content = generator.generate(result)

            # Save report
            report_path = str(self.report_store.save_report(html_content, version))
            logger.info(f"Report saved: {report_path}")

            # Generate summary
            summary_parts = [
                f"✅ 分析完成 v{version}",
                f"📊 平台數量: {len(result.platforms)}",
                f"📈 成功爬取: {sum(1 for p in result.platforms if p.status == 'success')}/{len(result.platforms)}",
            ]

            if result.alerts:
                summary_parts.append(f"⚠️ 警報: {len(result.alerts)} 個")

            if result.recommendations:
                summary_parts.append(
                    f"💡 建議: {len(result.recommendations)} 個"
                )

            summary_text = "\n".join(summary_parts)

            return report_path, summary_text, None

        except Exception as e:
            logger.error(f"Analysis sync failed: {str(e)}", exc_info=True)
            return None, None, str(e)
