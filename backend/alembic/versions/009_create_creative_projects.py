"""create creative project workflow tables

Revision ID: 009
Revises: 008
Create Date: 2026-06-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _table_exists("creative_projects"):
        op.create_table(
            "creative_projects",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False, server_default=""),
            sa.Column("project_type", sa.String(), nullable=False, server_default="short_drama"),
            sa.Column("source_type", sa.String(), nullable=False, server_default="original_idea"),
            sa.Column("source_ref_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("current_stage", sa.String(), nullable=False, server_default="outline"),
            sa.Column("outline_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("chapter_plan_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_creative_projects_title", "creative_projects", ["title"])
    _create_index_if_missing("ix_creative_projects_project_type", "creative_projects", ["project_type"])
    _create_index_if_missing("ix_creative_projects_source_type", "creative_projects", ["source_type"])
    _create_index_if_missing("ix_creative_projects_status", "creative_projects", ["status"])
    _create_index_if_missing("ix_creative_projects_current_stage", "creative_projects", ["current_stage"])
    _create_index_if_missing("ix_creative_projects_created_at", "creative_projects", ["created_at"])

    if not _table_exists("project_contents"):
        op.create_table(
            "project_contents",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("content_type", sa.String(), nullable=False),
            sa.Column("chapter_number", sa.Integer(), nullable=True),
            sa.Column("episode_number", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(), nullable=False, server_default=""),
            sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("text_content", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_content_id", sa.String(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_project_contents_project_id", "project_contents", ["project_id"])
    _create_index_if_missing("ix_project_contents_content_type", "project_contents", ["content_type"])
    _create_index_if_missing("ix_project_contents_chapter_number", "project_contents", ["chapter_number"])
    _create_index_if_missing("ix_project_contents_episode_number", "project_contents", ["episode_number"])
    _create_index_if_missing("ix_project_contents_title", "project_contents", ["title"])
    _create_index_if_missing("ix_project_contents_source_content_id", "project_contents", ["source_content_id"])
    _create_index_if_missing("ix_project_contents_version", "project_contents", ["version"])
    _create_index_if_missing("ix_project_contents_is_locked", "project_contents", ["is_locked"])
    _create_index_if_missing("ix_project_contents_created_at", "project_contents", ["created_at"])

    if not _table_exists("project_asset_links"):
        op.create_table(
            "project_asset_links",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("asset_id", sa.String(), nullable=False),
            sa.Column("content_id", sa.String(), nullable=True),
            sa.Column("role", sa.String(), nullable=False, server_default="reference"),
            sa.Column("relation", sa.String(), nullable=False, server_default="references"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
            sa.ForeignKeyConstraint(["content_id"], ["project_contents.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_project_asset_links_project_id", "project_asset_links", ["project_id"])
    _create_index_if_missing("ix_project_asset_links_asset_id", "project_asset_links", ["asset_id"])
    _create_index_if_missing("ix_project_asset_links_content_id", "project_asset_links", ["content_id"])
    _create_index_if_missing("ix_project_asset_links_role", "project_asset_links", ["role"])
    _create_index_if_missing("ix_project_asset_links_relation", "project_asset_links", ["relation"])
    _create_index_if_missing("ix_project_asset_links_created_at", "project_asset_links", ["created_at"])

    if not _table_exists("project_generation_logs"):
        op.create_table(
            "project_generation_logs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("content_id", sa.String(), nullable=True),
            sa.Column("stage", sa.String(), nullable=False, server_default=""),
            sa.Column("provider", sa.String(), nullable=False, server_default=""),
            sa.Column("model", sa.String(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False, server_default="success"),
            sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
            sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("raw_response", sa.Text(), nullable=False, server_default=""),
            sa.Column("normalized_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("validation_error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
            sa.ForeignKeyConstraint(["content_id"], ["project_contents.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_project_generation_logs_project_id", "project_generation_logs", ["project_id"])
    _create_index_if_missing("ix_project_generation_logs_content_id", "project_generation_logs", ["content_id"])
    _create_index_if_missing("ix_project_generation_logs_stage", "project_generation_logs", ["stage"])
    _create_index_if_missing("ix_project_generation_logs_provider", "project_generation_logs", ["provider"])
    _create_index_if_missing("ix_project_generation_logs_model", "project_generation_logs", ["model"])
    _create_index_if_missing("ix_project_generation_logs_status", "project_generation_logs", ["status"])
    _create_index_if_missing("ix_project_generation_logs_created_at", "project_generation_logs", ["created_at"])


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(table_name) if _table_exists(table_name) else []
    if any(index.get("name") == index_name for index in indexes):
        return
    op.create_index(index_name, table_name, columns)


def _index_exists(index_name: str, table_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    return any(index.get("name") == index_name for index in sa.inspect(bind).get_indexes(table_name))


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(index_name, table_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_table_if_exists(table_name: str) -> None:
    if _table_exists(table_name):
        op.drop_table(table_name)


def downgrade() -> None:
    _drop_index_if_exists("ix_project_generation_logs_created_at", "project_generation_logs")
    _drop_index_if_exists("ix_project_generation_logs_status", "project_generation_logs")
    _drop_index_if_exists("ix_project_generation_logs_model", "project_generation_logs")
    _drop_index_if_exists("ix_project_generation_logs_provider", "project_generation_logs")
    _drop_index_if_exists("ix_project_generation_logs_stage", "project_generation_logs")
    _drop_index_if_exists("ix_project_generation_logs_content_id", "project_generation_logs")
    _drop_index_if_exists("ix_project_generation_logs_project_id", "project_generation_logs")
    _drop_table_if_exists("project_generation_logs")

    _drop_index_if_exists("ix_project_asset_links_created_at", "project_asset_links")
    _drop_index_if_exists("ix_project_asset_links_relation", "project_asset_links")
    _drop_index_if_exists("ix_project_asset_links_role", "project_asset_links")
    _drop_index_if_exists("ix_project_asset_links_content_id", "project_asset_links")
    _drop_index_if_exists("ix_project_asset_links_asset_id", "project_asset_links")
    _drop_index_if_exists("ix_project_asset_links_project_id", "project_asset_links")
    _drop_table_if_exists("project_asset_links")

    _drop_index_if_exists("ix_project_contents_created_at", "project_contents")
    _drop_index_if_exists("ix_project_contents_is_locked", "project_contents")
    _drop_index_if_exists("ix_project_contents_version", "project_contents")
    _drop_index_if_exists("ix_project_contents_source_content_id", "project_contents")
    _drop_index_if_exists("ix_project_contents_title", "project_contents")
    _drop_index_if_exists("ix_project_contents_episode_number", "project_contents")
    _drop_index_if_exists("ix_project_contents_chapter_number", "project_contents")
    _drop_index_if_exists("ix_project_contents_content_type", "project_contents")
    _drop_index_if_exists("ix_project_contents_project_id", "project_contents")
    _drop_table_if_exists("project_contents")

    _drop_index_if_exists("ix_creative_projects_created_at", "creative_projects")
    _drop_index_if_exists("ix_creative_projects_current_stage", "creative_projects")
    _drop_index_if_exists("ix_creative_projects_status", "creative_projects")
    _drop_index_if_exists("ix_creative_projects_source_type", "creative_projects")
    _drop_index_if_exists("ix_creative_projects_project_type", "creative_projects")
    _drop_index_if_exists("ix_creative_projects_title", "creative_projects")
    _drop_table_if_exists("creative_projects")
