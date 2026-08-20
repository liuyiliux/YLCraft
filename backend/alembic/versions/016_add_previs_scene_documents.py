"""add previs scene documents

Revision ID: 016_add_previs_scene_documents
Revises: 015_add_video_task_kind
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "016_add_previs_scene_documents"
down_revision = "015_add_video_task_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "previs_scene_documents",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("storyboard_content_id", sa.String(length=80), nullable=False),
        sa.Column("panel_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False, server_default="3D 预演"),
        sa.Column("scene_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
        sa.ForeignKeyConstraint(["storyboard_content_id"], ["project_contents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_previs_scene_documents_project_id", "previs_scene_documents", ["project_id"], unique=False)
    op.create_index("ix_previs_scene_documents_storyboard_content_id", "previs_scene_documents", ["storyboard_content_id"], unique=False)
    op.create_index("ix_previs_scene_documents_panel_number", "previs_scene_documents", ["panel_number"], unique=False)
    op.create_index("ix_previs_scene_documents_revision", "previs_scene_documents", ["revision"], unique=False)
    op.create_index("ix_previs_scene_documents_created_at", "previs_scene_documents", ["created_at"], unique=False)
    op.create_index("ix_previs_scene_documents_updated_at", "previs_scene_documents", ["updated_at"], unique=False)
    op.create_index(
        "ix_previs_scene_documents_storyboard_panel",
        "previs_scene_documents",
        ["project_id", "storyboard_content_id", "panel_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_previs_scene_documents_storyboard_panel", table_name="previs_scene_documents")
    op.drop_index("ix_previs_scene_documents_updated_at", table_name="previs_scene_documents")
    op.drop_index("ix_previs_scene_documents_created_at", table_name="previs_scene_documents")
    op.drop_index("ix_previs_scene_documents_revision", table_name="previs_scene_documents")
    op.drop_index("ix_previs_scene_documents_panel_number", table_name="previs_scene_documents")
    op.drop_index("ix_previs_scene_documents_storyboard_content_id", table_name="previs_scene_documents")
    op.drop_index("ix_previs_scene_documents_project_id", table_name="previs_scene_documents")
    op.drop_table("previs_scene_documents")
