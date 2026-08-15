"""add project state entries

Revision ID: 013_add_project_state_entries
Revises: 012_add_team_composition_fields
"""

from alembic import context, op
import sqlalchemy as sa


revision = "013_add_project_state_entries"
down_revision = "012_add_team_composition_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = None if context.is_offline_mode() else sa.inspect(bind)
    if inspector is not None and inspector.has_table("project_state_entries"):
        return

    op.create_table(
        "project_state_entries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("op", sa.String(length=16), nullable=False, server_default="set"),
        sa.Column("value_json", sa.Text(), nullable=False, server_default="null"),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("source_content_id", sa.String(length=64), nullable=True),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"], name="fk_pse_project"),
        sa.ForeignKeyConstraint(["source_content_id"], ["project_contents.id"], name="fk_pse_source_content"),
    )
    for column in ("project_id", "scope", "key", "op", "chapter_number", "source_content_id", "fingerprint", "created_at"):
        op.create_index(f"ix_project_state_entries_{column}", "project_state_entries", [column])
    op.create_index("ix_pse_project_scope_chapter", "project_state_entries", ["project_id", "scope", "chapter_number"])
    op.create_index("ix_pse_project_fingerprint", "project_state_entries", ["project_id", "fingerprint"])


def downgrade() -> None:
    op.drop_table("project_state_entries")
