from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class ProductStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    DISABLED = "disabled"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    email: Mapped[str] = mapped_column(String(320))
    password: Mapped[str] = mapped_column(Text)
    two_factor: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[ProductStatus] = mapped_column(String(16), default=ProductStatus.AVAILABLE, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sold_order_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("orders.id"))

    sold_order = relationship("Order", foreign_keys=[sold_order_id])

    def delivery_value(self) -> str:
        values = [self.email, self.password]
        if self.two_factor:
            values.append(self.two_factor)
        return "|".join(values)
