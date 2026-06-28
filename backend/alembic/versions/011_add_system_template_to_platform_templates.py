"""add system template to platform templates

Revision ID: 011
Revises: 010
Create Date: 2026-06-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _table_exists("platform_templates"):
        return

    if not _column_exists("platform_templates", "system_template"):
        op.add_column(
            "platform_templates",
            sa.Column(
                "system_template",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
        )

    op.execute(
        "UPDATE platform_templates "
        "SET system_template = '' "
        "WHERE system_template IS NULL"
    )


def downgrade() -> None:
    if _table_exists("platform_templates") and _column_exists("platform_templates", "system_template"):
        op.drop_column("platform_templates", "system_template")


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    return any(column.get("name") == column_name for column in sa.inspect(bind).get_columns(table_name))
