import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from telegram import Bot

from app.config.settings import settings
from app.database.models import DeliveryStatus, Order, OrderStatus, Product
from app.utils.i18n import t

logger = logging.getLogger(__name__)


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        return await value
    return value


async def _notify_admins(message: str) -> None:
    if not settings.bot_token or not settings.admin_ids:
        logger.warning("Skipping delivery admin notification because BOT_TOKEN or ADMIN_IDS is not configured.")
        return

    bot = Bot(token=settings.bot_token)
    for admin_id in settings.admin_ids:
        try:
            await _maybe_await(bot.send_message(chat_id=admin_id, text=message))
        except Exception:
            logger.exception("Failed to notify Telegram admin %s about delivery failure", admin_id)


class DeliveryService:
    def failed_deliveries(self, session):
        return list(
            session.scalars(
                select(Order)
                .where(Order.delivery_status == DeliveryStatus.FAILED)
                .order_by(Order.delivery_attempted_at.desc().nullslast(), Order.paid_at.desc(), Order.id)
            )
        )

    def _delivery_payload(self, session, order: Order) -> str:
        products = list(
            session.scalars(
                select(Product)
                .where(Product.sold_order_id == order.id)
                .order_by(Product.created_at)
            )
        )
        if not products:
            raise ValueError(
                f"Inventory issue: no product/key/file remains to deliver for order #{order.id}. "
                "The order was paid but the reserved inventory is missing."
            )
        if len(products) == 1:
            return products[0].delivery_value()
        return "\n".join(f"{index}. {product.delivery_value()}" for index, product in enumerate(products, start=1))

    async def deliver_order(self, session, bot, order_id: str) -> Order:
        order = session.scalar(select(Order).where(Order.id == order_id))
        if order is None:
            raise ValueError(f"Order #{order_id} was not found for delivery.")
        if order.delivery_status == DeliveryStatus.DELIVERED:
            logger.info("Skipping delivery for order %s because it is already marked delivered.", order.id)
            return order

        customer = order.customer
        customer_id = getattr(customer, "id", None)
        telegram_id = getattr(customer, "telegram_user_id", None) if customer is not None else None
        order.delivery_attempted_at = datetime.now(timezone.utc)
        now = order.delivery_attempted_at

        try:
            message = self._delivery_payload(session, order)
            if telegram_id is None:
                raise ValueError(f"Customer telegram_id is missing for order #{order.id}; cannot deliver the product.")
            if not hasattr(bot, "send_message"):
                raise ValueError(f"Delivery bot instance is invalid for order #{order.id}.")

            await _maybe_await(bot.send_message(chat_id=telegram_id, text=message))

            order.delivery_status = DeliveryStatus.DELIVERED
            order.delivery_error = None
            order.status = OrderStatus.COMPLETED
            order.completed_at = now
            logger.info("Delivered order %s to customer %s", order.id, telegram_id)
        except Exception as exc:
            logger.exception(
                "Delivery failed for order_id=%s customer_id=%s product_id=%s",
                order.id,
                customer_id,
                order.product_id,
            )
            order.delivery_status = DeliveryStatus.FAILED
            order.delivery_error = str(exc)
            order.status = OrderStatus.COMPLETED
            if order.completed_at is None:
                order.completed_at = now
            admin_message = (
                "⚠️ Order #"
                f"{order.id} was paid but product delivery FAILED. Customer: {customer_id}. "
                f"Reason: {exc}. Please deliver manually."
            )
            if "Inventory issue" in str(exc):
                admin_message = (
                    "⚠️ Inventory issue: Order #"
                    f"{order.id} was paid but no product/key/file remains to deliver. "
                    f"Customer: {customer_id}. Reason: {exc}. This may require a refund decision."
                )
            await _maybe_await(_notify_admins(admin_message))

            if telegram_id is not None:
                try:
                    customer_message = (
                        t(getattr(customer, "language", None), "processing_payment")
                    )
                    await _maybe_await(bot.send_message(chat_id=telegram_id, text=customer_message))
                except Exception:
                    logger.exception(
                        "Failed to notify customer %s after delivery failure for order %s",
                        telegram_id,
                        order.id,
                    )

        session.commit()
        return order
