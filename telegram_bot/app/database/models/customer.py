from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(255), default="")
    last_name: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    total_orders: Mapped[int] = mapped_column(default=0)
    total_spending: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(32), default="active")

    orders = relationship("Order", back_populates="customer")
