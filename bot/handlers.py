"""
Command handlers for Telegram bot.

Implements all command handlers using python-telegram-bot v20 async API.
All user-facing messages are in Traditional Chinese (繁體中文).

Subscription model: users subscribe/unsubscribe to receive broadcast reports.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Update, Document
from telegram.ext import ContextTypes, CallbackContext

from analyzers.orchestrator import AnalysisOrchestrator
from report.generator import ReportGenerator
from storage.report_store import ReportStore
from storage.schedule_store import ScheduleStore
from storage.platform_store import PlatformStore
from storage.subscriber_store import SubscriberStore

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


def get_subscriber_store(context: ContextTypes.DEFAULT_TYPE) -> SubscriberStore:
    """Get SubscriberStore instance from bot_data."""
    return context.bot_data.get("subscriber_store")


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


async def broadcast_report(
    context: ContextTypes.DEFAULT_TYPE,
    report_path: str,
    summary_text: str,
    version: str,
) -> int:
    """
    Broadcast report to all subscribers.

    Args:
        context: Bot context
        report_path: Path to HTML report file
        summary_text: Summary message text
        version: Report version string

    Returns:
        Number of subscribers successfully notified
    """
    subscriber_store = get_subscriber_store(context)
    if not subscriber_store:
        logger.warning("No subscriber store available for broadcast")
        return 0

    chat_ids = subscriber_store.get_all_chat_ids()
    if not chat_ids:
        logger.info("No subscribers to broadcast to")
        return 0

    success_count = 0
    failed_ids = []

    for chat_id in chat_ids:
        try:
            # Send summary text
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 VoteFlux QA 分析報告\n\n{summary_text}",
            )
            # Send report as document
            if report_path:
                with open(report_path, "rb") as report_file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=report_file,
                        caption=f"VoteFlux QA 報告 - {version}",
                        filename=f"VoteFlux_Analysis_Report_{version}.html",
                    )
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send report to {chat_id}: {e}")
            failed_ids.append(chat_id)

    logger.info(
        f"Broadcast complete: {success_count}/{len(chat_ids)} subscribers notified"
    )
    if failed_ids:
        logger.warning(f"Failed to notify: {failed_ids}")

    return success_count


# ============================================================================
# Subscription Handlers
# ============================================================================


async def subscribe_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /subscribe command.

    Subscribes the current chat to receive broadcast reports.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"User {user.id} requesting /subscribe")

    subscriber_store = get_subscriber_store(context)
    if not subscriber_store:
        await update.message.reply_text("❌ 訂閱系統未初始化")
        return

    success, message = subscriber_store.subscribe(
        chat_id=chat_id,
        username=user.username or "",
        first_name=user.first_name or "",
    )
    total = subscriber_store.count()

    await update.message.reply_text(
        f"{message}\n\n目前共 {total} 位訂閱者"
    )


async def unsubscribe_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /unsubscribe command.

    Unsubscribes the current chat from broadcast reports.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"User {user.id} requesting /unsubscribe")

    subscriber_store = get_subscriber_store(context)
    if not subscriber_store:
        await update.message.reply_text("❌ 訂閱系統未初始化")
        return

    success, message = subscriber_store.unsubscribe(chat_id=chat_id)
    await update.message.reply_text(message)


async def mystatus_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /mystatus command.

    Shows current subscription status for the user.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"User {user.id} checking /mystatus")

    subscriber_store = get_subscriber_store(context)
    if not subscriber_store:
        await update.message.reply_text("❌ 訂閱系統未初始化")
        return

    if subscriber_store.is_subscribed(chat_id):
        info = subscriber_store.get_subscriber(chat_id)
        subscribed_at = info.get("subscribed_at", "未知")[:10]
        total = subscriber_store.count()
        await update.message.reply_text(
            f"✅ 你已訂閱 VoteFlux QA 報告\n\n"
            f"訂閱日期: {subscribed_at}\n"
            f"目前訂閱者: {total} 位\n\n"
            f"使用 /unsubscribe 取消訂閱"
        )
    else:
        await update.message.reply_text(
            f"❌ 你尚未訂閱\n\n"
            f"使用 /subscribe 開始訂閱，即可自動收到分析報告"
        )


# ============================================================================
# Command Handlers
# ============================================================================


async def start_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /start command.

    Sends welcome message. Also auto-subscribes new users if they're not yet subscribed.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"User {user.id} started bot")

    subscriber_store = get_subscriber_store(context)
    already_subscribed = subscriber_store and subscriber_store.is_subscribed(chat_id)

    name = user.first_name or "朋友"

    welcome_message = (
        f"👋 嗨，{name}！歡迎使用 VoteFlux QA 競品分析機器人 🤖\n\n"
        f"我會定期爬取 7 個預測市場平台資料，\n"
        f"自動生成競品分析 HTML 報告並傳送給你。\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📬 訂閱管理\n"
        f"  /subscribe — 訂閱自動報告\n"
        f"  /unsubscribe — 取消訂閱\n"
        f"  /mystatus — 查看訂閱狀態\n\n"
        f"🔧 手動執行\n"
        f"  /run — 立即執行分析並取得報告\n"
        f"  /history — 查看歷史報告\n\n"
        f"⏱️ 排程設定\n"
        f"  /schedule 09:00 — 每天09:00自動執行\n"
        f"  /schedule 09:00 1-5 — 週一至週五09:00\n\n"
        f"🌐 平台管理\n"
        f"  /platforms — 查看分析平台清單\n\n"
        f"❓ /help — 顯示完整指令說明\n"
        f"━━━━━━━━━━━━━━━\n"
    )

    if already_subscribed:
        welcome_message += "✅ 你已訂閱，報告將自動送達！"
    else:
        welcome_message += "👉 輸入 /subscribe 立即訂閱，自動收到分析報告！"

    await update.message.reply_text(welcome_message)


async def unknown_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle any non-command message.

    If user is new (not subscribed), show a brief welcome hint.
    If user is subscribed, show a command reminder.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = update.message.text or ""

    # Ignore empty or very long messages
    if not text or len(text) > 500:
        return

    logger.info(f"User {user.id} sent non-command message")

    subscriber_store = get_subscriber_store(context)
    is_subscribed = subscriber_store and subscriber_store.is_subscribed(chat_id)

    if is_subscribed:
        await update.message.reply_text(
            "💡 需要什麼幫助嗎？試試這些指令：\n\n"
            "  /run — 立即執行分析\n"
            "  /schedule — 查看/設定排程\n"
            "  /history — 查看歷史報告\n"
            "  /help — 完整指令說明"
        )
    else:
        name = user.first_name or "朋友"
        await update.message.reply_text(
            f"👋 嗨 {name}！我是 VoteFlux QA 競品分析機器人。\n\n"
            f"輸入 /subscribe 訂閱後，我會自動把競品分析報告傳給你！\n\n"
            f"或輸入 /start 查看完整功能介紹。"
        )


async def run_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /run command.

    Checks if analysis is already running, then runs analysis in background thread.
    After completion, broadcasts report to all subscribers.
    Also sends report directly to the command issuer.
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
            await progress_msg.edit_text(
                "❌ 分析失敗\n\n"
                f"錯誤: {error_msg}\n\n"
                "請檢查日誌並稍後重試"
            )
            logger.error(f"Analysis failed for user {user_id}: {error_msg}")
            return

        # Update progress message
        await progress_msg.edit_text(
            f"✅ 分析完成！\n\n{summary_text}"
        )

        # Send report to the command issuer
        if report_path:
            with open(report_path, "rb") as report_file:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=report_file,
                    caption=f"VoteFlux QA 報告 - {version}",
                    filename=f"VoteFlux_Analysis_Report_{version}.html",
                )
            logger.info(f"Report sent to user {user_id}")

        # Broadcast to all subscribers (excluding current user to avoid duplication)
        subscriber_store = get_subscriber_store(context)
        if subscriber_store:
            chat_ids = [
                cid for cid in subscriber_store.get_all_chat_ids()
                if cid != update.effective_chat.id
            ]
            broadcast_count = 0
            for chat_id in chat_ids:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"📊 VoteFlux QA 分析報告\n\n{summary_text}",
                    )
                    if report_path:
                        with open(report_path, "rb") as rf:
                            await context.bot.send_document(
                                chat_id=chat_id,
                                document=rf,
                                caption=f"VoteFlux QA 報告 - {version}",
                                filename=f"VoteFlux_Analysis_Report_{version}.html",
                            )
                    broadcast_count += 1
                except Exception as e:
                    logger.error(f"Broadcast to {chat_id} failed: {e}")

            if broadcast_count > 0:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"📤 已廣播給 {broadcast_count} 位訂閱者",
                )

    except Exception as e:
        logger.error(f"Error in /run handler: {str(e)}", exc_info=True)
        await progress_msg.edit_text(
            "❌ 執行出錯\n\n"
            f"詳情: {str(e)}\n\n"
            "請檢查日誌"
        )

    finally:
        set_analysis_running(context, False)


async def status_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /status command.

    Shows current bot status including analysis status, last run, next schedule,
    platform count, report count, and subscriber count.
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} queried status")

    try:
        report_store = get_report_store(context)
        schedule_store = get_schedule_store(context)
        subscriber_store = get_subscriber_store(context)

        running_status = "🔄 進行中" if is_analysis_running(context) else "✅ 待命"

        recent_reports = report_store.list_reports(limit=1)
        if recent_reports:
            last_report = recent_reports[0]
            last_run_text = (
                f"⏱️ 最後執行: {last_report['created_at'].strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            last_run_text = "⏱️ 最後執行: 尚未執行"

        schedule = schedule_store.get_schedule()
        next_runs = await asyncio.to_thread(_get_next_runs, schedule, count=1)
        next_run_text = (
            f"📅 下次排程: {next_runs[0].strftime('%Y-%m-%d %H:%M:%S')}"
            if next_runs else "📅 下次排程: 未設定"
        )

        total_reports = len(report_store.list_reports(limit=100))
        platform_store = get_platform_store(context)
        platform_count = platform_store.count() if platform_store else 0
        subscriber_count = subscriber_store.count() if subscriber_store else 0

        status_message = (
            f"🤖 機器人狀態\n\n"
            f"狀態: {running_status}\n"
            f"{last_run_text}\n"
            f"{next_run_text}\n\n"
            f"📊 統計\n"
            f"平台數: {platform_count}\n"
            f"報告數: {total_reports}\n"
            f"訂閱者: {subscriber_count} 位\n"
            f"排程表: {schedule}"
        )

        await update.message.reply_text(status_message)

    except Exception as e:
        logger.error(f"Error in /status handler: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ 查詢失敗\n\n錯誤: {str(e)}")


async def schedule_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /schedule command.

    Supports simple time format (no cron knowledge needed):
      /schedule              → show current schedule
      /schedule 09:00        → every day at 09:00
      /schedule 09:00 1-5    → weekdays (Mon-Fri) at 09:00
      /schedule 09:00 1,3,5  → Mon/Wed/Fri at 09:00
      /schedule 09:00 0      → Sunday only at 09:00
      /schedule off          → disable scheduled runs

    Also still accepts raw cron (5 fields) for power users.
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
                [f"  • {run.strftime('%Y-%m-%d %H:%M')} ({_day_name(run.weekday())})"
                 for run in next_runs]
            )
            human_desc = _cron_to_human(current_schedule)

            message = (
                f"📅 當前排程\n\n"
                f"說明: {human_desc}\n"
                f"Cron: `{current_schedule}`\n\n"
                f"下次 3 次執行:\n{next_runs_text}\n\n"
                f"━━━━ 設定方式 ━━━━\n"
                f"`/schedule 09:00` — 每天早上9點\n"
                f"`/schedule 18:30 1-5` — 週一至週五18:30\n"
                f"`/schedule 08:00 1,3,5` — 週一三五08:00\n"
                f"`/schedule off` — 停用排程"
            )
            await update.message.reply_text(message, parse_mode="Markdown")
            return

        # Parse input
        raw = context.args

        # Handle "off" / "disable"
        if raw[0].lower() in ("off", "disable", "停用", "關閉"):
            # Set to a far-future cron (run once a year on Feb 30 — never triggers)
            # Better: just use a placeholder cron that won't run and mark disabled
            new_cron = "0 0 31 2 *"  # Feb 31 never exists → never runs
            schedule_store.set_schedule(new_cron)
            scheduler = context.bot_data.get("scheduler")
            if scheduler:
                scheduler.update_schedule(new_cron)
            await update.message.reply_text(
                "⏸️ 定時排程已停用\n\n使用 `/schedule HH:MM` 重新啟用"
            )
            return

        # Parse simple format or raw cron
        parsed_cron, parse_error = _parse_schedule_input(raw)

        if parse_error:
            await update.message.reply_text(
                f"❌ 格式錯誤：{parse_error}\n\n"
                f"正確格式範例：\n"
                f"`/schedule 09:00` — 每天09:00\n"
                f"`/schedule 18:30 1-5` — 週一至週五18:30\n"
                f"`/schedule 08:00 1,3,5` — 週一三五08:00\n"
                f"`/schedule off` — 停用排程",
                parse_mode="Markdown",
            )
            return

        logger.info(f"User {user_id} updating schedule to cron: {parsed_cron}")

        if schedule_store.set_schedule(parsed_cron):
            next_runs = await asyncio.to_thread(_get_next_runs, parsed_cron, count=3)
            next_runs_text = "\n".join(
                [f"  • {run.strftime('%Y-%m-%d %H:%M')} ({_day_name(run.weekday())})"
                 for run in next_runs]
            )
            human_desc = _cron_to_human(parsed_cron)

            # Update live scheduler
            scheduler = context.bot_data.get("scheduler")
            if scheduler:
                scheduler.update_schedule(parsed_cron)

            await update.message.reply_text(
                f"✅ 排程已更新\n\n"
                f"說明: {human_desc}\n"
                f"Cron: `{parsed_cron}`\n\n"
                f"下次 3 次執行:\n{next_runs_text}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"❌ 無效的時間設定\n\n"
                f"請確認格式，例如：\n"
                f"`/schedule 09:00`\n"
                f"`/schedule 18:30 1-5`",
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Error in /schedule handler: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ 操作失敗\n\n錯誤: {str(e)}")


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
            await update.message.reply_text("📜 報告歷史\n\n尚無報告")
            return

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
        await update.message.reply_text(f"❌ 查詢失敗\n\n錯誤: {str(e)}")


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
            return

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
        await update.message.reply_text(f"❌ 送出報告失敗\n\n錯誤: {str(e)}")


async def help_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /help command.

    Lists all available commands with descriptions.
    """
    help_message = (
        "📖 VoteFlux QA 機器人命令說明\n\n"
        "📬 訂閱命令\n"
        "`/subscribe` - 訂閱分析報告\n"
        "  加入訂閱，自動收到定期報告\n\n"
        "`/unsubscribe` - 取消訂閱\n"
        "  取消後不再收到自動報告\n\n"
        "`/mystatus` - 查看我的訂閱狀態\n"
        "  顯示是否已訂閱及訂閱日期\n\n"
        "🔧 執行命令\n"
        "`/run` - 立即執行 QA 分析\n"
        "  執行分析並廣播報告給所有訂閱者\n\n"
        "📊 查詢命令\n"
        "`/status` - 查看機器人狀態\n"
        "  顯示當前狀態、最後執行時間、訂閱人數\n\n"
        "`/history` - 查看報告歷史\n"
        "  列出最近 10 個報告\n\n"
        "`/report <版本>` - 取得特定報告\n"
        "  例: `/report 20260306_001234`\n\n"
        "⏱️ 排程命令\n"
        "`/schedule` - 查看當前排程\n\n"
        "`/schedule HH:MM` - 每天指定時間執行\n"
        "  例: `/schedule 09:00` (每天早上9點)\n\n"
        "`/schedule HH:MM 週範圍` - 指定星期執行\n"
        "  例: `/schedule 09:00 1-5` (週一至週五)\n"
        "  例: `/schedule 08:00 1,3,5` (週一三五)\n\n"
        "`/schedule off` - 停用排程\n\n"
        "🌐 平台管理\n"
        "`/platforms` - 查看所有分析平台\n\n"
        "`/add_platform <ID> <名稱> <網址> [角色]`\n"
        "  例: `/add_platform betfair Betfair https://betfair.com 英國博彩`\n\n"
        "`/remove_platform <ID>` - 移除平台\n"
    )

    logger.info(f"User {update.effective_user.id} requested help")
    await update.message.reply_text(help_message, parse_mode="Markdown")


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
                f"✅ {message}\n\n目前剩餘 {total} 個平台"
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
    """Get next scheduled run times from cron expression."""
    try:
        from croniter import croniter
        base = datetime.now()
        cron = croniter(cron_expr, base)
        return [cron.get_next(datetime) for _ in range(count)]
    except Exception as e:
        logger.error(f"Error calculating next runs: {str(e)}")
        return []


