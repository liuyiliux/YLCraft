"""add project continuity candidates (continuity fact workflow)"""

from alembic import op
from alembic import context
import sqlalchemy as sa


revision = "005_add_project_continuity_candidates"
down_revision = "004_add_project_task_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table("project_continuity_candidates"):
        return

    op.create_table(
        "project_continuity_candidates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_content_id", sa.String(length=64), nullable=True),
        sa.Column("source_generation_log_id", sa.String(length=64), nullable=True),
        sa.Column("source_kind", sa.String(length=64), nullable=False, server_default="prose_review"),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("entity_type", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("entity_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("claim", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_anchor_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("suggested_action", sa.String(length=32), nullable=False, server_default="create_fact"),
        sa.Column("target_fact_type", sa.String(length=32), nullable=False, server_default="world_asset"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("resolved_fact_id", sa.String(length=64), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolved_at", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["creative_projects.id"], name="fk_pcc_project"
        ),
        sa.ForeignKeyConstraint(
            ["source_content_id"], ["project_contents.id"], name="fk_pcc_source_content"
        ),
        sa.ForeignKeyConstraint(
            ["source_generation_log_id"],
            ["project_generation_logs.id"],
            name="fk_pcc_source_log",
        ),
    )
    op.create_index(
        "ix_pcc_project_status", "project_continuity_candidates", ["project_id", "status"]
    )
    op.create_index(
        "ix_pcc_project_source",
        "project_continuity_candidates",
        ["project_id", "source_content_id"],
    )
    op.create_index(
        "ix_pcc_dedupe",
        "project_continuity_candidates",
        ["project_id", "source_kind", "source_fingerprint"],
    )
    op.create_index(
        "ix_pcc_severity", "project_continuity_candidates", ["project_id", "severity"]
    )
    op.create_index(
        "ix_pcc_created_at", "project_continuity_candidates", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_pcc_created_at", table_name="project_continuity_candidates")
    op.drop_index("ix_pcc_severity", table_name="project_continuity_candidates")
    op.drop_index("ix_pcc_dedupe", table_name="project_continuity_candidates")
    op.drop_index("ix_pcc_project_source", table_name="project_continuity_candidates")
    op.drop_index("ix_pcc_project_status", table_name="project_continuity_candidates")
    op.drop_table("project_continuity_candidates")
