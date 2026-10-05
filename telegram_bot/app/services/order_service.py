from datetime import datetime, timedelta, timezone
import logging
import secrets

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.database.models import Customer, DeliveryStatus, Order, OrderStatus, PaymentStatus, Product, ProductInventory, ProductStatus
from app.services.product_service import ProductUnavailableError

logger = logging.getLogger(__name__)

ORDER_ID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ORDER_ID_PATTERN = r"ORD\d{6}[A-Z0-9]{4}"


def generate_order_id(session: Session) -> str:
    date_part = datetime.now(timezone.utc).strftime("%y%m%d")
    while True:
        random_part = "".join(secrets.choice(ORDER_ID_ALPHABET) for _ in range(4))
        order_id = f"ORD{date_part}{random_part}"
        if session.get(Order, order_id) is None:
            return order_id


class UnauthorizedOrderError(Exception):
    pass


class OrderDatabaseError(RuntimeError):
    pass


def _raise_database_error(session: Session, operation: str, error: OperationalError) -> None:
    session.rollback()
    logger.exception(
        "Database error while %s. Check DATABASE_URL and run 'alembic upgrade head' to apply pending schema changes.",
        operation,
    )
    raise OrderDatabaseError(
        f"Unable to {operation}. Check the database schema with 'alembic upgrade head'."
    ) from error


