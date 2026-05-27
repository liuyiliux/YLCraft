"""add deleted_at to assets

为 assets 表添加软删除支持所需的 deleted_at 字段。
该表在早期通过 SQLModel.create_all() 创建，未纳入初始迁移。

Revision ID: 003
Revises: 002
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # assets 表添加 deleted_at 字段（如果不存在）
    op.execute("""
        ALTER TABLE assets
        ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITHOUT TIME ZONE
    """)
    # 添加索引加速软删除查询
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_assets_deleted_at
        ON assets (deleted_at)
        WHERE deleted_at IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_assets_deleted_at")
    op.execute("ALTER TABLE assets DROP COLUMN IF EXISTS deleted_at")
