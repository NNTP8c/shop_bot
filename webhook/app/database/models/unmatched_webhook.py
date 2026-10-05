from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UnmatchedWebhook(Base):
    __tablename__ = "unmatched_webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    reason: Mapped[str] = mapped_column(String(64), index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(255), index=True)
    order_id: Mapped[str | None] = mapped_column(String(32), index=True)
    reference_code: Mapped[str | None] = mapped_column(String(255), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
