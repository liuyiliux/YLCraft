"""extend platform templates for prompt template types

Revision ID: 010
Revises: 009
Create Date: 2026-06-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _table_exists("platform_templates"):
        return

    if not _column_exists("platform_templates", "template_scope"):
        op.add_column(
            "platform_templates",
            sa.Column(
                "template_scope",
                sa.String(length=40),
                nullable=False,
                server_default="image_platform",
            ),
        )
    if not _column_exists("platform_templates", "template_stage"):
        op.add_column(
            "platform_templates",
            sa.Column(
                "template_stage",
                sa.String(length=40),
                nullable=False,
                server_default="platform",
            ),
        )
    if not _column_exists("platform_templates", "description"):
        op.add_column("platform_templates", sa.Column("description", sa.Text(), nullable=True))
    if not _column_exists("platform_templates", "variables"):
        op.add_column(
            "platform_templates",
            sa.Column(
                "variables",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )

    op.execute(
        "UPDATE platform_templates "
        "SET template_scope = 'image_platform' "
        "WHERE template_scope IS NULL OR template_scope = ''"
    )
    op.execute(
        "UPDATE platform_templates "
        "SET template_stage = 'platform' "
        "WHERE template_stage IS NULL OR template_stage = ''"
    )
    op.execute(
        "UPDATE platform_templates "
        "SET variables = '{}'::jsonb "
        "WHERE variables IS NULL"
    )

    _create_index_if_missing("ix_platform_templates_template_scope", "platform_templates", ["template_scope"])
    _create_index_if_missing("ix_platform_templates_template_stage", "platform_templates", ["template_stage"])


def downgrade() -> None:
    if not _table_exists("platform_templates"):
        return
    _drop_index_if_exists("ix_platform_templates_template_stage", "platform_templates")
    _drop_index_if_exists("ix_platform_templates_template_scope", "platform_templates")
    _drop_column_if_exists("platform_templates", "variables")
    _drop_column_if_exists("platform_templates", "description")
    _drop_column_if_exists("platform_templates", "template_stage")
    _drop_column_if_exists("platform_templates", "template_scope")


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    return any(column.get("name") == column_name for column in sa.inspect(bind).get_columns(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(table_name) if _table_exists(table_name) else []
    if any(index.get("name") == index_name for index in indexes):
        return
    op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if not _table_exists(table_name):
        return
    bind = op.get_bind()
    if any(index.get("name") == index_name for index in sa.inspect(bind).get_indexes(table_name)):
        op.drop_index(index_name, table_name=table_name)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _column_exists(table_name, column_name):
        op.drop_column(table_name, column_name)
