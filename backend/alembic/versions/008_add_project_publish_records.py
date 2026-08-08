"""add project publish records

Revision ID: 008_add_project_publish_records
Revises: 007_add_project_narrative_context_snapshots
"""

from alembic import op
from alembic import context
import sqlalchemy as sa


revision = "008_add_project_publish_records"
down_revision = "007_add_project_narrative_context_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table("project_publish_records"):
        return

    op.create_table(
        "project_publish_records",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("content_id", sa.String(length=64), nullable=True),
        sa.Column("conn_id", sa.String(), nullable=False, server_default=""),
        sa.Column("book_id", sa.String(), nullable=False, server_default=""),
        sa.Column("item_id", sa.String(), nullable=False, server_default=""),
        sa.Column("volume_id", sa.String(), nullable=False, server_default=""),
        sa.Column("volume_name", sa.String(), nullable=False, server_default=""),
        sa.Column("chapter_number", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(), nullable=False, server_default="draft"),
        sa.Column("remote_version", sa.Integer(), nullable=True),
        sa.Column("post_url", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
        sa.ForeignKeyConstraint(["content_id"], ["project_contents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_publish_records_project_id", "project_publish_records", ["project_id"])
    op.create_index("ix_project_publish_records_content_id", "project_publish_records", ["content_id"])
    op.create_index("ix_project_publish_records_book_id", "project_publish_records", ["book_id"])
    op.create_index("ix_project_publish_records_item_id", "project_publish_records", ["item_id"])
    op.create_index("ix_project_publish_records_chapter_number", "project_publish_records", ["chapter_number"])
    op.create_index("ix_project_publish_records_status", "project_publish_records", ["status"])
    op.create_index("ix_project_publish_records_created_at", "project_publish_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_project_publish_records_created_at", table_name="project_publish_records")
    op.drop_index("ix_project_publish_records_status", table_name="project_publish_records")
    op.drop_index("ix_project_publish_records_chapter_number", table_name="project_publish_records")
    op.drop_index("ix_project_publish_records_item_id", table_name="project_publish_records")
    op.drop_index("ix_project_publish_records_book_id", table_name="project_publish_records")
    op.drop_index("ix_project_publish_records_content_id", table_name="project_publish_records")
    op.drop_index("ix_project_publish_records_project_id", table_name="project_publish_records")
    op.drop_table("project_publish_records")
