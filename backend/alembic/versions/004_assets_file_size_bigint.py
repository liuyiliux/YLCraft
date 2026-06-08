"""alter assets file_size to bigint

Revision ID: 004
Revises: 003
Create Date: 2026-06-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "assets",
        "file_size",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_server_default="0",
    )


def downgrade() -> None:
    op.alter_column(
        "assets",
        "file_size",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_server_default="0",
    )
