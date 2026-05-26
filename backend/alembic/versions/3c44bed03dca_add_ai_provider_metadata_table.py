"""add_ai_provider_metadata_table

Revision ID: 3c44bed03dca_add
Revises: 004
Create Date: 2026-05-26 22:15:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3c44bed03dca_add'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建 ai_provider_metadata 表
    op.create_table(
        'ai_provider_metadata',
        sa.Column('provider_id', sa.String(length=50), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('icon', sa.String(length=50), server_default='brain'),
        sa.Column('color', sa.String(length=20), server_default='#94a3b8'),
        sa.Column('description', sa.String(length=500), server_default=''),
        sa.Column('base_url', sa.String(length=500), nullable=True),
        sa.Column('api_key', sa.String(length=500), nullable=True),
        sa.Column('api_format', sa.String(length=50), server_default='openai-compatible'),
        sa.Column('request_template', sa.Text(), nullable=True),
        sa.Column('supported_types', sa.Text(), server_default='[]'),
        sa.Column('default_models', sa.Text(), server_default='{}'),
        sa.Column('available_models', sa.Text(), server_default='{}'),
        sa.Column('default_params', sa.Text(), server_default='{}'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('is_editable', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default='now()'),
        sa.Column('updated_at', sa.DateTime(), server_default='now()'),
    )


def downgrade() -> None:
    op.drop_table('ai_provider_metadata')
