"""add external_api_keys

Revision ID: 020_add_external_api_keys
Revises: 019_add_asset_authorized_source
"""

from alembic import op
import sqlalchemy as sa


revision = "020_add_external_api_keys"
down_revision = "019_add_asset_authorized_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_api_keys",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="read"),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_api_keys_key_hash", "external_api_keys", ["key_hash"], unique=False)
    op.create_index("ix_external_api_keys_scope", "external_api_keys", ["scope"], unique=False)


def downgrade() -> None:
    op.drop_table("external_api_keys")
