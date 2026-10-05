from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import overload
from urllib.parse import urlencode

from app.payments.base import PaymentRequest, PaymentResult


class SePayPaymentProvider:
    name = "sepay"

    def __init__(
        self,
        account_number: str,
        bank_code: str,
        template: str = "img",
        base_url: str = "https://qr.sepay.vn",
        currency: str = "VND",
    ):
        self.account_number = account_number
        self.bank_code = bank_code
        self.template = template or "img"
        self.base_url = base_url.rstrip("/")
        self.currency = currency.upper()

    @staticmethod
    def _normalize_amount(amount: Decimal, currency: str) -> str:
        try:
            amount_decimal = Decimal(str(amount))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid payment amount: {amount!r}") from exc

        quantizer = Decimal("1") if currency.upper() == "VND" else Decimal("0.01")
        normalized = amount_decimal.quantize(quantizer, rounding=ROUND_HALF_UP)
        return format(normalized, "f")

    @overload
    def create_payment(self, request: PaymentRequest) -> PaymentResult: ...

    @overload
    def create_payment(self, request: str, amount: Decimal | None = None) -> PaymentResult: ...

    def create_payment(self, request: PaymentRequest | str, amount: Decimal | None = None) -> PaymentResult:
        if isinstance(request, PaymentRequest):
            order_id = request.order_id
            amount_decimal = request.amount
            currency = request.currency.upper()
        else:
            order_id = str(request)
            amount_decimal = amount or Decimal("0")
            currency = self.currency

        reference_code = order_id
        normalized_amount = self._normalize_amount(amount_decimal, currency)
        params = {
            "acc": self.account_number,
            "bank": self.bank_code,
            "amount": normalized_amount,
            "des": reference_code,
        }

        qr_code_url = f"{self.base_url}/{self.template}?{urlencode(params)}"
        metadata = {
            "reference_code": reference_code,
            "qr_code_url": qr_code_url,
            "currency": currency,
            "amount": normalized_amount,
        }

        return PaymentResult(
            provider=self.name,
            transaction_id=None,
            instructions=(
                f"SePay/VietQR payment for order #{order_id}.\n\n"
                f"Transfer {normalized_amount} {currency} to the configured bank account, "
                f"then use transfer content: {reference_code}.\n\n"
                "The payment will be detected automatically via SePay webhook."
            ),
            qr_code_url=qr_code_url,
            reference_code=reference_code,
            metadata=metadata,
        )
