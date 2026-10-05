from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Product, ProductInventory, ProductStatus


class ProductUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class ProductBatchEntry:
    type: str
    name: str
    email: str
    password: str
    two_factor: str | None
    price: Decimal
    quantity: int


@dataclass(frozen=True)
class ProductListing:
    id: int
    type: str
    price: Decimal
    quantity: int


class ProductService:
    def available(self, session: Session) -> list[ProductListing]:
        inventory_rows = session.execute(
            select(ProductInventory.type, ProductInventory.quantity)
            .where(ProductInventory.quantity > 0)
            .order_by(ProductInventory.type)
        ).all()
        if not inventory_rows:
            return []

        rows = session.execute(
            select(Product.id, Product.type, Product.price)
            .where(Product.status == ProductStatus.AVAILABLE)
            .order_by(Product.created_at)
        ).all()

        first_products_by_type: dict[str, tuple[int, Decimal]] = {}
        for product_id, product_type, price in rows:
            key = product_type.strip().casefold()
            first_products_by_type.setdefault(key, (product_id, price))

        listings: list[ProductListing] = []
        for inventory_type, quantity in inventory_rows:
            key = inventory_type.strip().casefold()
            representative = first_products_by_type.get(key)
            if representative is None:
                continue
            product_id, price = representative
            listings.append(
                ProductListing(
                    id=product_id,
                    type=inventory_type.strip(),
                    price=price,
                    quantity=int(quantity),
                )
            )
        return listings

    def available_listing(self, session: Session, product_id: int) -> ProductListing | None:
        product = session.get(Product, product_id)
        if product is None or product.status != ProductStatus.AVAILABLE:
            return None

        inventory = session.scalar(
            select(ProductInventory)
            .where(func.lower(func.trim(ProductInventory.type)) == product.type.strip().casefold())
        )
        if inventory is None or inventory.quantity <= 0:
            return None

        return ProductListing(
            id=product.id,
            type=product.type.strip(),
            price=product.price,
            quantity=int(inventory.quantity),
        )

    def get(self, session: Session, product_id: int) -> Product | None:
        return session.get(Product, product_id)

    def add(self, session: Session, product_type: str, name: str, email: str, password: str, two_factor: str | None, price: Decimal) -> Product:
        if not product_type.strip() or not name.strip() or not email.strip() or not password:
            raise ValueError("Product type, name, email, and password are required")
        if price < 0:
            raise ValueError("Price cannot be negative")

        trimmed_type = product_type.strip()
        trimmed_name = name.strip()
        inventory = session.scalar(
            select(ProductInventory).where(func.lower(func.trim(ProductInventory.type)) == trimmed_type.casefold()).with_for_update()
        )
        canonical_type = inventory.type if inventory is not None else trimmed_type

        product = Product(
            type=trimmed_type,
            name=trimmed_name,
            email=email.strip(),
            password=password,
            two_factor=two_factor or None,
            price=price,
            status=ProductStatus.AVAILABLE,
        )
        session.add(product)
        session.flush()

        if inventory is None:
            inventory = ProductInventory(type=canonical_type, quantity=0)
            session.add(inventory)
        inventory.quantity += 1
        session.commit()
        session.refresh(product)
        return product

    def bulk_add(self, session: Session, entries: list[ProductBatchEntry]) -> dict[str, list[dict[str, object]]]:
        created: list[dict[str, object]] = []
        updated: list[dict[str, object]] = []
        try:
            for entry in entries:
                key = entry.type.strip().casefold()
                inventory = session.scalar(select(ProductInventory).where(func.lower(func.trim(ProductInventory.type)) == key).with_for_update())
                old_quantity = inventory.quantity if inventory is not None else 0
                canonical_type = inventory.type if inventory is not None else entry.type.strip()
                if inventory is None:
                    inventory = ProductInventory(type=canonical_type, quantity=0)
                    session.add(inventory)
                    session.flush()

                for _ in range(entry.quantity):
                    product = Product(
                        type=entry.type.strip(),
                        name=entry.name.strip(),
                        email=entry.email.strip(),
                        password=entry.password,
                        two_factor=entry.two_factor or None,
                        price=entry.price,
                        status=ProductStatus.AVAILABLE,
                    )
                    session.add(product)
                    session.flush()

                inventory.quantity += entry.quantity
                if old_quantity == 0:
                    created.append({"type": canonical_type, "quantity": entry.quantity})
                else:
                    updated.append({"type": canonical_type, "old_quantity": old_quantity, "new_quantity": inventory.quantity})
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"created": created, "updated": updated}

    def counts(self, session: Session) -> dict[str, int]:
        status_rows = session.execute(select(Product.status, func.count(Product.id)).group_by(Product.status)).all()
        counts = {str(status): count for status, count in status_rows}
        for status in ProductStatus:
            counts.setdefault(str(status), 0)
        counts["available"] = int(counts.get(str(ProductStatus.AVAILABLE), 0))
        counts["total"] = int(sum(counts.get(str(status), 0) for status in ProductStatus))
        return counts
