"""create platform_templates table with page_structure

创建平台生成模板表，包含 page_structure (JSONB) 字段，
驱动空白大纲创建和前端渲染。

Revision ID: 002
Revises: 001
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'platform_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('platform', sa.String(30), unique=True, index=True, nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('outline_template', sa.Text(), nullable=False),
        sa.Column('image_template', sa.Text(), nullable=False),
        sa.Column('page_structure', postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column('video_template', sa.Text(), nullable=True),
        sa.Column('default_size', sa.String(20), server_default='1024x1024'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('platform_templates')
