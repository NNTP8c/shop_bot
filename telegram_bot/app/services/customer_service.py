from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Customer


class CustomerService:
    def get_or_create(self, session: Session, telegram_user) -> Customer:
        customer = session.scalar(select(Customer).where(Customer.telegram_user_id == telegram_user.id))
        now = datetime.now(timezone.utc)
        if customer is None:
            customer = Customer(
                telegram_user_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name or "",
                last_name=telegram_user.last_name,
            )
            session.add(customer)
        else:
            customer.username = telegram_user.username
            customer.first_name = telegram_user.first_name or ""
            customer.last_name = telegram_user.last_name
            customer.last_activity = now
        session.commit()
        session.refresh(customer)
        return customer

    def set_language(self, session: Session, telegram_user_id: int, language: str) -> Customer:
        if language not in {"en", "vi"}:
            raise ValueError("Unsupported language")
        customer = session.scalar(select(Customer).where(Customer.telegram_user_id == telegram_user_id))
        if customer is None:
            raise ValueError("Customer not found")
        customer.language = language
        session.commit()
        session.refresh(customer)
        return customer
