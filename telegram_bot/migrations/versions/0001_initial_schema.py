"""Create the full shop schema and include later database changes in one unified migration."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None


def _create_initial_schema() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_spending", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.create_index(op.f("ix_customers_telegram_user_id"), "customers", ["telegram_user_id"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password", sa.Text(), nullable=False),
        sa.Column("two_factor", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sold_order_id", sa.String(length=32), nullable=True),
    )
    op.create_index(op.f("ix_products_type"), "products", ["type"], unique=False)
    op.create_index(op.f("ix_products_name"), "products", ["name"], unique=False)
    op.create_index(op.f("ix_products_status"), "products", ["status"], unique=False)

    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("payment_transaction_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_orders_customer_id"), "orders", ["customer_id"], unique=False)
    with op.batch_alter_table("orders") as batch_op:
        batch_op.create_unique_constraint("uq_orders_payment_transaction_id", ["payment_transaction_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.String(length=32), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("transaction_id", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="VND"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("raw_webhook_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_payments_order_id"), "payments", ["order_id"], unique=True)
    op.create_index(op.f("ix_payments_status"), "payments", ["status"], unique=False)
    with op.batch_alter_table("payments") as batch_op:
        batch_op.create_unique_constraint("uq_payments_transaction_id", ["transaction_id"])

    op.create_table(
        "product_inventory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_product_inventory_type"), "product_inventory", ["type"], unique=True)

    with op.batch_alter_table("products") as batch_op:
        batch_op.create_foreign_key(
            "fk_products_sold_order",
            "orders",
            ["sold_order_id"],
            ["id"],
        )


def _add_unmatched_webhooks() -> None:
    op.create_table(
        "unmatched_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("transaction_id", sa.String(length=255), nullable=True),
        sa.Column("order_id", sa.String(length=32), nullable=True),
        sa.Column("reference_code", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(op.f("ix_unmatched_webhooks_reason"), "unmatched_webhooks", ["reason"], unique=False)
    op.create_index(op.f("ix_unmatched_webhooks_transaction_id"), "unmatched_webhooks", ["transaction_id"], unique=False)
    op.create_index(op.f("ix_unmatched_webhooks_order_id"), "unmatched_webhooks", ["order_id"], unique=False)
    op.create_index(op.f("ix_unmatched_webhooks_reference_code"), "unmatched_webhooks", ["reference_code"], unique=False)


def _add_delivery_tracking() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("delivery_status", sa.String(length=16), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("delivery_attempted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("delivery_error", sa.Text(), nullable=True))


def upgrade() -> None:
    _create_initial_schema()
    _add_unmatched_webhooks()
    _add_delivery_tracking()


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("delivery_error")
        batch_op.drop_column("delivery_attempted_at")
        batch_op.drop_column("delivery_status")

    op.drop_index(op.f("ix_unmatched_webhooks_reference_code"), table_name="unmatched_webhooks")
    op.drop_index(op.f("ix_unmatched_webhooks_order_id"), table_name="unmatched_webhooks")
    op.drop_index(op.f("ix_unmatched_webhooks_transaction_id"), table_name="unmatched_webhooks")
    op.drop_index(op.f("ix_unmatched_webhooks_reason"), table_name="unmatched_webhooks")
    op.drop_table("unmatched_webhooks")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint("fk_products_sold_order", type_="foreignkey")
    op.drop_index(op.f("ix_product_inventory_type"), table_name="product_inventory")
    op.drop_table("product_inventory")
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_order_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_orders_customer_id"), table_name="orders")
    with op.batch_alter_table("orders") as batch_op:
        batch_op.create_unique_constraint("uq_orders_product_id", ["product_id"])
        batch_op.drop_constraint("uq_orders_payment_transaction_id", type_="unique")
    op.drop_table("orders")
    op.drop_index(op.f("ix_products_status"), table_name="products")
    op.drop_index(op.f("ix_products_name"), table_name="products")
    op.drop_index(op.f("ix_products_type"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_customers_telegram_user_id"), table_name="customers")
    op.drop_table("customers")
