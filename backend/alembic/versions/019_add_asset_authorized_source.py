"""add asset_nodes.authorized_source

Revision ID: 019_add_asset_authorized_source
Revises: 018_allow_standalone_previs_scenes
"""

from alembic import op
import sqlalchemy as sa


revision = "019_add_asset_authorized_source"
down_revision = "018_allow_standalone_previs_scenes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("asset_nodes", sa.Column("authorized_source", sa.String(length=64), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("asset_nodes", "authorized_source")
