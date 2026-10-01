"""确保 `connectionstatus` 枚举包含代码里用到的所有值。

## 为什么需要这个脚本（2026-10-01）

`PlatformConnection.status` 在 PostgreSQL 里是 **native enum 类型**
（不是 varchar）。Python 侧加一个枚举值（如今天的 `DISABLED`）
**不会自动同步到数据库** —— 写入时会直接报：

    invalid input value for enum connectionstatus: "disabled"

而且这个错误**只在真的去禁用一条连接时才出现** ——
导入检查、单元测试（用 SQLite 或 mock）全都发现不了。

所以给一个**幂等**的迁移脚本：跑多少次都安全。

## [!] 历史遗留：枚举里有大小写两套值

实测 DB 里同时存在 `active` 和 `ACTIVE`（SQLAlchemy 早期用 `name`
存、后来改用 `value`）。代码现在统一用**小写**
（`ConnectionStatus.ACTIVE.value == "active"`），
所以脚本也两个都补一遍，避免历史行读不出来。

## 用法

    cd backend
    .\\venv_win\\Scripts\\python.exe scripts\\sync_enum_values.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 加载 .env（否则拿不到 DATABASE_URL）
try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
except Exception:
    pass

# 代码里用到的所有 ConnectionStatus 值（小写 = value）
WANTED = ["active", "expired", "failed", "unknown", "disabled"]


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("[X] 没有 DATABASE_URL（检查 backend/.env）")
        return 1
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        import psycopg2
    except ImportError:
        print("[X] 缺 psycopg2（pip install psycopg2-binary）")
        return 1

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    # 1) 找到这个 enum 的类型名（不同环境可能不同）
    cur.execute("""
        SELECT t.typname
        FROM pg_type t
        JOIN pg_attribute a ON a.atttypid = t.oid
        JOIN pg_class c ON c.oid = a.attrelid
        WHERE c.relname = 'platform_connections' AND a.attname = 'status'
    """)
    row = cur.fetchone()
    if not row:
        print("[X] 找不到 platform_connections.status 的类型（表还没建？）")
        conn.close()
        return 1
    type_name = row[0]
    print(f"枚举类型名：{type_name}")

    # 2) 现有值
    cur.execute(
        """
        SELECT e.enumlabel FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = %s ORDER BY e.enumsortorder
        """,
        (type_name,),
    )
    existing = {r[0] for r in cur.fetchall()}
    print(f"现有值：{sorted(existing)}")

    # 3) 补齐（小写 + 大写都补，兼容历史数据）
    added = []
    for val in WANTED:
        for v in (val, val.upper()):
            if v in existing:
                continue
            try:
                cur.execute(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{v}'")
                added.append(v)
            except Exception as exc:
                print(f"  [!] 添加 {v} 失败：{str(exc)[:120]}")

    if added:
        print(f"[OK] 已添加：{added}")
    else:
        print("[OK] 无需改动（所有值都已存在）")

    # 4) 复核
    cur.execute(
        """
        SELECT e.enumlabel FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = %s ORDER BY e.enumsortorder
        """,
        (type_name,),
    )
    final = {r[0] for r in cur.fetchall()}
    missing = [v for v in WANTED if v not in final]
    conn.close()

    if missing:
        print(f"[X] 仍缺：{missing}")
        return 1
    print(f"[OK] 最终值：{sorted(final)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