def _parse_schedule_input(args: list) -> tuple[str, Optional[str]]:
    """
    Parse simple schedule input and convert to cron expression.

    Supported formats:
      ["09:00"]           → "0 9 * * *"     (every day)
      ["09:00", "1-5"]    → "0 9 * * 1-5"  (Mon-Fri)
      ["09:00", "1,3,5"]  → "0 9 * * 1,3,5" (Mon/Wed/Fri)
      ["09:00", "*"]      → "0 9 * * *"     (every day explicit)
      ["0","9","*","*","*"] → "0 9 * * *"   (raw cron, pass-through)

    Returns:
        (cron_expr, error_message) — error_message is None if successful
    """
    if not args:
        return "", "沒有輸入任何參數"

    # If 5 args → treat as raw cron expression
    if len(args) == 5:
        return " ".join(args), None

    # Expect first arg to be HH:MM
    time_str = args[0]
    days_str = args[1] if len(args) > 1 else "*"

    # Parse HH:MM
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        return "", f"時間格式錯誤：`{time_str}`\n請使用 HH:MM 格式，例如 09:00 或 18:30"

    # Validate days field
    valid_day_chars = set("0123456789,-*/")
    if not all(c in valid_day_chars for c in days_str):
        return "", f"星期格式錯誤：`{days_str}`\n請使用數字 0-7（0/7=日，1=一...6=六）或範圍如 1-5"

    cron_expr = f"{minute} {hour} * * {days_str}"
    return cron_expr, None


