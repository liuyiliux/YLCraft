"""add canvas documents

Revision ID: 002_add_canvas_documents
Revises: 2d4ffb118355
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "002_add_canvas_documents"
down_revision = "2d4ffb118355"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canvas_documents",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("document_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_canvas_documents_title", "canvas_documents", ["title"], unique=False)
    op.create_index("ix_canvas_documents_project_id", "canvas_documents", ["project_id"], unique=False)
    op.create_index("ix_canvas_documents_created_at", "canvas_documents", ["created_at"], unique=False)
    op.create_index("ix_canvas_documents_updated_at", "canvas_documents", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_canvas_documents_updated_at", table_name="canvas_documents")
    op.drop_index("ix_canvas_documents_created_at", table_name="canvas_documents")
    op.drop_index("ix_canvas_documents_project_id", table_name="canvas_documents")
    op.drop_index("ix_canvas_documents_title", table_name="canvas_documents")
    op.drop_table("canvas_documents")
