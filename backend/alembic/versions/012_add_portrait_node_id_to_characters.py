"""add portrait_node_id to characters

Revision ID: 012
Revises: 011
Create Date: 2026-06-28

为 characters 表新增 portrait_node_id 字段，关联资产中枢 asset_nodes.id。
向后兼容：可空 + 默认 NULL，已有数据不受影响。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _table_exists("characters"):
        return

    if not _column_exists("characters", "portrait_node_id"):
        op.add_column(
            "characters",
            sa.Column(
                "portrait_node_id",
                sa.String(),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_characters_portrait_node_id",
            "characters",
            ["portrait_node_id"],
        )


def downgrade() -> None:
    if _table_exists("characters") and _column_exists("characters", "portrait_node_id"):
        op.drop_index("ix_characters_portrait_node_id", table_name="characters")
        op.drop_column("characters", "portrait_node_id")


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
