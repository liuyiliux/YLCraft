"""add character story link extract origin"""
from alembic import op
import sqlalchemy as sa

revision = "027_add_character_extract_origin"
down_revision = "026_add_character_workflow_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "character_story_links",
        sa.Column("extract_origin", sa.String(length=32), nullable=False, server_default="unknown"),
    )
    op.create_index("ix_character_story_links_extract_origin", "character_story_links", ["extract_origin"])
    op.alter_column("character_story_links", "extract_origin", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_character_story_links_extract_origin", table_name="character_story_links")
    op.drop_column("character_story_links", "extract_origin")
