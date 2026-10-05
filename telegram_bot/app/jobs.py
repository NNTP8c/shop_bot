import asyncio
import logging

from telegram.ext import ContextTypes

from app.database.models import Order, OrderStatus
from app.services.order_service import OrderService

logger = logging.getLogger(__name__)


async def _notify_user_about_order(context: ContextTypes.DEFAULT_TYPE, order: Order, message: str) -> None:
    customer = order.customer
    if customer is None:
        logger.warning("Cannot notify customer for order %s because the relationship was not loaded.", order.id)
        return

    chat_id = getattr(customer, "telegram_user_id", None)
    if chat_id is None:
        logger.warning("Skipping notification for order %s because customer telegram_user_id is missing.", order.id)
        return

    try:
        await context.bot.send_message(chat_id=chat_id, text=message)
    except Exception:
        logger.exception("Failed to notify customer %s about order %s", customer.id, order.id)


async def expire_order(context: ContextTypes.DEFAULT_TYPE) -> None:
    order_id = context.job.data
    db = context.application.bot_data["session_factory"]()
    try:
        order = await asyncio.to_thread(OrderService().get_by_id, db, order_id)
        if order is None or order.status != OrderStatus.PENDING:
            return

        cancelled_order = await asyncio.to_thread(OrderService().cancel_unpaid_order, db, order_id)
        await _notify_user_about_order(
            context,
            cancelled_order,
            f"⏰ Order #{cancelled_order.id} expired before payment was confirmed. The order has been cancelled.",
        )
    except Exception:
        logger.exception("Failed to expire order %s", order_id)
    finally:
        db.close()


async def sweep_expired_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    timeout_minutes = context.application.bot_data.get("order_timeout_minutes", 15)
    db = context.application.bot_data["session_factory"]()
    try:
        orders = await asyncio.to_thread(OrderService().cancel_expired_orders, db, timeout_minutes)
        for order in orders:
            await _notify_user_about_order(
                context,
                order,
                f"⏰ Order #{order.id} expired before payment was confirmed. The order has been cancelled.",
            )
    except Exception:
        logger.exception("Failed to sweep expired orders")
    finally:
        db.close()
