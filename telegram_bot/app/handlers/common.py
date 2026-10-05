from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.database.models import Customer
from app.keyboards.main_menu import language_menu, main_menu
from app.services.customer_service import CustomerService
from app.utils.i18n import t


def session(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"]()


def customer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Customer:
    db = session(context)
    try:
        return CustomerService().get_or_create(db, update.effective_user)
    finally:
        db.close()

async def show_main(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Welcome to the shop.") -> None:
    language = customer(update, context).language or "en"
    if text == "Welcome to the shop.":
        text = t(language, "welcome")
    markup = main_menu(update.effective_user.id in settings.admin_ids, language)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(t("en", "choose_language"), reply_markup=language_menu())


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = query.data.split(":", 1)[1]
    db = session(context)
    try:
        CustomerService().set_language(db, update.effective_user.id, language)
    finally:
        db.close()
    await show_main(update, context, t(language, "language_changed") + "\n\n" + t(language, "welcome"))
