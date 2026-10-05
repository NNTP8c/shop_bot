from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class PaymentRequest:
    order_id: str
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class PaymentResult:
    provider: str
    transaction_id: str | None
    instructions: str
    qr_code_url: str | None = None
    reference_code: str | None = None
    metadata: dict | None = None


class PaymentProvider(Protocol):
    name: str

    def create_payment(self, request: PaymentRequest) -> PaymentResult:
        ...
