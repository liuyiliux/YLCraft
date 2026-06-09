"""add book source cookies

Revision ID: 005
Revises: 004
Create Date: 2026-06-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "book_source_cookies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("book_source_id", sa.String(), sa.ForeignKey("book_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("cookie_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_book_source_cookies_book_source_id", "book_source_cookies", ["book_source_id"])
    op.create_index("idx_book_source_cookies_domain", "book_source_cookies", ["domain"])
    op.create_index("idx_book_source_cookies_is_active", "book_source_cookies", ["is_active"])


def downgrade() -> None:
    op.drop_index("idx_book_source_cookies_is_active", table_name="book_source_cookies")
    op.drop_index("idx_book_source_cookies_domain", table_name="book_source_cookies")
    op.drop_index("idx_book_source_cookies_book_source_id", table_name="book_source_cookies")
    op.drop_table("book_source_cookies")
