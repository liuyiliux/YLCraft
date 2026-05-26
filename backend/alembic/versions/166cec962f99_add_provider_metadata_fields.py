"""add_provider_metadata_fields

Revision ID: 166cec962f99
Revises: 3c44bed03dca_add
Create Date: 2026-05-26 23:27:57.263277
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '166cec962f99'
down_revision: Union[str, None] = '3c44bed03dca_add'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加新字段到 ai_provider_metadata 表
    op.add_column('ai_provider_metadata', sa.Column('request_templates', sa.Text(), nullable=True))
    op.add_column('ai_provider_metadata', sa.Column('response_configs', sa.Text(), nullable=True))
    op.add_column('ai_provider_metadata', sa.Column('supported_sizes', sa.Text(), nullable=True))
    op.add_column('ai_provider_metadata', sa.Column('reference_image_configs', sa.Text(), nullable=True))
    op.add_column('ai_provider_metadata', sa.Column('parameter_transforms', sa.Text(), nullable=True))
    
    # 设置默认值
    op.execute("UPDATE ai_provider_metadata SET request_templates = '{}' WHERE request_templates IS NULL")
    op.execute("UPDATE ai_provider_metadata SET response_configs = '{}' WHERE response_configs IS NULL")
    op.execute("UPDATE ai_provider_metadata SET supported_sizes = '{}' WHERE supported_sizes IS NULL")
    op.execute("UPDATE ai_provider_metadata SET reference_image_configs = '{}' WHERE reference_image_configs IS NULL")
    op.execute("UPDATE ai_provider_metadata SET parameter_transforms = '{}' WHERE parameter_transforms IS NULL")
    
    # 设置为 NOT NULL
    op.alter_column('ai_provider_metadata', 'request_templates', nullable=False)
    op.alter_column('ai_provider_metadata', 'response_configs', nullable=False)
    op.alter_column('ai_provider_metadata', 'supported_sizes', nullable=False)
    op.alter_column('ai_provider_metadata', 'reference_image_configs', nullable=False)
    op.alter_column('ai_provider_metadata', 'parameter_transforms', nullable=False)


def downgrade() -> None:
    # 删除新字段
    op.drop_column('ai_provider_metadata', 'request_templates')
    op.drop_column('ai_provider_metadata', 'response_configs')
    op.drop_column('ai_provider_metadata', 'supported_sizes')
    op.drop_column('ai_provider_metadata', 'reference_image_configs')
    op.drop_column('ai_provider_metadata', 'parameter_transforms')