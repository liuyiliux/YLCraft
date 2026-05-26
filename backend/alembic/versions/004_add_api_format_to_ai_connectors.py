"""add api_format to ai_connectors

Revision ID: 004
Revises: 003
Create Date: 2026-05-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ai_connectors',
        sa.Column('api_format', sa.String(36), nullable=False, server_default='custom')
    )


def downgrade() -> None:
    op.drop_column('ai_connectors', 'api_format')
