"""add project scoped character extraction evidence"""

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "031_add_character_extraction_evidence"
down_revision = "030_add_character_voice_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "character_story_links",
        sa.Column("aliases_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "character_story_links",
        sa.Column("evidence_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "character_story_links",
        sa.Column("extraction_notes", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("character_story_links", "extraction_notes")
    op.drop_column("character_story_links", "evidence_json")
    op.drop_column("character_story_links", "aliases_json")
