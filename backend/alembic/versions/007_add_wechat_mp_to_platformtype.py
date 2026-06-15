"""add wechat_mp to platformtype enum

Revision ID: 007
Revises: 006
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 WECHAT_MP 平台到 platformtype 枚举。

    修复微信公众号账号创建时 InvalidTextRepresentationError 错误：
    asyncpg/asyncpg.postgres 拒收未在 PG enum 中定义的值。
    """
    # PostgreSQL 12+ 允许在事务外执行 ALTER TYPE ... ADD VALUE
    op.execute("ALTER TYPE platformtype ADD VALUE IF NOT EXISTS 'WECHAT_MP'")


def downgrade() -> None:
    """回滚：移除 WECHAT_MP（注意：PG 不支持在事务内 DROP enum value，需要手动处理）"""
    # PG 限制：不能在事务中 DROP 枚举值（必须保证无数据引用）
    # 此处仅做提示，开发者应人工确认无数据后再执行
    raise NotImplementedError(
        "PostgreSQL does not support removing enum values inside a transaction. "
        "Manually verify no rows use WECHAT_MP, then: ALTER TYPE platformtype DROP VALUE 'WECHAT_MP';"
    )
