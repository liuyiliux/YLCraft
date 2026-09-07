"""add writing style profiles and project bindings"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "043_add_writing_style_profiles"
down_revision = "042_add_world_map_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "writing_style_profiles",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("owner_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="default"),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user_defined"),
        sa.Column("source_snapshot_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_sample_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("profile_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("prompt_contract_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("provenance_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("checksum", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for name, columns in (
        ("ix_writing_style_profiles_owner_id", ["owner_id"]),
        ("ix_writing_style_profiles_name", ["name"]),
        ("ix_writing_style_profiles_source_snapshot_id", ["source_snapshot_id"]),
        ("ix_writing_style_profiles_source_sample_hash", ["source_sample_hash"]),
        ("ix_writing_style_profiles_status", ["status"]),
        ("ix_writing_style_profiles_checksum", ["checksum"]),
        ("ix_writing_style_profiles_owner_status", ["owner_id", "status"]),
        ("ix_writing_style_profiles_source", ["source_snapshot_id", "source_sample_hash"]),
    ):
        op.create_index(name, "writing_style_profiles", columns)

    op.create_table(
        "project_writing_style_links",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("creative_projects.id"), nullable=False),
        sa.Column("style_profile_id", sqlmodel.sql.sqltypes.AutoString(), sa.ForeignKey("writing_style_profiles.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("intensity", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="balanced"),
        sa.Column("stage_scope_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
        sa.Column("dimension_overrides_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_project_writing_style_links_project_id", "project_writing_style_links", ["project_id"])
    op.create_index("ix_project_writing_style_links_style_profile_id", "project_writing_style_links", ["style_profile_id"])
    op.create_index("ix_project_writing_style_links_enabled", "project_writing_style_links", ["enabled"])
    op.create_index("ix_project_writing_style_links_priority", "project_writing_style_links", ["priority"])
    op.create_index("ix_project_writing_style_link_runtime", "project_writing_style_links", ["project_id", "enabled", "priority"])
    op.create_index("ux_project_writing_style_link", "project_writing_style_links", ["project_id", "style_profile_id"], unique=True)


def downgrade() -> None:
    op.drop_table("project_writing_style_links")
    op.drop_table("writing_style_profiles")
