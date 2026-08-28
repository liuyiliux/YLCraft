"""add character relationships"""
from alembic import op
import sqlalchemy as sa

revision = "025_add_character_relationships"
down_revision = "024_add_character_field_sources"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "character_relationships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("related_character_id", sa.String(), nullable=False),
        sa.Column("relation_type", sa.String(), nullable=False, server_default=""),
        sa.Column("relation_note", sa.String(), nullable=False, server_default=""),
        sa.Column("source", sa.String(), nullable=False, server_default=""),
        sa.Column("is_directed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["related_character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_character_relationships_character_id", "character_relationships", ["character_id"])
    op.create_index("ix_character_relationships_related_character_id", "character_relationships", ["related_character_id"])
    op.create_index("ix_character_relationships_relation_type", "character_relationships", ["relation_type"])

def downgrade() -> None:
    op.drop_table("character_relationships")
