"""
Command handlers for Telegram bot.

Implements all command handlers using python-telegram-bot v20 async API.
All user-facing messages are in Traditional Chinese (繁體中文).
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Update, Document
from telegram.ext import ContextTypes, CallbackContext

from config.settings import TG_CHAT_ID
from analyzers.orchestrator import AnalysisOrchestrator
from report.generator import ReportGenerator
from storage.report_store import ReportStore
from storage.schedule_store import ScheduleStore
from storage.platform_store import PlatformStore

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================


def get_report_store(context: ContextTypes.DEFAULT_TYPE) -> ReportStore:
    """Get ReportStore instance from bot_data."""
    return context.bot_data.get("report_store")


def get_schedule_store(context: ContextTypes.DEFAULT_TYPE) -> ScheduleStore:
    """Get ScheduleStore instance from bot_data."""
    return context.bot_data.get("schedule_store")


def get_platform_store(context: ContextTypes.DEFAULT_TYPE) -> PlatformStore:
    """Get PlatformStore instance from bot_data."""
    return context.bot_data.get("platform_store")


def is_analysis_running(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if analysis is currently running."""
    return context.bot_data.get("is_running", False)


def set_analysis_running(context: ContextTypes.DEFAULT_TYPE, running: bool) -> None:
    """Set analysis running flag."""
    context.bot_data["is_running"] = running


def run_analysis_sync(version: str = "") -> tuple:
    """
    Run analysis synchronously (called in thread).

    This function runs in a separate thread to avoid blocking the bot.

    Args:
        version: Optional version string

    Returns:
        Tuple of (report_path, summary_text, error_msg)
        - report_path: Path to generated HTML report
        - summary_text: Summary message text
        - error_msg: Error message if failed, None if successful
    """
    try:
        logger.info("Starting analysis run")

        # Initialize orchestrator with version
        if not version:
            version = datetime.now().strftime("%Y%m%d_%H%M%S")

        orchestrator = AnalysisOrchestrator(version=version)

        # TODO: Load actual scraped data
        # For now, use empty data to avoid errors
        from config.platforms import PlatformData, CountryNews

        platforms_data = []
        countries_data = []

        # Run analysis
        result = orchestrator.run_analysis(platforms_data, countries_data)

        # Generate HTML report
        generator = ReportGenerator()
        html_content = generator.generate(result)

        # Get next version if not provided
        report_store = ReportStore()
        if not version or version.startswith("%"):
            version = report_store.get_next_version()

        # Save report
        report_path = str(report_store.save_report(html_content, version))
        logger.info(f"Report saved to {report_path}")

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
        logger.error(f"Analysis failed: {str(e)}", exc_info=True)
        return None, None, str(e)


# ============================================================================
# Command Handlers
# ============================================================================


