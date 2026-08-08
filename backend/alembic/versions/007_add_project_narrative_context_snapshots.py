"""add auditable creative context snapshots

Revision ID: 007_add_project_narrative_context_snapshots
Revises: 006_add_project_narrative_runtime
"""

from alembic import op
from alembic import context
import sqlalchemy as sa


revision = "007_add_project_narrative_context_snapshots"
down_revision = "006_add_project_narrative_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table("project_narrative_context_snapshots"):
        return

    op.create_table(
        "project_narrative_context_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("source_content_id", sa.String(length=64), nullable=True),
        sa.Column("narrative_run_id", sa.String(length=64), nullable=True),
        sa.Column("context_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("layers_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("included_sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("excluded_sources_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("budget_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("applied_skill_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("overflow_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"], name="fk_pncs_project"),
        sa.ForeignKeyConstraint(["source_content_id"], ["project_contents.id"], name="fk_pncs_source_content"),
        sa.ForeignKeyConstraint(["narrative_run_id"], ["project_narrative_runs.id"], name="fk_pncs_narrative_run"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pncs_project_chapter_created", "project_narrative_context_snapshots", ["project_id", "chapter_number", "created_at"])
    op.create_index("ix_pncs_project_fingerprint", "project_narrative_context_snapshots", ["project_id", "fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_pncs_project_fingerprint", table_name="project_narrative_context_snapshots")
    op.drop_index("ix_pncs_project_chapter_created", table_name="project_narrative_context_snapshots")
    op.drop_table("project_narrative_context_snapshots")
