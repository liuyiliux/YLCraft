"""add durable agent delegations

Revision ID: 009_add_agent_delegations
Revises: 008_add_project_publish_records
"""

from alembic import context, op
import sqlalchemy as sa


revision = "009_add_agent_delegations"
down_revision = "008_add_project_publish_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = None if context.is_offline_mode() else sa.inspect(bind)
    run_columns = set() if inspector is None else {column["name"] for column in inspector.get_columns("agent_runs")}
    profile_columns = set() if inspector is None else {column["name"] for column in inspector.get_columns("agent_profiles")}

    if "can_delegate" not in profile_columns:
        op.add_column(
            "agent_profiles",
            sa.Column("can_delegate", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_agent_profiles_can_delegate", "agent_profiles", ["can_delegate"])

    if "root_run_id" not in run_columns:
        op.add_column("agent_runs", sa.Column("root_run_id", sa.String(length=64), nullable=True))
        op.create_index("ix_agent_runs_root_run_id", "agent_runs", ["root_run_id"])
    if "run_kind" not in run_columns:
        op.add_column(
            "agent_runs",
            sa.Column("run_kind", sa.String(length=32), nullable=False, server_default="primary"),
        )
        op.create_index("ix_agent_runs_run_kind", "agent_runs", ["run_kind"])
    if "delegation_depth" not in run_columns:
        op.add_column(
            "agent_runs",
            sa.Column("delegation_depth", sa.Integer(), nullable=False, server_default="0"),
        )

    if inspector is not None and inspector.has_table("agent_delegations"):
        return

    op.create_table(
        "agent_delegations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("root_run_id", sa.String(length=64), nullable=False),
        sa.Column("parent_run_id", sa.String(length=64), nullable=False),
        sa.Column("child_run_id", sa.String(length=64), nullable=True),
        sa.Column("parent_step_id", sa.Integer(), nullable=True),
        sa.Column("task_key", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("target_profile_id", sa.String(length=64), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False, server_default=""),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("depends_on_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("execution_mode", sa.String(length=32), nullable=False, server_default="sequential"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["root_run_id"], ["agent_runs.id"], name="fk_agent_delegations_root_run"),
        sa.ForeignKeyConstraint(["parent_run_id"], ["agent_runs.id"], name="fk_agent_delegations_parent_run"),
        sa.ForeignKeyConstraint(["child_run_id"], ["agent_runs.id"], name="fk_agent_delegations_child_run"),
        sa.ForeignKeyConstraint(["parent_step_id"], ["agent_run_steps.id"], name="fk_agent_delegations_parent_step"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_delegations_user_id", "agent_delegations", ["user_id"])
    op.create_index("ix_agent_delegations_root_run_id", "agent_delegations", ["root_run_id"])
    op.create_index("ix_agent_delegations_parent_run_id", "agent_delegations", ["parent_run_id"])
    op.create_index("ix_agent_delegations_child_run_id", "agent_delegations", ["child_run_id"])
    op.create_index("ix_agent_delegations_parent_step_id", "agent_delegations", ["parent_step_id"])
    op.create_index("ix_agent_delegations_task_key", "agent_delegations", ["task_key"])
    op.create_index("ix_agent_delegations_target_profile_id", "agent_delegations", ["target_profile_id"])
    op.create_index("ix_agent_delegations_status", "agent_delegations", ["status"])
    op.create_index("ix_agent_delegations_created_at", "agent_delegations", ["created_at"])


def downgrade() -> None:
    op.drop_table("agent_delegations")
    op.drop_index("ix_agent_runs_run_kind", table_name="agent_runs")
    op.drop_column("agent_runs", "delegation_depth")
    op.drop_column("agent_runs", "run_kind")
    op.drop_index("ix_agent_runs_root_run_id", table_name="agent_runs")
    op.drop_column("agent_runs", "root_run_id")
    op.drop_index("ix_agent_profiles_can_delegate", table_name="agent_profiles")
    op.drop_column("agent_profiles", "can_delegate")
