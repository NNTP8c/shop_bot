"""Store each customer's interface language."""

from alembic import op
import sqlalchemy as sa

revision = "0002_customer_language"
down_revision = "0001_initial_schema"


def upgrade() -> None:
    op.add_column("customers", sa.Column("language", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "language")