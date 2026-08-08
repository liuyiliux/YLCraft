"""add project narrative runtime records

Revision ID: 006_add_project_narrative_runtime
Revises: 005_add_project_continuity_candidates
"""

from alembic import op
from alembic import context
import sqlalchemy as sa


revision = "006_add_project_narrative_runtime"
down_revision = "005_add_project_continuity_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = [
        "project_narrative_runs",
        "project_narrative_snapshots",
        "project_story_events",
        "project_foreshadowing",
        "project_style_measurements",
    ]
    if not context.is_offline_mode():
        existing = [sa.inspect(op.get_bind()).has_table(table) for table in tables]
        if any(existing):
            if not all(existing):
                raise RuntimeError("project narrative runtime schema is partially present; reconcile it before upgrading")
            return

    op.create_table(
        "project_narrative_runs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("target_chapters_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("input_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("trace_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("context_snapshot_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("current_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"], name="fk_pnr_project"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pnr_project_status", "project_narrative_runs", ["project_id", "status"])
    op.create_index("ix_pnr_project_created", "project_narrative_runs", ["project_id", "created_at"])

    op.create_table(
        "project_narrative_snapshots",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_content_id", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("character_state_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("timeline_delta_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("location_delta_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("open_questions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("diagnostics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("context_fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"], name="fk_pns_project"),
        sa.ForeignKeyConstraint(["source_content_id"], ["project_contents.id"], name="fk_pns_source_content"),
        sa.ForeignKeyConstraint(["run_id"], ["project_narrative_runs.id"], name="fk_pns_run"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pns_project_chapter", "project_narrative_snapshots", ["project_id", "chapter_number"])
    op.create_index("ix_pns_project_status", "project_narrative_snapshots", ["project_id", "status"])
    op.create_index("ix_pns_source_version", "project_narrative_snapshots", ["source_content_id", "source_version"])
    op.create_index(
        "ux_pns_source_pipeline",
        "project_narrative_snapshots",
        ["source_content_id", "source_fingerprint", "pipeline_version"],
        unique=True,
    )

    op.create_table(
        "project_story_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("source_content_id", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("event_type", sa.String(length=64), nullable=False, server_default="event"),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("participants_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("location", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("timeline_order", sa.Integer(), nullable=True),
        sa.Column("evidence_anchor_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"], name="fk_pse_project"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["project_narrative_snapshots.id"], name="fk_pse_snapshot"),
        sa.ForeignKeyConstraint(["source_content_id"], ["project_contents.id"], name="fk_pse_source_content"),
        sa.ForeignKeyConstraint(["run_id"], ["project_narrative_runs.id"], name="fk_pse_run"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pse_project_chapter", "project_story_events", ["project_id", "chapter_number"])
    op.create_index("ix_pse_project_status", "project_story_events", ["project_id", "status"])
    op.create_index("ix_pse_project_type", "project_story_events", ["project_id", "event_type"])

    op.create_table(
        "project_foreshadowing",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("source_content_id", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default="clue"),
        sa.Column("statement", sa.Text(), nullable=False, server_default=""),
        sa.Column("planted_chapter", sa.Integer(), nullable=False),
        sa.Column("expected_window_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("evidence_anchor_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("resolution_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"], name="fk_pf_project"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["project_narrative_snapshots.id"], name="fk_pf_snapshot"),
        sa.ForeignKeyConstraint(["source_content_id"], ["project_contents.id"], name="fk_pf_source_content"),
        sa.ForeignKeyConstraint(["run_id"], ["project_narrative_runs.id"], name="fk_pf_run"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pf_project_status", "project_foreshadowing", ["project_id", "status"])
    op.create_index("ix_pf_project_chapter", "project_foreshadowing", ["project_id", "chapter_number"])
    op.create_index("ix_pf_project_kind", "project_foreshadowing", ["project_id", "kind"])

    op.create_table(
        "project_style_measurements",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_content_id", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("measurement_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("style_fingerprint", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"], name="fk_psm_project"),
        sa.ForeignKeyConstraint(["source_content_id"], ["project_contents.id"], name="fk_psm_source_content"),
        sa.ForeignKeyConstraint(["run_id"], ["project_narrative_runs.id"], name="fk_psm_run"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_psm_project_chapter", "project_style_measurements", ["project_id", "chapter_number"])
    op.create_index("ix_psm_project_status", "project_style_measurements", ["project_id", "status"])
    op.create_index("ix_psm_source_version", "project_style_measurements", ["source_content_id", "source_version"])


def downgrade() -> None:
    op.drop_index("ix_psm_source_version", table_name="project_style_measurements")
    op.drop_index("ix_psm_project_status", table_name="project_style_measurements")
    op.drop_index("ix_psm_project_chapter", table_name="project_style_measurements")
    op.drop_table("project_style_measurements")
    op.drop_index("ix_pf_project_kind", table_name="project_foreshadowing")
    op.drop_index("ix_pf_project_chapter", table_name="project_foreshadowing")
    op.drop_index("ix_pf_project_status", table_name="project_foreshadowing")
    op.drop_table("project_foreshadowing")
    op.drop_index("ix_pse_project_type", table_name="project_story_events")
    op.drop_index("ix_pse_project_status", table_name="project_story_events")
    op.drop_index("ix_pse_project_chapter", table_name="project_story_events")
    op.drop_table("project_story_events")
    op.drop_index("ux_pns_source_pipeline", table_name="project_narrative_snapshots")
    op.drop_index("ix_pns_source_version", table_name="project_narrative_snapshots")
    op.drop_index("ix_pns_project_status", table_name="project_narrative_snapshots")
    op.drop_index("ix_pns_project_chapter", table_name="project_narrative_snapshots")
    op.drop_table("project_narrative_snapshots")
    op.drop_index("ix_pnr_project_created", table_name="project_narrative_runs")
    op.drop_index("ix_pnr_project_status", table_name="project_narrative_runs")
    op.drop_table("project_narrative_runs")
