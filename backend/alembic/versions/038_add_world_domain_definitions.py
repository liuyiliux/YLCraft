"""add world_domain_definitions for project-level domain/attribute extension

世界在变，模块不能写死：本表让每个项目在内置模块（contracts.DOMAIN_SPECS）之上
覆盖展示名/提示词、追加属性字段、禁用不需要的模块，或新增自定义模块（如赛博朋克的
「义体改造」、修仙的「灵脉品级」）。自定义模块的实体仍写入 world_entities，
entity_type 取本表值，因此新增模块不需要新表。
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "038_add_world_domain_definitions"
down_revision = "037_add_world_entities_and_relations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_domain_definitions",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("domain_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("entity_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("extra_attributes_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("prompt_hint", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_world_domain_definitions_project_key", "world_domain_definitions", ["project_id", "domain_key"], unique=True)
    op.create_index("ix_world_domain_definitions_project", "world_domain_definitions", ["project_id"])
    op.create_index("ix_world_domain_definitions_domain_key", "world_domain_definitions", ["domain_key"])
    op.create_index("ix_world_domain_definitions_source", "world_domain_definitions", ["source"])
    op.create_index("ix_world_domain_definitions_is_enabled", "world_domain_definitions", ["is_enabled"])
    op.create_index(
        "ix_world_domain_definitions_project_source",
        "world_domain_definitions",
        ["project_id", "source"],
    )


def downgrade() -> None:
    op.drop_table("world_domain_definitions")
