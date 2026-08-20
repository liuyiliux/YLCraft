"""add platform event logs

Revision ID: 017_add_platform_event_logs
Revises: 016_add_previs_scene_documents
"""

from alembic import op
import sqlalchemy as sa


revision = "017_add_platform_event_logs"
down_revision = "016_add_previs_scene_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_event_logs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("scene", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("task_type", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("provider", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("response_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("retry_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("retry_of", sa.String(length=64), nullable=True),
        sa.Column("retried_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_event_logs_scene", "platform_event_logs", ["scene"], unique=False)
    op.create_index("ix_platform_event_logs_task_type", "platform_event_logs", ["task_type"], unique=False)
    op.create_index("ix_platform_event_logs_task_id", "platform_event_logs", ["task_id"], unique=False)
    op.create_index("ix_platform_event_logs_level", "platform_event_logs", ["level"], unique=False)
    op.create_index("ix_platform_event_logs_status", "platform_event_logs", ["status"], unique=False)
    op.create_index("ix_platform_event_logs_project_id", "platform_event_logs", ["project_id"], unique=False)
    op.create_index("ix_platform_event_logs_retry_of", "platform_event_logs", ["retry_of"], unique=False)
    op.create_index("ix_platform_event_logs_retried_by", "platform_event_logs", ["retried_by"], unique=False)
    op.create_index("ix_platform_event_logs_created_at", "platform_event_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_platform_event_logs_created_at", table_name="platform_event_logs")
    op.drop_index("ix_platform_event_logs_retried_by", table_name="platform_event_logs")
    op.drop_index("ix_platform_event_logs_retry_of", table_name="platform_event_logs")
    op.drop_index("ix_platform_event_logs_project_id", table_name="platform_event_logs")
    op.drop_index("ix_platform_event_logs_status", table_name="platform_event_logs")
    op.drop_index("ix_platform_event_logs_level", table_name="platform_event_logs")
    op.drop_index("ix_platform_event_logs_task_id", table_name="platform_event_logs")
    op.drop_index("ix_platform_event_logs_task_type", table_name="platform_event_logs")
    op.drop_index("ix_platform_event_logs_scene", table_name="platform_event_logs")
    op.drop_table("platform_event_logs")
