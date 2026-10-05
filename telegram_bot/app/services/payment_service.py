import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Order, Payment
from app.payments.base import PaymentProvider, PaymentRequest, PaymentResult

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, provider: PaymentProvider, currency: str):
        self.provider = provider
        self.currency = currency

    def start(self, session: Session, order: Order) -> PaymentResult:
        payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
        if payment is None:
            logger.info(
                "Creating payment record for order %s with provider %s and amount %s",
                order.id,
                getattr(self.provider, "name", type(self.provider).__name__),
                order.amount,
            )
            result = self.provider.create_payment(PaymentRequest(order.id, order.amount, self.currency))
            logger.info(
                "Generated payment metadata for order %s: reference=%s qr=%s",
                order.id,
                result.reference_code,
                result.qr_code_url,
            )
            session.add(
                Payment(
                    order_id=order.id,
                    provider=result.provider,
                    transaction_id=result.transaction_id,
                    amount=order.amount,
                    currency=self.currency,
                    raw_webhook_data=result.metadata,
                )
            )
            session.commit()
            logger.info("Payment row saved for order %s; awaiting SePay webhook confirmation.", order.id)
            return result
        metadata = payment.raw_webhook_data or {}
        logger.info("Existing payment row found for order %s; reusing stored metadata.", order.id)
        return PaymentResult(
            payment.provider,
            payment.transaction_id,
            "Payment already started. Contact support to complete it.",
            qr_code_url=metadata.get("qr_code_url"),
            reference_code=metadata.get("reference_code"),
            metadata=metadata,
        )
