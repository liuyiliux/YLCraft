"""add novel source snapshot, text chunk, extraction run and world candidate"""

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = "032_add_novel_source_world"
down_revision = "031_add_character_extraction_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "novel_source_snapshots",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("author", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("source_kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="txt"),
        sa.Column("source_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="unknown"),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("creative_projects.id"), nullable=True),
        sa.Column("source_asset_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("original_file_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("checksum", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("encoding", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="utf-8"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_snapshot_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("chapter_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_chapter_ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexing_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="pending"),
        sa.Column("metadata_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_novel_source_snapshots_title", "novel_source_snapshots", ["title"])
    op.create_index("ix_novel_source_snapshots_source_kind", "novel_source_snapshots", ["source_kind"])
    op.create_index("ix_novel_source_snapshots_source_status", "novel_source_snapshots", ["source_status"])
    op.create_index("ix_novel_source_snapshots_project_id", "novel_source_snapshots", ["project_id"])
    op.create_index("ix_novel_source_snapshots_source_asset_id", "novel_source_snapshots", ["source_asset_id"])
    op.create_index("ix_novel_source_snapshots_checksum", "novel_source_snapshots", ["checksum"])
    op.create_index("ix_novel_source_snapshots_parent_snapshot_id", "novel_source_snapshots", ["parent_snapshot_id"])
    op.create_index("ix_novel_source_snapshots_indexing_status", "novel_source_snapshots", ["indexing_status"])
    op.create_index("ix_novel_source_snapshots_created_at", "novel_source_snapshots", ["created_at"])

    op.create_table(
        "novel_source_chapters",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("snapshot_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("novel_source_snapshots.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("start_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_chapter_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_novel_source_chapters_snapshot_id", "novel_source_chapters", ["snapshot_id"])
    op.create_index("ix_novel_source_chapters_ordinal", "novel_source_chapters", ["ordinal"])
    op.create_index("ix_novel_source_chapters_title", "novel_source_chapters", ["title"])
    op.create_index("ix_novel_source_chapters_source_chapter_id", "novel_source_chapters", ["source_chapter_id"])
    op.create_index("ix_novel_source_chapters_created_at", "novel_source_chapters", ["created_at"])
    op.create_index(
        "ix_novel_source_chapters_snapshot_ordinal",
        "novel_source_chapters",
        ["snapshot_id", "ordinal"],
    )

    op.create_table(
        "novel_text_chunks",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("snapshot_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("novel_source_snapshots.id"), nullable=False),
        sa.Column("chapter_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("novel_source_chapters.id"), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("metadata_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_novel_text_chunks_snapshot_id", "novel_text_chunks", ["snapshot_id"])
    op.create_index("ix_novel_text_chunks_chapter_id", "novel_text_chunks", ["chapter_id"])
    op.create_index("ix_novel_text_chunks_ordinal", "novel_text_chunks", ["ordinal"])
    op.create_index("ix_novel_text_chunks_content_hash", "novel_text_chunks", ["content_hash"])
    op.create_index("ix_novel_text_chunks_created_at", "novel_text_chunks", ["created_at"])
    op.create_index(
        "ix_novel_text_chunks_snapshot_ordinal",
        "novel_text_chunks",
        ["snapshot_id", "ordinal"],
    )

    op.create_table(
        "world_extraction_runs",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("snapshot_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("novel_source_snapshots.id"), nullable=False),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("creative_projects.id"), nullable=True),
        sa.Column("mode", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="full"),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="pending"),
        sa.Column("pipeline_version", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="v1"),
        sa.Column("domains_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
        sa.Column("checkpoint_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("trace_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
        sa.Column("diagnostics_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_world_extraction_runs_snapshot_id", "world_extraction_runs", ["snapshot_id"])
    op.create_index("ix_world_extraction_runs_project_id", "world_extraction_runs", ["project_id"])
    op.create_index("ix_world_extraction_runs_mode", "world_extraction_runs", ["mode"])
    op.create_index("ix_world_extraction_runs_status", "world_extraction_runs", ["status"])
    op.create_index("ix_world_extraction_runs_pipeline_version", "world_extraction_runs", ["pipeline_version"])
    op.create_index("ix_world_extraction_runs_created_at", "world_extraction_runs", ["created_at"])

    op.create_table(
        "world_fact_candidates",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("run_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("world_extraction_runs.id"), nullable=False),
        sa.Column("snapshot_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("novel_source_snapshots.id"), nullable=False),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("creative_projects.id"), nullable=True),
        sa.Column("domain", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("entity_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("normalized_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("fingerprint", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("payload_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("evidence_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="ai_inferred"),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="pending"),
        sa.Column("target_entity_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("target_entity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("review_note", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_world_fact_candidates_run_id", "world_fact_candidates", ["run_id"])
    op.create_index("ix_world_fact_candidates_snapshot_id", "world_fact_candidates", ["snapshot_id"])
    op.create_index("ix_world_fact_candidates_project_id", "world_fact_candidates", ["project_id"])
    op.create_index("ix_world_fact_candidates_domain", "world_fact_candidates", ["domain"])
    op.create_index("ix_world_fact_candidates_entity_name", "world_fact_candidates", ["entity_name"])
    op.create_index("ix_world_fact_candidates_normalized_key", "world_fact_candidates", ["normalized_key"])
    op.create_index("ix_world_fact_candidates_fingerprint", "world_fact_candidates", ["fingerprint"])
    op.create_index("ix_world_fact_candidates_origin", "world_fact_candidates", ["origin"])
    op.create_index("ix_world_fact_candidates_status", "world_fact_candidates", ["status"])
    op.create_index("ix_world_fact_candidates_target_entity_id", "world_fact_candidates", ["target_entity_id"])
    op.create_index("ix_world_fact_candidates_created_at", "world_fact_candidates", ["created_at"])
    op.create_index(
        "ix_world_fact_candidates_snapshot_domain",
        "world_fact_candidates",
        ["snapshot_id", "domain"],
    )
    op.create_index(
        "ix_world_fact_candidates_run_status",
        "world_fact_candidates",
        ["run_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_world_fact_candidates_run_status", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_snapshot_domain", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_created_at", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_target_entity_id", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_status", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_origin", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_fingerprint", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_normalized_key", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_entity_name", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_domain", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_project_id", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_snapshot_id", table_name="world_fact_candidates")
    op.drop_index("ix_world_fact_candidates_run_id", table_name="world_fact_candidates")
    op.drop_table("world_fact_candidates")

    op.drop_index("ix_world_extraction_runs_created_at", table_name="world_extraction_runs")
    op.drop_index("ix_world_extraction_runs_pipeline_version", table_name="world_extraction_runs")
    op.drop_index("ix_world_extraction_runs_status", table_name="world_extraction_runs")
    op.drop_index("ix_world_extraction_runs_mode", table_name="world_extraction_runs")
    op.drop_index("ix_world_extraction_runs_project_id", table_name="world_extraction_runs")
    op.drop_index("ix_world_extraction_runs_snapshot_id", table_name="world_extraction_runs")
    op.drop_table("world_extraction_runs")

    op.drop_index("ix_novel_text_chunks_snapshot_ordinal", table_name="novel_text_chunks")
    op.drop_index("ix_novel_text_chunks_created_at", table_name="novel_text_chunks")
    op.drop_index("ix_novel_text_chunks_content_hash", table_name="novel_text_chunks")
    op.drop_index("ix_novel_text_chunks_ordinal", table_name="novel_text_chunks")
    op.drop_index("ix_novel_text_chunks_chapter_id", table_name="novel_text_chunks")
    op.drop_index("ix_novel_text_chunks_snapshot_id", table_name="novel_text_chunks")
    op.drop_table("novel_text_chunks")

    op.drop_index("ix_novel_source_chapters_snapshot_ordinal", table_name="novel_source_chapters")
    op.drop_index("ix_novel_source_chapters_created_at", table_name="novel_source_chapters")
    op.drop_index("ix_novel_source_chapters_source_chapter_id", table_name="novel_source_chapters")
    op.drop_index("ix_novel_source_chapters_title", table_name="novel_source_chapters")
    op.drop_index("ix_novel_source_chapters_ordinal", table_name="novel_source_chapters")
    op.drop_index("ix_novel_source_chapters_snapshot_id", table_name="novel_source_chapters")
    op.drop_table("novel_source_chapters")

    op.drop_index("ix_novel_source_snapshots_created_at", table_name="novel_source_snapshots")
    op.drop_index("ix_novel_source_snapshots_indexing_status", table_name="novel_source_snapshots")
    op.drop_index("ix_novel_source_snapshots_parent_snapshot_id", table_name="novel_source_snapshots")
    op.drop_index("ix_novel_source_snapshots_checksum", table_name="novel_source_snapshots")
    op.drop_index("ix_novel_source_snapshots_source_asset_id", table_name="novel_source_snapshots")
    op.drop_index("ix_novel_source_snapshots_project_id", table_name="novel_source_snapshots")
    op.drop_index("ix_novel_source_snapshots_source_status", table_name="novel_source_snapshots")
    op.drop_index("ix_novel_source_snapshots_source_kind", table_name="novel_source_snapshots")
    op.drop_index("ix_novel_source_snapshots_title", table_name="novel_source_snapshots")
    op.drop_table("novel_source_snapshots")
