"""add character field source markers"""
from alembic import op
import sqlalchemy as sa

revision = "024_add_character_field_sources"
down_revision = "023_remove_legacy_asset_sampling_metadata"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("characters", sa.Column("field_sources_json", sa.Text(), nullable=False, server_default="{}"))
    op.alter_column("characters", "field_sources_json", server_default=None)

def downgrade() -> None:
    op.drop_column("characters", "field_sources_json")
