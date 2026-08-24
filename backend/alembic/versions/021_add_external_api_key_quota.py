"""add external_api_keys quota columns

Revision ID: 021_add_external_api_key_quota
Revises: 020_add_external_api_keys
"""

from alembic import op
import sqlalchemy as sa


revision = "021_add_external_api_key_quota"
down_revision = "020_add_external_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("external_api_keys", sa.Column("quota", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("external_api_keys", sa.Column("quota_used", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("external_api_keys", "quota_used")
    op.drop_column("external_api_keys", "quota")
