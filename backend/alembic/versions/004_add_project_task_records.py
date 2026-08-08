"""add durable project task records"""

from alembic import op
from alembic import context
import sqlalchemy as sa


revision = "004_add_project_task_records"
down_revision = "003_add_image_prompt_reference_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table("project_task_records"):
        return

    op.create_table(
        "project_task_records",
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=True),
        sa.Column("completed_at", sa.Float(), nullable=True),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index("ix_project_task_records_task_type", "project_task_records", ["task_type"])
    op.create_index("ix_project_task_records_status", "project_task_records", ["status"])
    op.create_index("ix_project_task_records_created_at", "project_task_records", ["created_at"])
    op.create_index("ix_project_task_records_updated_at", "project_task_records", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_project_task_records_updated_at", table_name="project_task_records")
    op.drop_index("ix_project_task_records_created_at", table_name="project_task_records")
    op.drop_index("ix_project_task_records_status", table_name="project_task_records")
    op.drop_index("ix_project_task_records_task_type", table_name="project_task_records")
    op.drop_table("project_task_records")