async def start_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /start command.

    Sends welcome message with available commands.
    """
    welcome_message = (
        "歡迎使用 VoteFlux QA 自動化機器人 🤖\n\n"
        "可用命令:\n"
        "📋 /run - 執行分析\n"
        "📊 /status - 查看狀態\n"
        "⏱️ /schedule - 管理排程\n"
        "📜 /history - 查看報告歷史\n"
        "📄 /report - 取得特定報告\n"
        "🌐 /platforms - 查看平台清單\n"
        "➕ /add_platform - 新增平台\n"
        "➖ /remove_platform - 移除平台\n"
        "❓ /help - 顯示幫助\n\n"
        "輸入 /help 了解更多詳情"
    )

    logger.info(f"User {update.effective_user.id} started bot")
    await update.message.reply_text(welcome_message)


async def run_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /run command.

    Checks if analysis is already running, then runs analysis in background thread.
    Sends progress updates and final report to user.
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} triggered /run command")

    # Check if analysis is already running
    if is_analysis_running(context):
        await update.message.reply_text(
            "⚠️ 分析已在進行中，請稍候...\n"
            "請勿重複執行"
        )
        return

    # Set running flag
    set_analysis_running(context, True)

    # Send initial message
    progress_msg = await update.message.reply_text(
        "🔄 分析進行中，請稍候...\n"
        "這可能需要數分鐘"
    )

    try:
        # Generate version
        version = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Run analysis in thread to avoid blocking
        logger.info("Running analysis in background thread")
        report_path, summary_text, error_msg = await asyncio.to_thread(
            run_analysis_sync, version
        )

        if error_msg:
            # Analysis failed
            error_message = (
                "❌ 分析失敗\n\n"
                f"錯誤: {error_msg}\n\n"
                "請檢查日誌並稍後重試"
            )
            await progress_msg.edit_text(error_message)
            logger.error(f"Analysis failed for user {user_id}: {error_msg}")
            return

        # Update progress message with summary
        await progress_msg.edit_text(
            f"✅ 分析完成！\n\n{summary_text}"
        )

        # Send report as document
        if report_path:
            with open(report_path, "rb") as report_file:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=report_file,
                    caption=f"VoteFlux QA 報告 - {version}",
                    filename=f"VoteFlux_Analysis_Report_{version}.html",
                )
            logger.info(f"Report sent to user {user_id}")

    except Exception as e:
        logger.error(f"Error in /run handler: {str(e)}", exc_info=True)
        error_msg = (
            "❌ 執行出錯\n\n"
            f"詳情: {str(e)}\n\n"
            "請檢查日誌"
        )
        await progress_msg.edit_text(error_msg)

    finally:
        # Clear running flag
        set_analysis_running(context, False)


async def status_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /status command.

    Shows current bot status including:
    - Analysis running status
    - Last run time
    - Next scheduled run
    - Platform and report counts
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} queried status")

    try:
        report_store = get_report_store(context)
        schedule_store = get_schedule_store(context)

        # Get analysis running status
        running_status = "🔄 進行中" if is_analysis_running(context) else "✅ 待命"

        # Get last report info
        recent_reports = report_store.list_reports(limit=1)
        if recent_reports:
            last_report = recent_reports[0]
            last_run_text = (
                f"⏱️ 最後執行: {last_report['created_at'].strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            last_run_text = "⏱️ 最後執行: 尚未執行"

        # Get next scheduled run
        schedule = schedule_store.get_schedule()
        next_runs = await asyncio.to_thread(_get_next_runs, schedule, count=1)
        if next_runs:
            next_run_text = (
                f"📅 下次排程: {next_runs[0].strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            next_run_text = "📅 下次排程: 未設定"

        # Count stats
        total_reports = len(report_store.list_reports(limit=100))
        platform_store = get_platform_store(context)
        platform_count = platform_store.count() if platform_store else 0

        status_message = (
            f"🤖 機器人狀態\n\n"
            f"狀態: {running_status}\n"
            f"{last_run_text}\n"
            f"{next_run_text}\n\n"
            f"📊 統計\n"
            f"平台數: {platform_count}\n"
            f"報告數: {total_reports}\n"
            f"排程表: {schedule}"
        )

        await update.message.reply_text(status_message)

    except Exception as e:
        logger.error(f"Error in /status handler: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ 查詢失敗\n\n錯誤: {str(e)}"
        )


async def schedule_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /schedule command.

    - No args: show current schedule and next 3 run times
    - With args: update schedule with new cron expression
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} accessed schedule handler")

    try:
        schedule_store = get_schedule_store(context)
        current_schedule = schedule_store.get_schedule()

        if not context.args:
            # Show current schedule
            next_runs = await asyncio.to_thread(
                _get_next_runs, current_schedule, count=3
            )

            next_runs_text = "\n".join(
                [f"  • {run.strftime('%Y-%m-%d %H:%M:%S')}" for run in next_runs]
            )

            message = (
                f"📅 當前排程\n\n"
                f"Cron 表達式: `{current_schedule}`\n\n"
                f"下次 3 次執行:\n"
                f"{next_runs_text}\n\n"
                f"使用 `/schedule <cron表達式>` 更新排程\n"
                f"例: `/schedule 0 9 * * 1-5` (工作日 9:00)"
            )

            await update.message.reply_text(
                message,
                parse_mode="Markdown"
            )

        else:
            # Update schedule
            new_cron = " ".join(context.args)
            logger.info(f"User {user_id} attempting to update schedule to: {new_cron}")

            if schedule_store.set_schedule(new_cron):
                # Validate and get next runs
                try:
                    next_runs = await asyncio.to_thread(
                        _get_next_runs, new_cron, count=3
                    )
                    next_runs_text = "\n".join(
                        [f"  • {run.strftime('%Y-%m-%d %H:%M:%S')}" for run in next_runs]
                    )

                    message = (
                        f"✅ 排程已更新\n\n"
                        f"新表達式: `{new_cron}`\n\n"
                        f"下次 3 次執行:\n"
                        f"{next_runs_text}"
                    )

                    # Update scheduler in bot_data if available
                    scheduler = context.bot_data.get("scheduler")
                    if scheduler:
                        scheduler.update_schedule(new_cron)
                        logger.info("Scheduler updated successfully")

                    await update.message.reply_text(
                        message,
                        parse_mode="Markdown"
                    )

                except Exception as e:
                    logger.error(f"Error getting next runs: {str(e)}")
                    await update.message.reply_text(
                        f"⚠️ 排程已保存，但無法計算下次執行時間\n\n"
                        f"請檢查 Cron 表達式: {new_cron}"
                    )

            else:
                await update.message.reply_text(
                    f"❌ 無效的 Cron 表達式: {new_cron}\n\n"
                    f"格式應為: `minute hour day month dayofweek`\n"
                    f"例: `0 9 * * 1-5` (工作日 9:00)"
                )

    except Exception as e:
        logger.error(f"Error in /schedule handler: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ 操作失敗\n\n錯誤: {str(e)}"
        )


async def history_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /history command.

    Lists recent 10 reports with version, date, and file size.
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested history")

    try:
        report_store = get_report_store(context)
        reports = report_store.list_reports(limit=10)

        if not reports:
            await update.message.reply_text(
                "📜 報告歷史\n\n"
                "尚無報告"
            )
            return

        # Format report list
        report_lines = ["📜 最近報告\n"]
        for i, report in enumerate(reports, 1):
            size_kb = report["size"] / 1024
            date_str = report["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            report_lines.append(
                f"{i}. {report['version']}\n"
                f"   📅 {date_str} | 📦 {size_kb:.1f} KB"
            )

        message = "\n".join(report_lines)
        await update.message.reply_text(
            f"{message}\n\n"
            f"使用 `/report <版本>` 獲取特定報告\n"
            f"例: `/report 20260306_001234`"
        )

    except Exception as e:
        logger.error(f"Error in /history handler: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ 查詢失敗\n\n錯誤: {str(e)}"
        )


async def report_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /report <version> command.

    Retrieves a specific report by version and sends it as a document.
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested report")

    if not context.args:
        await update.message.reply_text(
            "❌ 請指定報告版本\n\n"
            "使用: `/report <版本>`\n"
            "例: `/report 20260306_001234`\n\n"
            "使用 `/history` 查看可用版本"
        )
        return

    try:
        version = context.args[0]
        report_store = get_report_store(context)

        report_path = report_store.get_report_path(version)

        if not report_path:
            await update.message.reply_text(
                f"❌ 找不到報告: {version}\n\n"
                f"使用 `/history` 查看可用版本"
            )
            logger.warning(f"User {user_id} requested non-existent report: {version}")
            return

        # Send report as document
        with open(report_path, "rb") as report_file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=report_file,
                caption=f"VoteFlux QA 報告 - {version}",
                filename=f"VoteFlux_Analysis_Report_{version}.html",
            )

        logger.info(f"Report {version} sent to user {user_id}")

    except Exception as e:
        logger.error(f"Error in /report handler: {str(e)}", exc_info=True)
        await update.message.reply_text(
            f"❌ 送出報告失敗\n\n錯誤: {str(e)}"
        )


async def help_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /help command.

    Lists all available commands with descriptions.
    """
    help_message = (
        "📖 VoteFlux QA 機器人命令說明\n\n"
        "🔧 執行命令\n"
        "`/run` - 立即執行 QA 分析\n"
        "  執行分析並生成報告\n\n"
        "📊 查詢命令\n"
        "`/status` - 查看機器人狀態\n"
        "  顯示當前狀態、最後執行時間、下次排程\n\n"
        "`/history` - 查看報告歷史\n"
        "  列出最近 10 個報告\n\n"
        "`/report <版本>` - 取得特定報告\n"
        "  例: `/report 20260306_001234`\n\n"
        "⏱️ 排程命令\n"
        "`/schedule` - 查看當前排程\n"
        "  顯示 Cron 表達式和下次執行時間\n\n"
        "`/schedule <表達式>` - 更新排程\n"
        "  格式: `分 時 日 月 周`\n"
        "  例: `/schedule 0 9 * * 1-5` (工作日 9:00)\n\n"
        "🌐 平台管理\n"
        "`/platforms` - 查看所有分析平台\n\n"
        "`/add_platform <ID> <名稱> <網址> [角色]`\n"
        "  新增分析平台\n"
        "  例: `/add_platform betfair Betfair https://betfair.com 英國博彩平台`\n\n"
        "`/remove_platform <ID>` - 移除平台\n"
        "  例: `/remove_platform betfair`\n\n"
        "❓ 幫助\n"
        "`/help` - 顯示此幫助信息\n\n"
        "`/start` - 顯示歡迎信息\n"
    )

    logger.info(f"User {update.effective_user.id} requested help")
    await update.message.reply_text(
        help_message,
        parse_mode="Markdown"
    )


