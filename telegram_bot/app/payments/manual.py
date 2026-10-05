from app.payments.base import PaymentRequest, PaymentResult


class ManualPaymentProvider:
    name = "manual"

    def create_payment(self, request: PaymentRequest) -> PaymentResult:
        return PaymentResult(
            provider=self.name,
            transaction_id=None,
            instructions=(
                f"Manual payment for order #{request.order_id}: "
                f"send {request.amount:.2f} {request.currency} to the administrator, "
                "then contact support with your order ID. "
                "If payment is not completed within 15 minutes, the order will automatically cancel."
            ),
        )
