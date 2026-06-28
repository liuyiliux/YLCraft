"""add scene and ref_id to project_generation_logs

Revision ID: 013
Revises: 012
Create Date: 2026-06-28

为 project_generation_logs 表新增 scene + ref_id 字段，支持多场景日志：
- scene: 场景标记（默认 "creative_project"，角色立绘为 "character_portrait"）
- ref_id: 通用关联 ID（当 scene != creative_project 时使用，如 character_id）

同时将 project_id / content_id 改为可空（兼容非项目场景）。
向后兼容：所有新字段可空 + 默认值。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _table_exists("project_generation_logs"):
        return

    # 1. 新增 scene 字段（默认 creative_project，向后兼容）
    if not _column_exists("project_generation_logs", "scene"):
        op.add_column(
            "project_generation_logs",
            sa.Column(
                "scene",
                sa.String(),
                nullable=False,
                server_default="creative_project",
            ),
        )
        op.create_index(
            "ix_project_generation_logs_scene",
            "project_generation_logs",
            ["scene"],
        )

    # 2. 新增 ref_id 字段（可空）
    if not _column_exists("project_generation_logs", "ref_id"):
        op.add_column(
            "project_generation_logs",
            sa.Column(
                "ref_id",
                sa.String(),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_project_generation_logs_ref_id",
            "project_generation_logs",
            ["ref_id"],
        )

    # 3. 将 project_id / content_id 改为可空（兼容非项目场景）
    # 使用 ALTER COLUMN ... DROP NOT NULL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE project_generation_logs "
            "ALTER COLUMN project_id DROP NOT NULL"
        )
        op.execute(
            "ALTER TABLE project_generation_logs "
            "ALTER COLUMN content_id DROP NOT NULL"
        )


def downgrade() -> None:
    if not _table_exists("project_generation_logs"):
        return

    # 恢复 NOT NULL 约束（仅在数据无 NULL 时成功）
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE project_generation_logs "
            "ALTER COLUMN project_id SET NOT NULL"
        )
        op.execute(
            "ALTER TABLE project_generation_logs "
            "ALTER COLUMN content_id SET NOT NULL"
        )

    if _column_exists("project_generation_logs", "ref_id"):
        op.drop_index(
            "ix_project_generation_logs_ref_id",
            table_name="project_generation_logs",
        )
        op.drop_column("project_generation_logs", "ref_id")

    if _column_exists("project_generation_logs", "scene"):
        op.drop_index(
            "ix_project_generation_logs_scene",
            table_name="project_generation_logs",
        )
        op.drop_column("project_generation_logs", "scene")


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    return any(
        column.get("name") == column_name
        for column in sa.inspect(bind).get_columns(table_name)
    )
