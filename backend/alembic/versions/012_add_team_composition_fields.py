"""add team composition fields to agent delegations

Revision ID: 012_add_team_composition_fields
Revises: 011_add_model3d_generation_tasks
"""

from alembic import context, op
import sqlalchemy as sa


revision = "012_add_team_composition_fields"
down_revision = "011_add_model3d_generation_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = None if context.is_offline_mode() else sa.inspect(bind)
    columns = (
        set()
        if inspector is None
        else {column["name"] for column in inspector.get_columns("agent_delegations")}
    )

    if "spawn_mode" not in columns:
        op.add_column(
            "agent_delegations",
            sa.Column("spawn_mode", sa.String(length=16), nullable=False, server_default="spawn"),
        )
    if "team_template_id" not in columns:
        op.add_column(
            "agent_delegations",
            sa.Column("team_template_id", sa.String(length=120), nullable=False, server_default=""),
        )
    if "role_id" not in columns:
        op.add_column(
            "agent_delegations",
            sa.Column("role_id", sa.String(length=64), nullable=False, server_default=""),
        )
    if "continuation_of" not in columns:
        op.add_column(
            "agent_delegations",
            sa.Column("continuation_of", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("agent_delegations", "continuation_of")
    op.drop_column("agent_delegations", "role_id")
    op.drop_column("agent_delegations", "team_template_id")
    op.drop_column("agent_delegations", "spawn_mode")