def _cron_to_human(cron_expr: str) -> str:
    """
    Convert cron expression to human-readable Traditional Chinese description.

    Handles common patterns only. Falls back to cron string for complex ones.
    """
    DAYS_MAP = {
        "0": "日", "1": "一", "2": "二", "3": "三",
        "4": "四", "5": "五", "6": "六", "7": "日",
    }

    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return cron_expr

        minute, hour, day, month, dow = parts

        # Build time string
        try:
            time_str = f"{int(hour):02d}:{int(minute):02d}"
        except ValueError:
            time_str = f"{hour}:{minute}"

        # Interpret day-of-week
        if dow in ("*", "*/1"):
            day_str = "每天"
        elif dow == "1-5":
            day_str = "週一至週五"
        elif dow == "0-6" or dow == "1-7":
            day_str = "每天"
        elif dow == "6,0" or dow == "0,6":
            day_str = "週六日"
        elif "," in dow:
            names = [f"週{DAYS_MAP.get(d.strip(), d.strip())}" for d in dow.split(",")]
            day_str = "、".join(names)
        elif "-" in dow:
            start, end = dow.split("-", 1)
            day_str = f"週{DAYS_MAP.get(start, start)}至週{DAYS_MAP.get(end, end)}"
        elif dow in DAYS_MAP:
            day_str = f"每週{DAYS_MAP[dow]}"
        else:
            day_str = f"dow={dow}"

        # Special: never-run placeholder
        if day == "31" and month == "2":
            return "⏸️ 已停用"

        return f"{day_str} {time_str}"

    except Exception:
        return cron_expr


def _day_name(weekday: int) -> str:
    """Convert Python weekday (0=Mon) to Chinese label."""
    names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    return names[weekday] if 0 <= weekday <= 6 else ""
