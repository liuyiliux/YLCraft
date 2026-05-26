"""remove_request_template_field

Revision ID: 20260527_remove_request_template_field
Revises: 166cec962f99_add_provider_metadata_fields
Create Date: 2026-05-27 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260527_remove_request_template_field'
down_revision: Union[str, None] = '166cec962f99_add_provider_metadata_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 删除旧的 request_template 字段（已被 request_templates 替代）
    op.drop_column('ai_provider_metadata', 'request_template')


def downgrade() -> None:
    # 添加回滚的 request_template 字段
    op.add_column('ai_provider_metadata', sa.Column('request_template', sa.Text(), nullable=True))