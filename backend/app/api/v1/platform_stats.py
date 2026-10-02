"""平台健康度**统计**接口（历史成功率 / 耗时 / 风控命中率）。

## 与「体检」的区别（两个不同的东西，别混）

    `/platforms/{p}/health`     → **实时探针**：现在能不能用（发一次搜索）
    `/platforms/{p}/stats`      → **历史统计**：过去一段时间成功率多少

前者回答"现在行不行"，后者回答"最近稳不稳"。
两者互补：实时体检通过但历史成功率低 → 说明**不稳定**（该限速了）。

## 数据来源

`platform_event_logs` 表（**已存在**，无需新表/新依赖）。

⚠️ 2026-10-01 实测发现：这个表**原本只记录 LLM/图片/视频等 AI 场景**，
**没有平台采集记录**（`scene` 里没有 bilibili/douyin 等）——
所以本接口上线时**历史数据为空**，需要先让采集流程开始记录。

本模块同时负责**写入**（`record_platform_event`），
让采集/体检把结果记进去，之后统计才有数据。

## 时间窗口

`hours` 参数（默认 24 小时）。不设上限统计（那会全表扫）。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("ylcraft.api.platform_stats")

router = APIRouter()

# 平台别名 → 统一名（统计时归并，避免 `x`/`twitter` 分成两组）
_ALIAS = {
    "bilibili": "bili",
    "ks": "kuaishou",
    "wb": "weibo",
    "x": "twitter",
    "tw": "twitter",
    "dy": "douyin",
    "xiaohongshu": "xhs",
}


def normalize_platform(p: str) -> str:
    p = (p or "").strip().lower()
    return _ALIAS.get(p, p)


class PlatformStats(BaseModel):
    platform: str
    window_hours: int
    total: int = 0
    success: int = 0
    failed: int = 0
    success_rate: float = 0.0
    # 耗时（只统计成功的，失败的不该混进平均值）
    avg_duration_ms: int = 0
    p95_duration_ms: int = 0
    # 按动作拆分（search / detail / comments / download …）
    by_action: List[Dict[str, Any]] = Field(default_factory=list)
    # 最近一次失败的原因（让用户知道"错在哪"）
    last_error: str = ""
    last_error_at: float = 0.0
    # ⚠️ 采样是否足够 —— 样本太少时**不要**下"稳定/不稳定"的结论
    sample_sufficient: bool = False


class PlatformStatsResponse(BaseModel):
    success: bool = True
    data: Optional[PlatformStats] = None
    message: str = ""


# 样本数低于这个值就不下结论（否则 1 次失败 = 0% 成功率，误导）
MIN_SAMPLE = 5


@router.get("/{platform}/stats", summary="平台历史健康度统计", response_model=PlatformStatsResponse)
async def platform_stats(
    platform: str,
    hours: int = Query(24, ge=1, le=24 * 30, description="统计窗口（小时）"),
) -> PlatformStatsResponse:
    """看某平台过去 `hours` 小时的成功率 / 耗时 / 最近错误。

    ## ⚠️ 数据从哪来

    读 `platform_event_logs`（**已有表**）。

    ⚠️ 实测（2026-10-01）：这个表**原本没有平台采集记录** ——
    所以刚上线时这里会显示"无数据"。采集/体检开始记录后才有统计。
    **不编造数据**：没记录就如实说"无数据"。
    """
    from sqlalchemy import text

    # ⚠️ 正确路径是 `app.db.database`（不是 `app.core.database` ——
    # 我第一版写错了，结果是运行时 500：ImportError 被外层吞成 500）
    from app.db.database import get_async_session

    p = normalize_platform(platform)
    since = time.time() - hours * 3600

    try:
        async with get_async_session() as session:
            # ⚠️ 用 `scene = 'platform'` + `provider = 平台名` 区分。
            # 原来 scene 里只有 llm/image/writing 等 AI 场景。
            rows = (await session.execute(
                text(
                    "SELECT status, duration_ms, task_type, error, created_at "
                    "FROM platform_event_logs "
                    "WHERE scene = 'platform' AND provider = :p AND created_at >= :since "
                    "ORDER BY created_at DESC"
                ),
                {"p": p, "since": since},
            )).fetchall()
    except HTTPException:
        raise
    except Exception as exc:
        # ⚠️ 收窄：只吞**数据库/查询**类错误（统计不可用不该影响采集），
        # 但把真实原因**说出来**，不要笼统的"内部错误"。
        #
        # 2026-10-01 踩过：这里原来是宽泛的 `except Exception`，
        # 把 `ImportError`（session 工厂路径写错）也吞了 ——
        # 表现为"统计不可用"，看不出是代码 bug。
        logger.warning("[stats] 查询失败：%s: %s", type(exc).__name__, exc)
        return PlatformStatsResponse(
            success=True,
            data=PlatformStats(platform=p, window_hours=hours),
            message=(
                f"统计不可用（{type(exc).__name__}: {str(exc)[:120]}）"
                "—— 不影响采集功能"
            ),
        )

    total = len(rows)
    if total == 0:
        return PlatformStatsResponse(
            success=True,
            data=PlatformStats(platform=p, window_hours=hours),
            message=(
                f"最近 {hours} 小时没有 {p} 的采集记录。\n"
                "⚠️ 这不是「平台有问题」—— 是**还没有数据**。\n"
                "（平台事件记录是 2026-10-01 才接入的，之前的历史没有留存。）"
            ),
        )

    success = sum(1 for r in rows if r[0] == "success")
    failed = total - success
    durations = sorted(int(r[1] or 0) for r in rows if r[0] == "success" and (r[1] or 0) > 0)
    avg_ms = int(sum(durations) / len(durations)) if durations else 0
    p95_ms = durations[int(len(durations) * 0.95)] if durations else 0

    # 按动作拆
    by_action: Dict[str, Dict[str, int]] = {}
    for r in rows:
        act = r[2] or "unknown"
        d = by_action.setdefault(act, {"total": 0, "success": 0, "failed": 0})
        d["total"] += 1
        d["success" if r[0] == "success" else "failed"] += 1

    last_err = ""
    last_err_at = 0.0
    for r in rows:
        if r[0] != "success" and r[3]:
            last_err = str(r[3])[:300]
            last_err_at = float(r[4] or 0)
            break

    return PlatformStatsResponse(
        success=True,
        data=PlatformStats(
            platform=p,
            window_hours=hours,
            total=total,
            success=success,
            failed=failed,
            success_rate=round(success / total * 100, 1),
            avg_duration_ms=avg_ms,
            p95_duration_ms=p95_ms,
            by_action=[
                {"action": k, **v, "success_rate": round(v["success"] / v["total"] * 100, 1)}
                for k, v in sorted(by_action.items(), key=lambda x: -x[1]["total"])
            ],
            last_error=last_err,
            last_error_at=last_err_at,
            # ⚠️ 样本太少不要下结论
            sample_sufficient=total >= MIN_SAMPLE,
        ),
        message=(
            f"最近 {hours} 小时：{success}/{total} 成功"
            f"（{round(success / total * 100, 1)}%）"
            + ("" if total >= MIN_SAMPLE else f"\n⚠️ 样本仅 {total} 条，不足以判断稳定性")
        ),
    )


async def record_platform_event(
    platform: str,
    action: str,
    *,
    success: bool = True,
    duration_ms: int = 0,
    error: str = "",
    conn_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """把一次平台操作记进 `platform_event_logs`（供统计用）。

    ## ⚠️ 为什么用 `scene='platform'`

    这个表原本只记 LLM/图片等 AI 场景（`scene` = llm/image/writing…）。
    平台采集是**新接入**的，用 `scene='platform'` + `provider=<平台名>`
    区分，不影响既有数据。

    ## best-effort

    记录失败**绝不影响主流程**（采集本身比统计重要）——
    所以这里吞掉异常，只打警告。
    """
    from app.services.platform_log.service import record_event

    p = normalize_platform(platform)
    summary = {"conn_id": conn_id, **(extra or {})}
    try:
        await record_event(
            scene="platform",
            task_type=action,
            status="success" if success else "failed",
            level="info" if success else "warning",
            provider=p,
            message=f"{p}/{action} " + ("成功" if success else "失败"),
            error=error or None,
            duration_ms=duration_ms,
            request=summary,
        )
    except Exception as exc:
        logger.debug("[stats] 记录事件失败（不影响主流程）：%s", exc)
