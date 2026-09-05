"""一次性清库脚本（阶段 6）：删除 ``world_maps`` 与 ``world_map_revisions`` 全部行。

背景：区域几何重构把区域从「成员据点围合凸包」改为「独立形状 +
语义参数」（openspec 规格 region-geometry / 决策记录 D-1），旧数据的空间语义
已作废，按既定决策「直接清库，不备份」执行。

行为：
  1. 打印两张表的当前行数（world_maps / world_map_revisions）；
  2. 需要显式确认：交互式输入 ``yes``，或命令行加 ``--yes``（自动化用）；
  3. 删除两张表全部行；两表均空时无事发生（幂等，可重复执行）。

用法：
  python backend/scripts/cleanup_world_maps.py            # 只报数量，交互确认
  python backend/scripts/cleanup_world_maps.py --yes      # 跳过确认直接清库
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 与应用同一数据源：先加载 backend/.env（DATABASE_URL），再导入 db 模块。
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_ROOT / ".env")

from sqlmodel import delete, select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models.novel_source import WorldMapDocument, WorldMapRevision  # noqa: E402


def _count(model) -> int:
    with SessionLocal() as session:
        return len(list(session.exec(select(model)).all()))


def main() -> int:
    parser = argparse.ArgumentParser(description="清空 world_maps 与 world_map_revisions（幂等，需确认）")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认，直接清库")
    args = parser.parse_args()

    map_count = _count(WorldMapDocument)
    revision_count = _count(WorldMapRevision)
    print(f"world_maps          : {map_count} 行")
    print(f"world_map_revisions : {revision_count} 行")
    if map_count == 0 and revision_count == 0:
        print("两张表已是空表，无事发生（幂等）。")
        return 0

    if not args.yes:
        try:
            answer = input(
                f"将删除全部 {map_count} 张地图与 {revision_count} 条历史快照，且不备份。"
                "输入 yes 确认："
            )
        except EOFError:
            print("\n非交互环境且未加 --yes：已中止，未删除任何数据。")
            return 1
        if answer.strip().lower() != "yes":
            print("未确认：已中止，未删除任何数据。")
            return 1

    with SessionLocal() as session:
        session.exec(delete(WorldMapRevision))
        session.exec(delete(WorldMapDocument))
        session.commit()
    print(f"已清空：world_maps -{map_count} 行，world_map_revisions -{revision_count} 行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
