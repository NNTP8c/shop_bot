from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from app.config.settings import settings
from app.database.models import Customer, Order
from app.handlers.common import customer, session
from app.keyboards.admin import admin_menu, admin_orders_menu
from app.keyboards.main_menu import navigation
from app.services.delivery_service import DeliveryService
from app.services.order_service import OrderService
from app.services.product_service import ProductBatchEntry, ProductService
from app.utils.helpers import parse_price
from app.utils.i18n import localized_status, t

NAME = 0
ORDER_ID = 1


def authorized(update: Update) -> bool:
    return update.effective_user.id in settings.admin_ids


def _language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return customer(update, context).language or "en"

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        await query.edit_message_text(t("en", "admin_access_denied"))
        return
    language = _language(update, context)
    await query.edit_message_text(t(language, "admin_panel"), reply_markup=admin_menu(language))

async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        return
    language = _language(update, context)
    db = session(context)
    try:
        counts = ProductService().counts(db)
        text = (
            f"📦 {t(language, 'inventory')}\n\n{t(language, 'total')}: {counts.get('total', 0)}\n"
            f"{t(language, 'available')}: {counts.get('available', 0)}\n{t(language, 'sold')}: {counts.get('sold', 0)}\n"
            f"{t(language, 'disabled')}: {counts.get('disabled', 0)}"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([navigation(language)]))
    finally:
        db.close()


def _customer_label(customer: Customer, language: str = "en") -> str:
    name = " ".join(part for part in [customer.first_name, customer.last_name] if part).strip()
    username = f"@{customer.username}" if customer.username else t(language, "no_username")
    return f"{name or username} (#{customer.id})"


def _date_value(value) -> str:
    return value.isoformat() if value is not None else "-"


def _order_details(order: Order, language: str = "en") -> str:
    return (
        f"{t(language, 'admin_order')} #{order.id}\n"
        f"{t(language, 'field_order_id')}: {order.id}\n"
        f"{t(language, 'field_customer_id')}: {order.customer_id}\n"
        f"{t(language, 'field_product_id')}: {order.product_id}\n"
        f"{t(language, 'quantity')}: {order.quantity}\n"
        f"{t(language, 'amount')}: {order.amount}\n"
        f"{t(language, 'payment_status')}: {localized_status(language, order.payment_status)}\n"
        f"{t(language, 'status')}: {localized_status(language, order.status)}\n"
        f"{t(language, 'delivery_status')}: {localized_status(language, order.delivery_status or 'pending')}\n"
        f"{t(language, 'field_delivery_attempted_at')}: {_date_value(order.delivery_attempted_at)}\n"
        f"{t(language, 'field_delivery_error')}: {order.delivery_error or '-'}\n"
        f"{t(language, 'field_payment_transaction_id')}: {order.payment_transaction_id or '-'}\n"
        f"{t(language, 'field_created_at')}: {_date_value(order.created_at)}\n"
        f"{t(language, 'field_paid_at')}: {_date_value(order.paid_at)}\n"
        f"{t(language, 'field_completed_at')}: {_date_value(order.completed_at)}"
    )


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        return
    language = _language(update, context)
    db = session(context)
    try:
        customers = OrderService().customers_with_orders(db)
        rows = [
            [InlineKeyboardButton(_customer_label(customer, language), callback_data=f"admin:customer:{customer.id}")]
            for customer in customers
        ]
        rows.extend(admin_orders_menu(language).inline_keyboard)
        text = f"{t(language, 'admin_orders')}\n\n{t(language, 'select_customer')}" if customers else f"{t(language, 'admin_orders')}\n\n{t(language, 'no_customers')}"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
    finally:
        db.close()


async def admin_customer_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        return
    language = _language(update, context)
    customer_id = int(query.data.rsplit(":", 1)[1])
    db = session(context)
    try:
        customer = db.get(Customer, customer_id)
        if customer is None:
            await query.edit_message_text(t(language, "customer_not_found"), reply_markup=admin_orders_menu(language))
            return
        items = OrderService().for_customer(db, customer.id)
        rows = [
            [InlineKeyboardButton(f"#{order.id} | {localized_status(language, order.status)} | {order.amount}", callback_data=f"admin:order:{order.id}")]
            for order in items
        ]
        rows.append([InlineKeyboardButton(t(language, "customers"), callback_data="admin:orders")])
        rows.extend(admin_orders_menu(language).inline_keyboard[-2:])
        await query.edit_message_text(
            f"{t(language, 'orders_for_customer', customer=_customer_label(customer, language))}\n\n{t(language, 'select_order')}",
            reply_markup=InlineKeyboardMarkup(rows),
        )
    finally:
        db.close()


