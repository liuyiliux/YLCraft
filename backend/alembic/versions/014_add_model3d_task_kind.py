"""add kind column to model3d generation tasks

Splits the durable 3D task ledger into capability kinds ("generation" for
image/text-to-3D, "rigging" for auto-rigging) so generation and rigging
history can be listed independently.

Revision ID: 014_add_model3d_task_kind
Revises: 013_add_project_state_entries
"""

from alembic import op
import sqlalchemy as sa


revision = "014_add_model3d_task_kind"
down_revision = "013_add_project_state_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model3d_generation_tasks",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="generation"),
    )
    op.create_index("ix_model3d_generation_tasks_kind", "model3d_generation_tasks", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_model3d_generation_tasks_kind", table_name="model3d_generation_tasks")
    op.drop_column("model3d_generation_tasks", "kind")
