import logging

from telegram import Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, PicklePersistence, PersistenceInput, filters)

from app.config.settings import settings
from app.database.connection import Base, create_database, create_session_factory
from app.database import models  # noqa: F401
from app.handlers.account import account, help_page
from app.handlers.admin import (NAME, ORDER_ID, add_name, add_start, admin, admin_customer_orders, admin_order_details, admin_orders, cancel, failed_deliveries, find_order, find_order_start, inventory, redeliver)
from app.handlers.common import choose_language, set_language, show_main
from app.handlers.errors import error_handler
from app.handlers.orders import cancel_order, order_details, orders
from app.handlers.shop import confirm, product_details, quantity, shop
from app.handlers.start import start
from app.jobs import sweep_expired_orders
from app.payments.manual import ManualPaymentProvider
from app.payments.sepay import SePayPaymentProvider
from app.services.order_service import ORDER_ID_PATTERN
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)

ORDER_DETAILS_CALLBACK_PATTERN = rf"^order:{ORDER_ID_PATTERN}$"
CANCEL_ORDER_CALLBACK_PATTERN = rf"^cancel_order:{ORDER_ID_PATTERN}$"
ADMIN_ORDER_DETAILS_CALLBACK_PATTERN = rf"^admin:order:{ORDER_ID_PATTERN}$"


async def unmatched_callback(update: Update, context) -> None:
    query = update.callback_query
    logger.warning("Unmatched callback_data: %r", query.data if query else None)
    if query:
        await query.answer()


def build_application() -> Application:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    engine = create_database(settings.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(settings.database_url)

    # bot_data holds non-picklable runtime objects (DB session factory, payment
    # provider), so we must stop PicklePersistence from trying to save/restore
    # bot_data across restarts. Otherwise, on startup, PTB overwrites the fresh
    # bot_data we set below with a stale/empty version loaded from the pickle
    # file, wiping out "session_factory" and causing KeyError at runtime.
    persistence = PicklePersistence(
        filepath="bot_persistence.pkl",
        store_data=PersistenceInput(bot_data=False),
    )
    application = Application.builder().token(settings.bot_token).persistence(persistence).build()

    payment_provider = (
        SePayPaymentProvider(
            account_number=settings.sepay_bank_account_number,
            bank_code=settings.sepay_bank_code,
            template=settings.sepay_template,
            base_url=settings.sepay_base_url,
            currency=settings.currency,
        )
        if settings.payment_provider == "sepay"
        else ManualPaymentProvider()
    )

    application.bot_data.update(
        session_factory=factory,
        payment_provider=payment_provider,
        currency=settings.currency,
        order_timeout_minutes=15,
    )

    add_product = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_start, pattern=r"^admin:add$")],
        states={NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    find_admin_order = ConversationHandler(
        entry_points=[CallbackQueryHandler(find_order_start, pattern=r"^admin:find_order$")],
        states={ORDER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_order)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("failed_deliveries", failed_deliveries))
    application.add_handler(CommandHandler("redeliver", redeliver))
    application.add_handler(add_product)
    application.add_handler(find_admin_order)
    application.add_handler(CallbackQueryHandler(shop, pattern=r"^shop$"))
    application.add_handler(CallbackQueryHandler(product_details, pattern=r"^product:\d+$"))
    application.add_handler(CallbackQueryHandler(confirm, pattern=r"^confirm:\d+$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, quantity))
    application.add_handler(CallbackQueryHandler(orders, pattern=r"^orders$"))
    application.add_handler(CallbackQueryHandler(order_details, pattern=ORDER_DETAILS_CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(cancel_order, pattern=CANCEL_ORDER_CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(account, pattern=r"^account$"))
    application.add_handler(CallbackQueryHandler(help_page, pattern=r"^help$"))
    application.add_handler(CallbackQueryHandler(admin, pattern=r"^admin$"))
    application.add_handler(CallbackQueryHandler(inventory, pattern=r"^admin:inventory$"))
    application.add_handler(CallbackQueryHandler(admin_orders, pattern=r"^admin:orders$"))
    application.add_handler(CallbackQueryHandler(admin_customer_orders, pattern=r"^admin:customer:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_order_details, pattern=ADMIN_ORDER_DETAILS_CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(lambda update, context: show_main(update, context), pattern=r"^main$"))
    application.add_handler(CallbackQueryHandler(choose_language, pattern=r"^change_language$"))
    application.add_handler(CallbackQueryHandler(set_language, pattern=r"^language:(en|vi)$"))
    application.add_handler(CallbackQueryHandler(unmatched_callback))
    application.add_error_handler(error_handler)
    application.job_queue.run_repeating(sweep_expired_orders, interval=300, first=300)
    return application


def run() -> None:
    configure_logging(settings.log_level)
    logger.info("Starting shop bot in %s environment", settings.environment)
    logger.info(
        "Bot config: payment_provider=%s, currency=%s, admin_ids=%s, webhook_api_key_configured=%s",
        settings.payment_provider,
        settings.currency,
        bool(settings.admin_ids),
        bool(settings.sepay_api_key),
    )
    if settings.payment_provider == "sepay":
        logger.warning(
            "SePay mode is enabled. The bot will only confirm payment after a webhook arrives at /webhook/payment; "
            "make sure the FastAPI webhook service is running separately on a public HTTPS URL."
        )
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()