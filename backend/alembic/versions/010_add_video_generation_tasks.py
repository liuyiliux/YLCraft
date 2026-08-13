"""add durable standalone video generation tasks

Revision ID: 010_add_video_generation_tasks
Revises: 009_add_agent_delegations
"""

from alembic import context, op
import sqlalchemy as sa


revision = "010_add_video_generation_tasks"
down_revision = "009_add_agent_delegations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table("video_generation_tasks"):
        return

    op.create_table(
        "video_generation_tasks",
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("asset_id", sa.String(length=64), nullable=True),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("content_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("completed_at", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index("ix_video_generation_tasks_provider", "video_generation_tasks", ["provider"])
    op.create_index("ix_video_generation_tasks_status", "video_generation_tasks", ["status"])
    op.create_index("ix_video_generation_tasks_asset_id", "video_generation_tasks", ["asset_id"])
    op.create_index("ix_video_generation_tasks_project_id", "video_generation_tasks", ["project_id"])
    op.create_index("ix_video_generation_tasks_content_id", "video_generation_tasks", ["content_id"])
    op.create_index("ix_video_generation_tasks_created_at", "video_generation_tasks", ["created_at"])


def downgrade() -> None:
    op.drop_table("video_generation_tasks")
