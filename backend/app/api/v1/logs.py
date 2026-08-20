"""
YLCraft — 平台事件日志 / 运行日志 API

GET  /api/v1/logs           — 事件日志列表（筛选/分页）
GET  /api/v1/logs/{id}      — 单条事件详情
GET  /api/v1/logs/runtime   — 运行日志（文件 tail，级别/关键词过滤）
POST /api/v1/logs/{id}/retry — 失败事件重发（按场景重放原请求）
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.platform_log import service as platform_log
from app.services.ai import get_ai_service
from app.services.ai.types import ImageGenerationRequest, VideoGenerationRequest
import dataclasses

router = APIRouter()
logger = logging.getLogger("ylcraft.logs")

# 运行日志文件（与 main.py 配置保持一致）
_LOG_FILE = Path(__file__).parent.parent.parent.parent / "storage" / "logs" / "app.log"
_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}


class EventListResponse(BaseModel):
    success: bool = True
    items: list[dict[str, Any]] = []
    total: int = 0
    page: int = 1
    page_size: int = 50


class EventDetailResponse(BaseModel):
    success: bool = True
    item: dict[str, Any] | None = None


class RuntimeLogLine(BaseModel):
    timestamp: str = ""
    level: str = ""
    name: str = ""
    message: str = ""


class RuntimeLogResponse(BaseModel):
    success: bool = True
    lines: list[RuntimeLogLine] = []
    before: str = ""
    has_more: bool = False


class RetryResponse(BaseModel):
    success: bool = False
    event_id: str | None = None
    task_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# 事件日志查询
# ---------------------------------------------------------------------------


@router.get("", response_model=EventListResponse, summary="事件日志列表")
async def list_logs(
    scene: Optional[str] = None,
    level: Optional[str] = None,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    project_id: Optional[str] = None,
    q: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    items, total = await platform_log.list_events(
        scene=scene,
        level=level,
        status=status,
        task_type=task_type,
        project_id=project_id,
        q=q,
        since=since,
        until=until,
        page=page,
        page_size=page_size,
    )
    return EventListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/runtime", response_model=RuntimeLogResponse, summary="运行日志（文件 tail）")
async def list_runtime_logs(
    level: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(200, ge=1, le=2000),
    before: Optional[str] = None,
):
    if level and level.lower() not in _LOG_LEVELS:
        raise HTTPException(status_code=400, detail="无效的日志级别")
    if not _LOG_FILE.is_file():
        return RuntimeLogResponse(lines=[], has_more=False)

    lines = _read_runtime_lines(_LOG_FILE, limit=limit, before=before)
    filtered: list[RuntimeLogLine] = []
    for raw in lines:
        parsed = _parse_runtime_line(raw)
        if level and parsed.level.lower() != level.lower():
            continue
        if q and q.lower() not in parsed.message.lower() and q.lower() not in parsed.name.lower():
            continue
        filtered.append(parsed)

    # before 游标：用首条时间戳继续向前翻页
    next_before = filtered[0].timestamp if filtered else ""
    return RuntimeLogResponse(lines=filtered, before=next_before, has_more=len(filtered) >= limit)


@router.get("/{event_id}", response_model=EventDetailResponse, summary="事件日志详情")
async def get_log(event_id: str):
    item = await platform_log.get_event(event_id)
    if item is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return EventDetailResponse(item=item)


# ---------------------------------------------------------------------------
# 失败重发
# ---------------------------------------------------------------------------


@router.post("/{event_id}/retry", response_model=RetryResponse, summary="失败事件重发")
async def retry_log(event_id: str):
    item = await platform_log.get_event(event_id)
    if item is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    if item.get("status") != "failed":
        raise HTTPException(status_code=409, detail="只有失败的事件可以重发")
    payload = item.get("retry_payload") or {}
    if not payload:
        raise HTTPException(status_code=400, detail="该事件缺少可重放参数")

    scene = item.get("scene", "")
    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    new_event_id: Optional[str] = None
    new_task_id: Optional[str] = None
    new_error: Optional[str] = None

    try:
        if scene == "image":
            image_payload = _filter_fields(payload, ImageGenerationRequest)
            result = await manager.generate_image(ImageGenerationRequest(**image_payload))
            new_task_id = result.task_id or None
            if result.success:
                new_event_id = await platform_log.record_event(
                    scene="image",
                    task_type="image_generation",
                    task_id=new_task_id,
                    level="info",
                    status="success",
                    provider=result.provider or "",
                    model=result.model or "",
                    message="图片生成重发成功",
                    duration_ms=result.latency_ms,
                    retry_of=event_id,
                )
            else:
                new_error = result.error
        elif scene == "video":
            video_payload = _filter_fields(payload, VideoGenerationRequest)
            result = await manager.generate_video(VideoGenerationRequest(**video_payload))
            new_task_id = result.task_id or None
            if result.success:
                new_event_id = await platform_log.record_event(
                    scene="video",
                    task_type="video_generation",
                    task_id=new_task_id,
                    level="info",
                    status="success",
                    provider=result.provider or "",
                    model=result.model or "",
                    message="视频生成重发成功",
                    duration_ms=result.latency_ms,
                    retry_of=event_id,
                )
            else:
                new_error = result.error
        elif scene == "llm":
            messages = payload.get("messages", [])
            model = payload.get("model")
            result = await manager.chat(messages, model=model)
            if result.success:
                new_event_id = await platform_log.record_event(
                    scene="llm",
                    task_type="llm_chat",
                    level="info",
                    status="success",
                    provider=result.provider or "",
                    model=result.model or model or "",
                    message="文本生成重发成功",
                    duration_ms=result.latency_ms,
                    retry_of=event_id,
                )
            else:
                new_error = result.error
        else:
            raise HTTPException(status_code=400, detail=f"不支持的场景重发: {scene}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Retry of event %s failed: %s", event_id, exc)
        new_error = str(exc)

    if new_error:
        new_event_id = await platform_log.record_event(
            scene=scene,
            task_type=item.get("task_type", ""),
            level="error",
            status="failed",
            provider=item.get("provider", ""),
            model=item.get("model", ""),
            message="重发失败",
            error=new_error,
            retry_of=event_id,
        )

    if new_event_id:
        await platform_log.link_retried_by(event_id, new_event_id)
        return RetryResponse(success=new_error is None, event_id=new_event_id, task_id=new_task_id, error=new_error)
    return RetryResponse(success=False, error=new_error or "重发未产生结果")


# ---------------------------------------------------------------------------
# 运行日志读取 helper
# ---------------------------------------------------------------------------


def _read_runtime_lines(path: Path, *, limit: int, before: Optional[str]) -> list[str]:
    """读取文件末尾若干行；若给 before，则读到该时间戳之前的行。"""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return []

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if before:
        lines = [ln for ln in lines if ln < before]
    return lines[-limit:]


def _filter_fields(payload: dict[str, Any], dataclass_type: Any) -> dict[str, Any]:
    """只保留 dataclass 接受的字段，避免 lineage 等额外字段导致 TypeError。"""
    valid = {f.name for f in dataclasses.fields(dataclass_type)}
    return {k: v for k, v in payload.items() if k in valid}


def _parse_runtime_line(raw: str) -> RuntimeLogLine:
    # 格式: "2026-08-20 16:00:00,000 LEVEL name: message"
    line = RuntimeLogLine(message=raw)
    parts = raw.split(" ", 3)
    if len(parts) >= 3:
        line.timestamp = f"{parts[0]} {parts[1].rstrip(',')}"
        line.level = parts[2]
        rest = parts[3] if len(parts) == 4 else ""
        if ": " in rest:
            name, message = rest.split(": ", 1)
            line.name = name
            line.message = message
        else:
            line.name = rest
    return line
