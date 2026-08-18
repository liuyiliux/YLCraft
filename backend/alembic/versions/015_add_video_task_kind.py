"""add kind column to video generation tasks

Mirrors 014_add_model3d_task_kind: VideoGenerationTask.kind was added to the
model alongside the 3D ledger's kind split, but the video table never got the
column, so any `SELECT *` over video_generation_tasks failed with
UndefinedColumnError. The video workspace only uses "generation" today, but
keeping the column aligned with the model avoids the same crash on every read.

Revision ID: 015_add_video_task_kind
Revises: 014_add_model3d_task_kind
"""

from alembic import op
import sqlalchemy as sa


revision = "015_add_video_task_kind"
down_revision = "014_add_model3d_task_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "video_generation_tasks",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="generation"),
    )
    op.create_index("ix_video_generation_tasks_kind", "video_generation_tasks", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_video_generation_tasks_kind", table_name="video_generation_tasks")
    op.drop_column("video_generation_tasks", "kind")
