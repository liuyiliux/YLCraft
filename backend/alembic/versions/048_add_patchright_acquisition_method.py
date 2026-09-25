"""add PATCHRIGHT to acquisitionmethod enum

Revision ID: 048_add_patchright_acquisition_method
Revises: 047_add_fanqie_platform_type

背景：`PatchrightAcquisitionManager._save_to_db` 一直写
`AcquisitionMethod.PATCHRIGHT`，但 Python 枚举 `AcquisitionMethod` 里
**没有这个成员**（只有 MANUAL / PLAYWRIGHT / QRCODE），实际抛的是
`AttributeError: PATCHRIGHT`。

之所以一直没被发现也不好查：`except` 里用的是
`logger.error(f"... failed: {e}")` —— 只打 `str(e)`，**丢掉了异常类型**，
日志里就剩下孤零零的 `PATCHRIGHT`，看起来像数据库枚举报错，其实是属性不存在。
（同类误导已在本项目出现多次：见 `PlatformType.FANQIE` 那次。）

修复两步：
1. Python 枚举补 `PATCHRIGHT`（本迁移对应的同批改动）
2. PostgreSQL 原生枚举补 **大写 `PATCHRIGHT`** —— SQLAlchemy 对 enum 字段默认存
   name（大写）；实测 `platform_connections` 现存值均为大写（QRCODE 等），
   库里那批小写值（manual/playwright/qrcode）是历史遗留、未被使用。

保留 `PLAYWRIGHT`：历史连接可能仍用它，删除会让旧数据读不出来。
"""

from alembic import context, op


revision = "048_add_patchright_acquisition_method"
down_revision = "047_add_fanqie_platform_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE acquisitionmethod ADD VALUE IF NOT EXISTS 'PATCHRIGHT'")


def downgrade() -> None:
    # PostgreSQL 不支持删除枚举值；降级保持空操作。
    pass
