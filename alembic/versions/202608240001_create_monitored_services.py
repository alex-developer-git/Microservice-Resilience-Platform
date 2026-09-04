from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "202608240001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monitored_services",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("health_check_path", sa.String(length=256), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("failure_threshold", sa.Integer(), nullable=False),
        sa.Column("recovery_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("cache_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_monitored_services_name", "monitored_services", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_monitored_services_name", table_name="monitored_services")
    op.drop_table("monitored_services")
