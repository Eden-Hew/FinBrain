import asyncio

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.config import get_settings
from app.integrations.telegram.handlers import (
    cancel_command,
    capture,
    content_message,
    error_handler,
    help_command,
    privacy_command,
    review_callback,
    start,
    status_command,
    type_callback,
    whoami,
)


async def post_init(application: Application) -> None:
    await application.bot.delete_webhook(drop_pending_updates=False)
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Connect to FinBrain"),
            BotCommand("capture", "Capture a protected business record"),
            BotCommand("status", "Show recent submission status"),
            BotCommand("cancel", "Cancel the active capture"),
            BotCommand("privacy", "Explain data handling"),
            BotCommand("help", "Show available commands"),
            BotCommand("whoami", "Show your Telegram setup ID"),
        ]
    )


async def post_shutdown(application: Application) -> None:
    tasks = [
        application.bot_data.get("heartbeat_task"),
        application.bot_data.get("reminder_task"),
    ]
    for task in (item for item in tasks if item is not None):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def build_application() -> Application:
    token = get_settings().telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("capture", capture))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("whoami", whoami))
    application.add_handler(
        CallbackQueryHandler(type_callback, pattern=r"^(type:|cancel:selection)")
    )
    application.add_handler(
        CallbackQueryHandler(review_callback, pattern=r"^(confirm|change|cancel):")
    )
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.Document.ALL | filters.CONTACT) & ~filters.COMMAND,
            content_message,
        )
    )
    application.add_error_handler(error_handler)
    return application
