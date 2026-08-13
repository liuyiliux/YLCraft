"""add durable standalone image-to-3d generation tasks

Revision ID: 011_add_model3d_generation_tasks
Revises: 010_add_video_generation_tasks
"""

from alembic import context, op
import sqlalchemy as sa


revision = "011_add_model3d_generation_tasks"
down_revision = "010_add_video_generation_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing PostgreSQL databases already have this native enum from 001.
    # Fresh databases receive the value directly from the squashed schema.
    if not context.is_offline_mode() and op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE aiprovidertype ADD VALUE IF NOT EXISTS '3d'")
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table("model3d_generation_tasks"):
        return
    op.create_table(
        "model3d_generation_tasks",
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("asset_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("completed_at", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
    )
    for field in ("provider", "status", "asset_id", "created_at"):
        op.create_index(f"ix_model3d_generation_tasks_{field}", "model3d_generation_tasks", [field])


def downgrade() -> None:
    op.drop_table("model3d_generation_tasks")
