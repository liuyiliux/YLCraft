"""add FANQIE to platformtype enum

Revision ID: 047_add_fanqie_platform_type
Revises: 046_add_user_email_reservation

背景：`PlatformType.FANQIE` 早已加进 Python 枚举
（`app/db/models/platform_connection.py`），但 PostgreSQL 的 `platformtype`
原生枚举类型**没有对应值**，于是创建番茄连接时写入/查询直接报：

    psycopg2.errors.InvalidTextRepresentation:
    invalid input value for enum platformtype: "FANQIE"

注意大小写：SQLAlchemy 对 `enum.Enum` 字段默认存 **name（大写）**，
实测库里既有历史遗留的小写值（`fanqie` 等，未被使用），也有真实在用的大写值
（`platform_connections` 现存行为 `WECHAT_MP`、`BILIBILI`）。因此这里补的是
**大写 `FANQIE`** —— 小写那个已存在且不是代码查询用的值。
"""

from alembic import context, op


revision = "047_add_fanqie_platform_type"
down_revision = "046_add_user_email_reservation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 专有：原生枚举加值。其它方言（SQLite 测试库）用 VARCHAR，无需处理。
    if not context.is_offline_mode() and op.get_bind().dialect.name == "postgresql":
        # ADD VALUE 在 PG 12+ 可参与事务，但为兼容老版本仍按惯例单独执行。
        op.execute("ALTER TYPE platformtype ADD VALUE IF NOT EXISTS 'FANQIE'")


def downgrade() -> None:
    # PostgreSQL 不支持删除枚举值；降级保持空操作，避免制造不可逆的半成品。
    pass
