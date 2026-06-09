"""add book source rule metadata

Revision ID: 006
Revises: 005
Create Date: 2026-06-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("book_sources", sa.Column("rule_format", sa.String(), nullable=False, server_default="legado"))
    op.add_column("book_sources", sa.Column("rule_version", sa.String(), nullable=False, server_default=""))
    op.add_column("book_sources", sa.Column("ylcraft_rule", sa.Text(), nullable=False, server_default=""))
    op.add_column("book_sources", sa.Column("original_format", sa.String(), nullable=False, server_default=""))
    op.add_column("book_sources", sa.Column("original_source", sa.Text(), nullable=False, server_default=""))
    op.add_column("book_sources", sa.Column("migration_log", sa.Text(), nullable=False, server_default=""))
    op.create_index("idx_book_sources_rule_format", "book_sources", ["rule_format"])


def downgrade() -> None:
    op.drop_index("idx_book_sources_rule_format", table_name="book_sources")
    op.drop_column("book_sources", "migration_log")
    op.drop_column("book_sources", "original_source")
    op.drop_column("book_sources", "original_format")
    op.drop_column("book_sources", "ylcraft_rule")
    op.drop_column("book_sources", "rule_version")
    op.drop_column("book_sources", "rule_format")