class OrderService:
    def customers_with_orders(self, session: Session) -> list[Customer]:
        try:
            return list(
                session.scalars(
                    select(Customer)
                    .join(Order, Order.customer_id == Customer.id)
                    .distinct()
                    .order_by(Customer.first_name, Customer.last_name, Customer.id)
                )
            )
        except OperationalError as error:
            _raise_database_error(session, "load customers with orders", error)

    def get_by_id(self, session: Session, order_id: str) -> Order | None:
        try:
            return session.scalar(select(Order).where(Order.id == order_id))
        except OperationalError as error:
            _raise_database_error(session, "load an order", error)

    def create_order(self, session: Session, customer: Customer, product_id: int, quantity: int | None = None) -> Order:
        try:
            product = session.scalar(
                select(Product)
                .where(Product.id == product_id)
                .with_for_update()
            )
        except OperationalError as error:
            _raise_database_error(session, "create an order", error)
        if product is None:
            raise ProductUnavailableError("This product is no longer available")

        requested_quantity = 1 if quantity is None else quantity
        if requested_quantity <= 0:
            raise ProductUnavailableError("Purchase quantity must be greater than zero")

        try:
            inventory = session.scalar(
                select(ProductInventory)
                .where(func.lower(func.trim(ProductInventory.type)) == product.type.strip().casefold())
                .with_for_update()
            )
        except OperationalError as error:
            _raise_database_error(session, "create an order", error)
        if inventory is None or inventory.quantity <= 0 or (quantity is not None and requested_quantity > inventory.quantity):
            raise ProductUnavailableError("This product is no longer available")

        try:
            selected_products = list(session.scalars(
                select(Product)
                .where(
                    func.lower(func.trim(Product.type)) == product.type.strip().casefold(),
                    Product.status == ProductStatus.AVAILABLE,
                )
                .order_by(Product.created_at)
                .limit(requested_quantity)
                .with_for_update()
            ))
        except OperationalError as error:
            _raise_database_error(session, "create an order", error)
        if len(selected_products) != requested_quantity:
            raise ProductUnavailableError("Not enough products are available")

        fresh_customer = session.get(Customer, customer.id)
        if fresh_customer is None:
            raise ProductUnavailableError("Your customer profile could not be found. Please use /start again.")

        order = Order(
            id=generate_order_id(session),
            customer_id=fresh_customer.id,
            product_id=selected_products[0].id,
            quantity=requested_quantity,
            amount=selected_products[0].price * requested_quantity,
        )
        try:
            session.add(order)
            session.flush()
            inventory.quantity -= requested_quantity
            for selected_product in selected_products:
                selected_product.status = ProductStatus.RESERVED
                selected_product.sold_order_id = order.id
            session.commit()
        except IntegrityError as error:
            session.rollback()
            logger.exception("IntegrityError while creating order: %s", error.orig)
            raise ProductUnavailableError("Unable to complete the order because of a database conflict. Please try again.") from error
        except OperationalError as error:
            _raise_database_error(session, "create an order", error)
        try:
            session.refresh(order)
        except OperationalError as error:
            _raise_database_error(session, "refresh the created order", error)
        return order

    def mark_paid(self, session: Session, order_id: str, transaction_id: str | None = None) -> Order:
        try:
            order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        except OperationalError as error:
            _raise_database_error(session, "load an order for payment", error)
        if order is None:
            raise ValueError("Order not found")
        if order.payment_status == PaymentStatus.PAID:
            if order.delivery_status is None:
                order.delivery_status = DeliveryStatus.PENDING
            return order
        now = datetime.now(timezone.utc)
        order.payment_status = PaymentStatus.PAID
        order.status = OrderStatus.PAID
        order.payment_transaction_id = transaction_id
        order.delivery_status = DeliveryStatus.PENDING
        order.delivery_error = None
        order.delivery_attempted_at = None
        order.paid_at = now
        try:
            reserved_products = list(session.scalars(select(Product).where(Product.sold_order_id == order.id).with_for_update()))
        except OperationalError as error:
            _raise_database_error(session, "load reserved products", error)
        for product in reserved_products:
            product.status = ProductStatus.SOLD
            product.sold_at = now
        order.status = OrderStatus.COMPLETED
        order.completed_at = now
        order.customer.total_orders += 1
        order.customer.total_spending += order.amount
        try:
            session.commit()
            session.refresh(order)
        except OperationalError as error:
            _raise_database_error(session, "mark an order as paid", error)
        return order

    def for_customer(self, session: Session, customer_id: int) -> list[Order]:
        try:
            return list(session.scalars(select(Order).where(Order.customer_id == customer_id).order_by(Order.created_at.desc())))
        except OperationalError as error:
            _raise_database_error(session, "load order history", error)

    def get_for_customer(self, session: Session, order_id: str, customer_id: int) -> Order:
        try:
            order = session.scalar(select(Order).where(Order.id == order_id, Order.customer_id == customer_id))
        except OperationalError as error:
            _raise_database_error(session, "load a customer order", error)
        if order is None:
            raise UnauthorizedOrderError("Order not found")
        return order

    def cancel_unpaid_order(self, session: Session, order_id: str) -> Order:
        try:
            order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        except OperationalError as error:
            _raise_database_error(session, "load an order for cancellation", error)
        if order is None:
            raise ValueError("Order not found")
        if order.status == OrderStatus.CANCELLED:
            return order
        if order.status == OrderStatus.COMPLETED:
            raise ValueError("Completed orders cannot be cancelled")

        try:
            inventory = session.scalar(
                select(ProductInventory)
                .where(func.lower(func.trim(ProductInventory.type)) == order.product.type.strip().casefold())
                .with_for_update()
            )
            reserved_products = list(
                session.scalars(
                    select(Product)
                    .where(Product.sold_order_id == order.id, Product.status == ProductStatus.RESERVED)
                    .with_for_update()
                )
            )
        except OperationalError as error:
            _raise_database_error(session, "load an order for cancellation", error)
        if inventory is None or len(reserved_products) != order.quantity:
            raise OrderDatabaseError("Unable to cancel the order because its reserved products are unavailable.")

        inventory.quantity += order.quantity
        for product in reserved_products:
            product.status = ProductStatus.AVAILABLE
            product.sold_order_id = None
        order.status = OrderStatus.CANCELLED
        try:
            session.commit()
            session.refresh(order)
        except OperationalError as error:
            _raise_database_error(session, "cancel an order", error)
        return order

    def cancel_for_customer(self, session: Session, order_id: str, customer_id: int) -> Order:
        try:
            order = session.scalar(
                select(Order)
                .where(Order.id == order_id, Order.customer_id == customer_id)
                .with_for_update()
            )
        except OperationalError as error:
            _raise_database_error(session, "load an order for cancellation", error)
        if order is None:
            raise UnauthorizedOrderError("Order not found")
        return self.cancel_unpaid_order(session, order.id)

    def cancel_expired_orders(self, session: Session, older_than_minutes: int = 15) -> list[Order]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        try:
            orders = list(
                session.scalars(
                    select(Order)
                    .where(Order.status == OrderStatus.PENDING, Order.created_at < cutoff)
                    .with_for_update()
                )
            )
        except OperationalError as error:
            _raise_database_error(session, "load pending orders for cleanup", error)

        cancelled_orders: list[Order] = []
        for order in orders:
            if order.payment_status == PaymentStatus.PAID:
                continue
            cancelled_orders.append(self.cancel_unpaid_order(session, order.id))
        if cancelled_orders:
            session.commit()
        return cancelled_orders
