from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.handlers.common import customer, session
from app.keyboards.main_menu import navigation
from app.database.models import Product
from app.services.order_service import OrderService, UnauthorizedOrderError
from app.utils.i18n import localized_status, t


async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = customer(update, context).language or "en"
    db = session(context)
    try:
        items = OrderService().for_customer(db, customer(update, context).id)
        text = t(language, "orders_empty") if not items else t(language, "orders_select")
        rows = [[InlineKeyboardButton(f"#{item.id} · {item.product.type} x{item.quantity} · {item.amount:,.0f}₫", callback_data=f"order:{item.id}")] for item in items]
        rows.append(navigation(language))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
    finally:
        db.close()


async def order_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = customer(update, context).language or "en"
    order_id = query.data.split(":", 1)[1]
    db = session(context)
    try:
        try:
            order = OrderService().get_for_customer(db, order_id, customer(update, context).id)
        except UnauthorizedOrderError:
            await query.edit_message_text(t(language, "order_not_found"), reply_markup=InlineKeyboardMarkup([navigation(language)]))
            return
        text = (
            f"📦 Order #{order.id}\n"
            f"{t(language, 'order_type')}: {order.product.type}\n"
            f"{t(language, 'quantity')}: {order.quantity}\n"
            f"{t(language, 'amount')}: {order.amount:,.0f}₫\n"
            f"{t(language, 'status')}: {localized_status(language, order.status)}\n"
            f"{t(language, 'payment_status')}: {localized_status(language, order.payment_status)}\n"
            f"{t(language, 'delivery_status')}: {localized_status(language, order.delivery_status or 'pending')}\n"
            f"{t(language, 'date')}: {order.created_at:%Y-%m-%d %H:%M}"
        )
        if order.delivery_error:
            text += f"\n{t(language, 'delivery_error')}: {order.delivery_error}"
        if str(order.status) == "completed":
            products = list(db.scalars(select(Product).where(Product.sold_order_id == order.id).order_by(Product.created_at)))
            text += f"\n\n{t(language, 'delivery')}:\n" + "\n".join(product.delivery_value() for product in products)
        rows = []
        if str(order.status) in {"pending", "paid"}:
            rows.append([InlineKeyboardButton(t(language, "cancel_order"), callback_data=f"cancel_order:{order.id}")])
        rows.append(navigation(language))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
    finally:
        db.close()


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = customer(update, context).language or "en"
    order_id = query.data.split(":", 1)[1]
    db = session(context)
    try:
        try:
            OrderService().cancel_for_customer(db, order_id, customer(update, context).id)
        except UnauthorizedOrderError:
            await query.edit_message_text(t(language, "order_not_found"), reply_markup=InlineKeyboardMarkup([navigation(language)]))
            return
        except ValueError as error:
            await query.edit_message_text(t(language, "order_cancelled_error") if str(error) == "Completed orders cannot be cancelled" else str(error), reply_markup=InlineKeyboardMarkup([navigation(language)]))
            return
        await query.edit_message_text(
            t(language, "order_cancelled"),
            reply_markup=InlineKeyboardMarkup([navigation(language)]),
        )
    finally:
        db.close()
