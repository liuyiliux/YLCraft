"""add image prompt reference library

Revision ID: 003_add_image_prompt_reference_library
Revises: 002_add_canvas_documents
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "003_add_image_prompt_reference_library"
down_revision = "002_add_canvas_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_prompt_sources",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("repo_url", sa.String(), nullable=False, server_default=""),
        sa.Column("raw_base_url", sa.String(), nullable=False, server_default=""),
        sa.Column("raw_path", sa.String(), nullable=False, server_default="README.md"),
        sa.Column("parser", sa.String(), nullable=False, server_default="markdown_sections"),
        sa.Column("category", sa.String(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_status", sa.String(), nullable=False, server_default="idle"),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(), nullable=False, server_default=""),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_image_prompt_sources_name", "image_prompt_sources", ["name"], unique=False)
    op.create_index("ix_image_prompt_sources_parser", "image_prompt_sources", ["parser"], unique=False)
    op.create_index("ix_image_prompt_sources_category", "image_prompt_sources", ["category"], unique=False)
    op.create_index("ix_image_prompt_sources_enabled", "image_prompt_sources", ["enabled"], unique=False)
    op.create_index("ix_image_prompt_sources_sync_status", "image_prompt_sources", ["sync_status"], unique=False)
    op.create_index("ix_image_prompt_sources_last_synced_at", "image_prompt_sources", ["last_synced_at"], unique=False)
    op.create_index("ix_image_prompt_sources_created_at", "image_prompt_sources", ["created_at"], unique=False)
    op.create_index("ix_image_prompt_sources_updated_at", "image_prompt_sources", ["updated_at"], unique=False)

    op.create_table(
        "image_prompt_references",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("negative_prompt", sa.String(), nullable=False, server_default=""),
        sa.Column("cover_url", sa.String(), nullable=False, server_default=""),
        sa.Column("preview_markdown", sa.String(), nullable=False, server_default=""),
        sa.Column("tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("category", sa.String(), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(), nullable=False, server_default=""),
        sa.Column("model_hint", sa.String(), nullable=False, server_default=""),
        sa.Column("needs_reference_image", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("language", sa.String(), nullable=False, server_default=""),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["image_prompt_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_image_prompt_references_source_external"),
    )
    op.create_index("ix_image_prompt_references_source_id", "image_prompt_references", ["source_id"], unique=False)
    op.create_index("ix_image_prompt_references_external_id", "image_prompt_references", ["external_id"], unique=False)
    op.create_index("ix_image_prompt_references_title", "image_prompt_references", ["title"], unique=False)
    op.create_index("ix_image_prompt_references_category", "image_prompt_references", ["category"], unique=False)
    op.create_index("ix_image_prompt_references_needs_reference_image", "image_prompt_references", ["needs_reference_image"], unique=False)
    op.create_index("ix_image_prompt_references_language", "image_prompt_references", ["language"], unique=False)
    op.create_index("ix_image_prompt_references_created_at", "image_prompt_references", ["created_at"], unique=False)
    op.create_index("ix_image_prompt_references_updated_at", "image_prompt_references", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_image_prompt_references_updated_at", table_name="image_prompt_references")
    op.drop_index("ix_image_prompt_references_created_at", table_name="image_prompt_references")
    op.drop_index("ix_image_prompt_references_language", table_name="image_prompt_references")
    op.drop_index("ix_image_prompt_references_needs_reference_image", table_name="image_prompt_references")
    op.drop_index("ix_image_prompt_references_category", table_name="image_prompt_references")
    op.drop_index("ix_image_prompt_references_title", table_name="image_prompt_references")
    op.drop_index("ix_image_prompt_references_external_id", table_name="image_prompt_references")
    op.drop_index("ix_image_prompt_references_source_id", table_name="image_prompt_references")
    op.drop_table("image_prompt_references")

    op.drop_index("ix_image_prompt_sources_updated_at", table_name="image_prompt_sources")
    op.drop_index("ix_image_prompt_sources_created_at", table_name="image_prompt_sources")
    op.drop_index("ix_image_prompt_sources_last_synced_at", table_name="image_prompt_sources")
    op.drop_index("ix_image_prompt_sources_sync_status", table_name="image_prompt_sources")
    op.drop_index("ix_image_prompt_sources_enabled", table_name="image_prompt_sources")
    op.drop_index("ix_image_prompt_sources_category", table_name="image_prompt_sources")
    op.drop_index("ix_image_prompt_sources_parser", table_name="image_prompt_sources")
    op.drop_index("ix_image_prompt_sources_name", table_name="image_prompt_sources")
    op.drop_table("image_prompt_sources")
