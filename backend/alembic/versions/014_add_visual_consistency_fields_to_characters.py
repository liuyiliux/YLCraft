"""add visual consistency fields to characters

Revision ID: 014
Revises: 013
Create Date: 2026-07-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _table_exists("characters"):
        return

    for column_name, column_type, default in [
        ("signature_items", sa.Text(), "[]"),
        ("expressions", sa.Text(), "[]"),
        ("poses", sa.Text(), "[]"),
        ("visual_consistency", sa.Text(), ""),
    ]:
        if not _column_exists("characters", column_name):
            op.add_column(
                "characters",
                sa.Column(column_name, column_type, nullable=False, server_default=default),
            )


def downgrade() -> None:
    if not _table_exists("characters"):
        return

    for column_name in [
        "visual_consistency",
        "poses",
        "expressions",
        "signature_items",
    ]:
        if _column_exists("characters", column_name):
            op.drop_column("characters", column_name)


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
