import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram update", exc_info=context.error)
    error_text = str(context.error) if context.error else "unknown error"
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            f"Bot error while handling this update: {error_text}. Please retry or contact support with the exact error text above."
        )
