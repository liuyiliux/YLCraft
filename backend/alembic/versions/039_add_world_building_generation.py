"""add run kind and world_building_templates for AI progressive world building

渐进式世界构建（openspec/changes/ai-progressive-world-building）的 Phase 0 契约：

- ``world_extraction_runs.kind`` 区分「从原文提取」与「无原文的 AI 生成」（Decision D-3：
  复用同一张运行表与游标/诊断机制，不引入第二套运行表），既有行默认 ``extract``。
- ``world_building_templates`` 承载项目级层次策略与每档提示词（Decision D-1）。
  层次叫什么、有几层由数据决定，不写死在项目代码里；``project_id`` 为空即内置种子模板。
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "039_add_world_building_generation"
down_revision = "038_add_world_domain_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "world_extraction_runs",
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="extract"),
    )
    op.create_index("ix_world_extraction_runs_kind", "world_extraction_runs", ["kind"])

    op.create_table(
        "world_building_templates",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("layers_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("prompts_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_world_building_templates_project", "world_building_templates", ["project_id"])
    op.create_index("ix_world_building_templates_name", "world_building_templates", ["name"])
    op.create_index("ix_world_building_templates_is_default", "world_building_templates", ["is_default"])
    op.create_index("ix_world_building_templates_is_builtin", "world_building_templates", ["is_builtin"])
    op.create_index(
        "ix_world_building_templates_project_default",
        "world_building_templates",
        ["project_id", "is_default"],
    )


def downgrade() -> None:
    op.drop_table("world_building_templates")
    op.drop_index("ix_world_extraction_runs_kind", table_name="world_extraction_runs")
    op.drop_column("world_extraction_runs", "kind")