# ============================================================================
# Platform Management Handlers
# ============================================================================


async def platforms_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /platforms command.

    Lists all currently configured analysis platforms.
    """
    logger.info(f"User {update.effective_user.id} requested platform list")

    try:
        platform_store = get_platform_store(context)
        if not platform_store:
            await update.message.reply_text("❌ 平台管理未初始化")
            return

        platforms = platform_store.get_platforms()

        if not platforms:
            await update.message.reply_text(
                "🌐 分析平台清單\n\n尚無平台\n\n"
                "使用 `/add_platform` 新增平台"
            )
            return

        lines = ["🌐 分析平台清單\n"]
        for i, p in enumerate(platforms, 1):
            role_tag = f" ({p['role']})" if p.get('role') else ""
            lines.append(
                f"{i}. **{p['name']}**{role_tag}\n"
                f"   ID: `{p['id']}`\n"
                f"   🔗 {p['url']}"
            )

        lines.append(f"\n共 {len(platforms)} 個平台")
        lines.append("\n使用 `/add_platform` 新增 | `/remove_platform` 移除")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    except Exception as e:
        logger.error(f"Error in /platforms: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 查詢失敗\n\n錯誤: {e}")


async def add_platform_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /add_platform command.

    Usage: /add_platform <id> <name> <url> [role]
    Example: /add_platform betfair Betfair https://betfair.com 英國博彩平台
    """
    logger.info(f"User {update.effective_user.id} adding platform")

    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "❌ 參數不足\n\n"
            "格式: `/add_platform <ID> <名稱> <網址> [角色]`\n\n"
            "範例:\n"
            "`/add_platform betfair Betfair https://betfair.com 英國博彩平台`\n"
            "`/add_platform metaculus Metaculus https://metaculus.com`",
            parse_mode="Markdown",
        )
        return

    try:
        platform_store = get_platform_store(context)
        if not platform_store:
            await update.message.reply_text("❌ 平台管理未初始化")
            return

        platform_id = context.args[0]
        name = context.args[1]
        url = context.args[2]
        role = " ".join(context.args[3:]) if len(context.args) > 3 else "競品"

        success, message = platform_store.add_platform(platform_id, name, url, role)

        if success:
            total = platform_store.count()
            await update.message.reply_text(
                f"✅ {message}\n\n"
                f"ID: `{platform_id}`\n"
                f"名稱: {name}\n"
                f"網址: {url}\n"
                f"角色: {role}\n\n"
                f"目前共 {total} 個平台",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(f"❌ {message}")

    except Exception as e:
        logger.error(f"Error in /add_platform: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 新增失敗\n\n錯誤: {e}")


async def remove_platform_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /remove_platform command.

    Usage: /remove_platform <id>
    Example: /remove_platform betfair
    """
    logger.info(f"User {update.effective_user.id} removing platform")

    if not context.args:
        await update.message.reply_text(
            "❌ 請指定要移除的平台 ID\n\n"
            "格式: `/remove_platform <ID>`\n"
            "例: `/remove_platform betfair`\n\n"
            "使用 `/platforms` 查看所有平台 ID",
            parse_mode="Markdown",
        )
        return

    try:
        platform_store = get_platform_store(context)
        if not platform_store:
            await update.message.reply_text("❌ 平台管理未初始化")
            return

        platform_id = context.args[0].lower().strip()

        # Show confirmation info
        platform = platform_store.get_platform(platform_id)
        if not platform:
            await update.message.reply_text(
                f"❌ 找不到平台: `{platform_id}`\n\n"
                f"使用 `/platforms` 查看所有平台",
                parse_mode="Markdown",
            )
            return

        success, message = platform_store.remove_platform(platform_id)

        if success:
            total = platform_store.count()
            await update.message.reply_text(
                f"✅ {message}\n\n"
                f"目前剩餘 {total} 個平台"
            )
        else:
            await update.message.reply_text(f"❌ {message}")

    except Exception as e:
        logger.error(f"Error in /remove_platform: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 移除失敗\n\n錯誤: {e}")


# ============================================================================
# Utility Functions
# ============================================================================


def _get_next_runs(cron_expr: str, count: int = 3) -> list:
    """
    Get next scheduled run times from cron expression.

    Args:
        cron_expr: Cron expression string
        count: Number of next runs to return

    Returns:
        List of datetime objects for next scheduled runs
    """
    try:
        from croniter import croniter
        base = datetime.now()
        cron = croniter(cron_expr, base)
        return [cron.get_next(datetime) for _ in range(count)]
    except Exception as e:
        logger.error(f"Error calculating next runs: {str(e)}")
        return []
