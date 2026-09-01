"""add world_map_documents for structured world map editing"""

import sqlalchemy as sa
from alembic import op


revision = "035_add_world_map_documents"
down_revision = "034_add_novel_chunk_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_map_documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("snapshot_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("map_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_world_map_documents_project_id",
        "world_map_documents",
        ["project_id"],
    )
    op.create_index(
        "ix_world_map_documents_snapshot_id",
        "world_map_documents",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_world_map_documents_title",
        "world_map_documents",
        ["title"],
    )
    op.create_index(
        "ix_world_map_documents_created_at",
        "world_map_documents",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_world_map_documents_created_at", table_name="world_map_documents")
    op.drop_index("ix_world_map_documents_title", table_name="world_map_documents")
    op.drop_index("ix_world_map_documents_snapshot_id", table_name="world_map_documents")
    op.drop_index("ix_world_map_documents_project_id", table_name="world_map_documents")
    op.drop_table("world_map_documents")
