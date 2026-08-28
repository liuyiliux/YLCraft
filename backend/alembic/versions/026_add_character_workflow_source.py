"""add character workflow source"""
from alembic import op
import sqlalchemy as sa

revision = "026_add_character_workflow_source"
down_revision = "025_add_character_relationships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("workflow_source", sa.String(length=32), nullable=False, server_default="unknown"),
    )
    op.create_index("ix_characters_workflow_source", "characters", ["workflow_source"])
    op.alter_column("characters", "workflow_source", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_characters_workflow_source", table_name="characters")
    op.drop_column("characters", "workflow_source")
