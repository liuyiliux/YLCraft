"""add ignored_suggestions_json to world_domain_definitions

结构建议（AI 提出的字段/模块）必须经用户确认才成为 schema（梯子原则 I2）。
确认后的字段写进 extra_attributes；被忽略的字段需要记住，否则每次生成后都会
重复提示同一个建议。本迁移为此新增 ignored_suggestions_json。
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "041_add_ignored_domain_suggestions"
down_revision = "040_allow_snapshotless_generation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "world_domain_definitions",
        sa.Column(
            "ignored_suggestions_json",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("world_domain_definitions", "ignored_suggestions_json")
