from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.handlers.common import customer, session
from app.keyboards.main_menu import navigation
from app.utils.i18n import t


async def account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = customer(update, context).language or "en"
    db = session(context)
    try:
        item = customer(update, context)
        await query.edit_message_text(
            f"{t(language, 'my_account')}\n\n{t(language, 'name')}: {item.first_name}\n"
            f"{t(language, 'total_orders')}: {item.total_orders}\n"
            f"{t(language, 'total_spending')}: {item.total_spending:,.0f}₫\n"
            f"{t(language, 'status')}: {t(language, 'status_active') if item.status == 'active' else item.status}",
            reply_markup=InlineKeyboardMarkup([navigation(language)]),
        )
    finally:
        db.close()


async def help_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = customer(update, context).language or "en"
    await query.edit_message_text(t(language, "help_text"), reply_markup=InlineKeyboardMarkup([navigation(language)]))