async def admin_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        return
    language = _language(update, context)
    db = session(context)
    try:
        order = OrderService().get_by_id(db, query.data.split(":", 2)[2])
        if order is None:
            await query.edit_message_text(t(language, "order_not_found"), reply_markup=admin_orders_menu(language))
            return
        rows = [[InlineKeyboardButton(t(language, "customer_orders"), callback_data=f"admin:customer:{order.customer_id}")]]
        rows.extend(admin_orders_menu(language).inline_keyboard[-2:])
        await query.edit_message_text(_order_details(order, language), reply_markup=InlineKeyboardMarkup(rows))
    finally:
        db.close()


async def find_order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        return ConversationHandler.END
    language = _language(update, context)
    await query.edit_message_text(t(language, "send_order_id"), reply_markup=admin_orders_menu(language))
    return ORDER_ID


async def find_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not authorized(update):
        return ConversationHandler.END
    language = _language(update, context)
    order_id = update.message.text.strip()
    db = session(context)
    try:
        order = OrderService().get_by_id(db, order_id)
        text = _order_details(order, language) if order is not None else t(language, "order_not_found")
        await update.message.reply_text(text, reply_markup=admin_orders_menu(language))
    finally:
        db.close()
    return ConversationHandler.END

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not authorized(update):
        return ConversationHandler.END
    language = _language(update, context)
    await query.edit_message_text(t(language, "send_products"))
    return NAME

def parse_product_batch(text: str, language: str = "en") -> tuple[list[ProductBatchEntry], list[str]]:
    entries: list[ProductBatchEntry] = []
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 6:
            errors.append(t(language, "expected_product_fields", line=line_number))
            continue
        product_type, name, email, password, two_factor, price_text = fields
        try:
            price = parse_price(price_text)
            if not product_type or not name or not email or not password:
                raise ValueError
        except ValueError:
            errors.append(t(language, "invalid_product_fields", line=line_number))
            continue
        entry = ProductBatchEntry(product_type, name, email, password, None if two_factor == "-" else two_factor, price, 1)
        entries.append(entry)
    return entries, errors


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not authorized(update):
        return ConversationHandler.END
    language = _language(update, context)
    entries, errors = parse_product_batch(update.message.text, language)
    summary = [t(language, "batch_processed")]
    if entries:
        db = session(context)
        try:
            result = ProductService().bulk_add(db, entries)
        finally:
            db.close()
        if result["created"]:
            summary.append(t(language, "new_items") + "\n" + "\n".join(f"- {item['type']} x{item['quantity']}" for item in result["created"]))
        if result["updated"]:
            summary.append(t(language, "stock_updated") + "\n" + "\n".join(f"- {item['type']}: {item['old_quantity']} -> {item['new_quantity']}" for item in result["updated"]))
    if errors:
        summary.append(t(language, "failed_entries") + "\n" + "\n".join(f"- {error}" for error in errors))
    if not entries and not errors:
        summary.append(t(language, "failed_entries") + "\n- " + t(language, "no_product_lines"))
    await update.message.reply_text("\n\n".join(summary), reply_markup=admin_menu(language))
    return ConversationHandler.END

async def failed_deliveries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = _language(update, context) if authorized(update) else "en"
    if not authorized(update):
        await update.message.reply_text(t(language, "admin_access_denied"))
        return
    db = session(context)
    try:
        orders = DeliveryService().failed_deliveries(db)
        if not orders:
            await update.message.reply_text(t(language, "no_failed_deliveries"))
            return
        lines = [
            f"#{order.id} | {t(language, 'customer_label')} {order.customer_id} | "
            f"{t(language, 'payment_label')} {localized_status(language, order.payment_status)} | "
            f"{t(language, 'reason_label')}: {order.delivery_error or t(language, 'unknown')}"
            for order in orders
        ]
        await update.message.reply_text(t(language, "failed_deliveries") + "\n\n" + "\n".join(lines), reply_markup=admin_menu(language))
    finally:
        db.close()


async def redeliver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = _language(update, context) if authorized(update) else "en"
    if not authorized(update):
        await update.message.reply_text(t(language, "admin_access_denied"))
        return
    message = update.message.text.strip()
    parts = message.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(t(language, "redeliver_usage"))
        return
    order_id = parts[1].strip()
    db = session(context)
    try:
        order = OrderService().get_by_id(db, order_id)
        if order is None:
            await update.message.reply_text(f"{t(language, 'order_not_found')} #{order_id}")
            return
        try:
            result = await DeliveryService().deliver_order(db, context.bot, order.id)
        except Exception as exc:
            await update.message.reply_text(t(language, "delivery_retry_failed", order_id=order.id, error=exc))
            return
        status = result.delivery_status
        if status == "delivered":
            await update.message.reply_text(t(language, "redelivery_succeeded", order_id=order.id))
        else:
            await update.message.reply_text(
                t(language, "redelivery_attempted", order_id=order.id, status=localized_status(language, status), error=result.delivery_error or t(language, "unknown"))
            )
    finally:
        db.close()


async def cancel(update, context):
    language = _language(update, context)
    await update.message.reply_text(t(language, "cancelled"), reply_markup=admin_menu(language))
    return ConversationHandler.END
