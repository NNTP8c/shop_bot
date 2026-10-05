import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.handlers.common import customer, session, show_main
from app.jobs import expire_order
from app.keyboards.shop import confirm_purchase, products
from app.services.order_service import OrderService, UnauthorizedOrderError
from app.services.product_service import ProductService, ProductUnavailableError
from app.services.payment_service import PaymentService
from app.utils.i18n import t

logger = logging.getLogger(__name__)


async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = customer(update, context).language or "en"
    db = session(context)
    try:
        items = ProductService().available(db)
        text = t(language, "no_products") if not items else t(language, "select_product")
        await query.edit_message_text(text, reply_markup=products(items, language))
    finally:
        db.close()


async def product_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = customer(update, context).language or "en"
    product_id = int(query.data.split(":")[1])
    db = session(context)
    try:
        listing = ProductService().available_listing(db, product_id)
        if listing is None:
            await query.edit_message_text(t(language, "product_unavailable"), reply_markup=products(ProductService().available(db), language))
            return
        context.user_data["purchase_product_id"] = product_id
        await query.edit_message_text(
            f"📦 {listing.type}\n💰 {t(language, 'price')}: {listing.price:,.0f}₫\n\n"
            f"{t(language, 'enter_quantity', quantity=listing.quantity)}"
        )
    finally:
        db.close()


async def quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = customer(update, context).language or "en"
    product_id = context.user_data.get("purchase_product_id")
    if product_id is None:
        await update.message.reply_text(t(language, "quantity_no_product"))
        return
    try:
        requested_quantity = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(t(language, "quantity_invalid"))
        return

    db = session(context)
    try:
        listing = ProductService().available_listing(db, product_id)
        if listing is None:
            await update.message.reply_text(
                t(language, "quantity_listing_unavailable")
            )
            return

        if not 0 < requested_quantity <= listing.quantity:
            await update.message.reply_text(
                t(language, "quantity_unavailable", requested=requested_quantity, available=listing.quantity, product_type=listing.type)
            )
            return

        try:
            order = OrderService().create_order(db, customer(update, context), product_id, requested_quantity)
            logger.info("Customer %s created order %s for %s x product_id=%s, amount=%s", customer(update, context).id, order.id, requested_quantity, product_id, order.amount)
        except ProductUnavailableError as error:
            await update.message.reply_text(_localized_order_error(language, str(error)))
            return
        payment = PaymentService(context.application.bot_data["payment_provider"], context.application.bot_data["currency"]).start(db, order)
        context.user_data.pop("purchase_product_id", None)

        provider_name = context.application.bot_data["payment_provider"].name
        logger.info("Order %s payment provider=%s reference=%s qr=%s", order.id, provider_name, payment.reference_code, payment.qr_code_url)
        currency = context.application.bot_data["currency"]
        if provider_name == "sepay":
            instructions = t(language, "sepay_payment", order_id=order.id, amount=order.amount, currency=currency, reference=payment.reference_code)
        else:
            instructions = t(language, "manual_payment", order_id=order.id, amount=f"{order.amount:.2f}", currency=currency)
        message = t(language, "order_created", order_id=order.id, quantity=requested_quantity, product_type=listing.type, currency=currency, instructions=instructions)

        timeout_minutes = context.application.bot_data.get("order_timeout_minutes", 15)
        context.application.job_queue.run_once(
            expire_order,
            timeout_minutes * 60,
            data=order.id,
            name=f"expire-order-{order.id}",
        )

        if provider_name == "sepay" and payment.qr_code_url:
            await update.message.reply_photo(
                photo=payment.qr_code_url,
                caption=message,
            )
            return

        await update.message.reply_text(
            message,
            reply_markup=confirm_purchase(order.id, language),
        )
    finally:
        db.close()


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    language = customer(update, context).language or "en"
    order_id = query.data.split(":", 1)[1]
    db = session(context)
    try:
        try:
            order = OrderService().get_for_customer(db, order_id, customer(update, context).id)
        except UnauthorizedOrderError:
            await query.edit_message_text(t(language, "order_not_found"))
            return
        await query.edit_message_text(
            t(language, "payment_received", order_id=order.id)
        )
    finally:
        db.close()


def _localized_order_error(language: str, error: str) -> str:
    known_errors = {
        "This product is no longer available": "product_not_available",
        "Purchase quantity must be greater than zero": "quantity_must_be_positive",
        "Not enough products are available": "not_enough_products",
        "Your customer profile could not be found. Please use /start again.": "profile_missing",
        "Unable to complete the order because of a database conflict. Please try again.": "order_conflict",
    }
    return t(language, known_errors[error]) if error in known_errors else error
