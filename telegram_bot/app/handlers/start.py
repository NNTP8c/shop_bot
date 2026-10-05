from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.common import customer, show_main
from app.keyboards.main_menu import language_menu
from app.utils.i18n import t


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    item = customer(update, context)
    if item.language is None:
        await update.message.reply_text(t("en", "choose_language"), reply_markup=language_menu())
        return
    await show_main(update, context)
