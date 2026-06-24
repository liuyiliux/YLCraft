"""add timeout and test_timeout to ai_connectors

Revision ID: 008
Revises: 007
Create Date: 2026-06-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为 ai_connectors 表添加 timeout 和 test_timeout 字段。

    - timeout: API 请求超时时间（秒），默认 300（5分钟）
    - test_timeout: 连接测试超时时间（秒），默认 20
    """
    op.add_column(
        "ai_connectors",
        sa.Column("timeout", sa.Integer(), nullable=True, server_default="300"),
    )
    op.add_column(
        "ai_connectors",
        sa.Column("test_timeout", sa.Integer(), nullable=True, server_default="20"),
    )


def downgrade() -> None:
    """回滚：移除 timeout 和 test_timeout 字段"""
    op.drop_column("ai_connectors", "test_timeout")
    op.drop_column("ai_connectors", "timeout")
