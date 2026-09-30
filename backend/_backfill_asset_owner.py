"""把历史「无主」素材节点补上 owner（2026-09-29）。

## 背景

下载/解析创建的素材节点原来**不写 `owner_user_id`**，
而素材库列表按 owner 过滤 —— 用户看不到自己下载的素材。

已修代码（新建的会带 owner），但**历史节点仍是 None**，
所以要把它们补到 root 用户名下。

用法：
    python backend/_backfill_asset_owner.py          # 预览
    python backend/_backfill_asset_owner.py --apply  # 执行
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from sqlalchemy import text  # noqa: E402

from app.db.database import AsyncSessionLocal  # noqa: E402


async def main(apply: bool) -> None:
    async with AsyncSessionLocal() as s:
        # 取 root 用户 id
        uid = (await s.execute(text(
            "SELECT id FROM users WHERE username = 'root' LIMIT 1"))).scalar()
        if not uid:
            print("  ✗ 没找到 root 用户")
            return
        print(f"  root 用户 id = {uid}")

        rows = (await s.execute(text("""
            SELECT id, name FROM asset_nodes
            WHERE owner_user_id IS NULL
            ORDER BY created_at DESC
        """))).fetchall()
        print(f"  无主素材节点: {len(rows)} 个")
        for r in rows[:8]:
            print(f"    {str(r[0])[:10]}  {str(r[1])[:44]!r}")
        if len(rows) > 8:
            print(f"    …还有 {len(rows) - 8} 个")

        if not apply:
            print("\n  （预览模式，未改动。加 --apply 执行）")
            return

        n = (await s.execute(text("""
            UPDATE asset_nodes SET owner_user_id = :u
            WHERE owner_user_id IS NULL
        """), {"u": uid})).rowcount
        await s.commit()
        print(f"\n  ✅ 已补 {n} 个节点的 owner")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
