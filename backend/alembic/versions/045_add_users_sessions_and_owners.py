"""add users, revocable sessions, and nullable resource ownership

Revision ID: 045_add_users_sessions_and_owners
Revises: 044_add_previs_motion_assets

Ownership deliberately remains nullable in this migration.  Existing NULL rows
represent pre-account data and must remain readable until the authorization
rollout can explicitly tighten that policy.
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = "045_add_users_sessions_and_owners"
down_revision = "044_add_previs_motion_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), primary_key=True),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("password_hash", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("display_name", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ux_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_is_active", "users", ["is_active"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), primary_key=True),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(length=64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ux_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_index("ix_user_sessions_is_revoked", "user_sessions", ["is_revoked"])

    for table_name in (
        "creative_projects",
        "asset_nodes",
        "project_task_records",
        "video_generation_tasks",
        "model3d_generation_tasks",
    ):
        op.add_column(
            table_name,
            sa.Column("owner_user_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_owner_user_id", table_name, "users", ["owner_user_id"], ["id"]
        )
        op.create_index(f"ix_{table_name}_owner_user_id", table_name, ["owner_user_id"])


def downgrade() -> None:
    for table_name in (
        "model3d_generation_tasks",
        "video_generation_tasks",
        "project_task_records",
        "asset_nodes",
        "creative_projects",
    ):
        op.drop_index(f"ix_{table_name}_owner_user_id", table_name=table_name)
        op.drop_constraint(f"fk_{table_name}_owner_user_id", table_name, type_="foreignkey")
        op.drop_column(table_name, "owner_user_id")

    op.drop_table("user_sessions")
    op.drop_table("users")
