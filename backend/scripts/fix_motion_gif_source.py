"""一次性数据修复：把动图资产的 source 从自创的 motion_gif 改成 image_generation。

为什么要改：素材库的「来源」筛选按前端 `SOURCE_TYPE_OPTIONS` 的固定几项分组，
自创的 `motion_gif` 不在其中 —— 卡片显示"未知来源"，且一点「AI生成」筛选
就被排除，表现为"存入素材库成功但找不到"。

只改 metadata 的 source，**不动 lineage**（那是溯源信息，另一个字段）。
幂等：再跑一次不会重复改。
"""

import sys
from pathlib import Path

# `scripts/` 在 `backend/` 下，而 `app` 包也在 `backend/` —— 把 backend 加进
# 搜索路径，脚本才能 `from app...` 导入（直接 `python scripts/x.py` 时
# sys.path[0] 是 scripts/，不是 backend/）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db.database import sync_engine  # noqa: E402

NEW_SOURCE = "image_generation"
OLD_SOURCE = "motion_gif"


def main() -> int:
    with sync_engine.begin() as conn:
        rows = conn.execute(
            text(
                "select id, name from asset_nodes "
                "where metadata_json->>'source' = :old"
            ),
            {"old": OLD_SOURCE},
        ).fetchall()
        if not rows:
            print("没有需要修复的行（已经是 image_generation 或不存在）")
            return 0
        for node_id, name in rows:
            print(f"  修复 {node_id} | {name}")
        conn.execute(
            text(
                "update asset_nodes "
                # `to_jsonb(cast(:new as text))` 而不是 `:new::jsonb`：
                # psycopg2 推断不出 jsonb 参数的类型，会报
                # "could not determine data type of parameter"。
                "set metadata_json = jsonb_set(metadata_json, '{source}', "
                "to_jsonb(cast(:new as text))) "
                "where metadata_json->>'source' = :old"
            ),
            {"new": NEW_SOURCE, "old": OLD_SOURCE},
        )
        # 顺手补 source_url：素材卡预览靠它，早期那批动图没写
        conn.execute(
            text(
                "update asset_nodes "
                "set metadata_json = jsonb_set(metadata_json, '{source_url}', "
                "to_jsonb(coalesce(thumbnail_url, ''))) "
                "where metadata_json->>'source' = :new "
                "and coalesce(metadata_json->>'source_url', '') = '' "
                "and coalesce(thumbnail_url, '') <> ''"
            ),
            {"new": NEW_SOURCE},
        )
    print(f"完成：{len(rows)} 行 source → {NEW_SOURCE}，并补齐 source_url")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
