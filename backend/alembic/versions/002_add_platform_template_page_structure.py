"""add page_structure (JSONB) to platform_templates

每个平台模板新增 page_structure 字段，定义默认页面结构和字段
驱动空白大纲创建和前端渲染

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
    # 使用 IF NOT EXISTS 避免表已存在时报错
    op.execute("""
        ALTER TABLE platform_templates
        ADD COLUMN IF NOT EXISTS page_structure JSONB DEFAULT '{}'::jsonb
    """)
    # 为已有数据设置默认值
    op.execute("""
        UPDATE platform_templates
        SET page_structure = '{"default_pages": []}'::jsonb
        WHERE page_structure IS NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE platform_templates
        DROP COLUMN IF EXISTS page_structure
    """)
