"""
YLCraft — 任务队列管理 API

GET  /api/v1/tasks       — 所有任务列表（简单聚合视图）
GET  /api/v1/tasks/:id   — 单个任务详情
GET  /api/v1/tasks/stats — 统计概览数据
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.task_queue import get_task_queue, task_event_to_dict

router = APIRouter()
logger = logging.getLogger("ylcraft.tasks")


class TaskInfo(BaseModel):
    task_id: str
    task_type: str
    status: str
    progress: int
    progress_message: str
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None
    events: list[dict[str, Any]] | None = None
    error: str | None = None


class TaskStats(BaseModel):
    total: int = 0
    completed: int = 0
    pending: int = 0
    running: int = 0
    failed: int = 0
    images: int = 0
    videos: int = 0
    characters: int = 0
    stories: int = 0
    today_count: int = 0
    week_count: int = 0


class TaskListResponse(BaseModel):
    success: bool = True
    tasks: list[TaskInfo]


class TaskDetailResponse(BaseModel):
    success: bool = True
    task: TaskInfo | None = None


class TaskStatsResponse(BaseModel):
    success: bool = True
    stats: TaskStats


class TaskActionResponse(BaseModel):
    success: bool = True
    message: str
    task: TaskInfo | None = None


def _format_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _get_task_value(task: Any, key: str, default: Any = None) -> Any:
    if isinstance(task, dict):
        return task.get(key, default)
    return getattr(task, key, default)


def _normalize_status(status: Any) -> str:
    if hasattr(status, "value"):
        status = status.value
    value = str(status or "").lower()
    return {
        "completed": "done",
        "succeeded": "done",
        "success": "done",
        "downloading": "running",
        "processing": "running",
        "queued": "pending",
        "cancel": "cancelled",
        "canceled": "cancelled",
    }.get(value, value)


def _duration_seconds(task: Any) -> float | None:
    started = _get_task_value(task, "started_at") or _get_task_value(task, "created_at")
    finished = _get_task_value(task, "completed_at") or _get_task_value(task, "finished_at")
    if not started:
        return None
    end = finished if finished else datetime.now().timestamp()
    if hasattr(started, "timestamp"):
        started = started.timestamp()
    if hasattr(end, "timestamp"):
        end = end.timestamp()
    try:
        return max(0, round(float(end) - float(started), 2))
    except (TypeError, ValueError):
        return None


def _task_status(task: Any) -> str:
    return _normalize_status(_get_task_value(task, "status", ""))


def _task_info(task: Any, include_detail: bool = False) -> TaskInfo:
    payload = _get_task_value(task, "payload")
    result = _get_task_value(task, "result")
    diagnostics = None
    if include_detail:
        if isinstance(payload, dict) and isinstance(payload.get("diagnostics"), dict):
            diagnostics = payload.get("diagnostics")
        if isinstance(result, dict) and isinstance(result.get("diagnostics"), dict):
            diagnostics = {**(diagnostics or {}), **result.get("diagnostics")}
    events = None
    if include_detail:
        raw_events = _get_task_value(task, "events", []) or []
        events = [task_event_to_dict(event) if not isinstance(event, dict) else event for event in raw_events]
    return TaskInfo(
        task_id=_get_task_value(task, "task_id"),
        task_type=_get_task_value(task, "task_type"),
        status=_task_status(task),
        progress=int(_get_task_value(task, "progress", 0) or 0),
        progress_message=_get_task_value(task, "progress_message", "") or _get_task_value(task, "message", "") or "",
        created_at=_format_timestamp(_get_task_value(task, "created_at")),
        started_at=_format_timestamp(_get_task_value(task, "started_at")),
        completed_at=_format_timestamp(_get_task_value(task, "completed_at") or _get_task_value(task, "finished_at")),
        duration_seconds=_duration_seconds(task),
        payload=payload if include_detail else None,
        result=result if include_detail else None,
        diagnostics=diagnostics,
        events=events,
        error=_get_task_value(task, "error") if include_detail else None,
    )


def _download_task_info(task_id: str, data: dict[str, Any], include_detail: bool = False) -> TaskInfo:
    progress = int(data.get("progress") or 0)
    result = {
        "file_path": data.get("file_path"),
        "asset_id": data.get("asset_id"),
    }
    result = {k: v for k, v in result.items() if v}
    payload = {
        "url": data.get("url"),
        "quality": data.get("quality"),
        "title": data.get("title"),
        "page_url": data.get("page_url"),
        "is_audio": data.get("is_audio"),
        "asset_id": data.get("asset_id"),
    }
    payload = {k: v for k, v in payload.items() if v is not None and v != ""}

    return TaskInfo(
        task_id=task_id,
        task_type="download",
        status=_normalize_status(data.get("status")),
        progress=progress,
        progress_message=data.get("progress_message") or data.get("message") or "",
        created_at=_format_timestamp(data.get("created_at")),
        started_at=_format_timestamp(data.get("started_at")),
        completed_at=_format_timestamp(data.get("completed_at") or data.get("finished_at")),
        duration_seconds=_duration_seconds(data),
        payload=payload if include_detail else None,
        result=result or None,
        error=data.get("error"),
    )


def _external_task_infos(include_detail: bool = False) -> list[TaskInfo]:
    """Collect task views from modules that still keep their own in-memory task stores."""
    infos: list[TaskInfo] = []
    try:
        from app.api.v1 import download

        for task_id, data in getattr(download, "_download_tasks", {}).items():
            if isinstance(data, dict):
                infos.append(_download_task_info(task_id, data, include_detail=include_detail))
    except Exception as exc:
        logger.debug("Failed to collect download tasks: %s", exc)
    return infos


def _all_task_infos(include_detail: bool = False) -> list[TaskInfo]:
    queue = get_task_queue()
    infos: list[TaskInfo] = []
    seen: set[str] = set()
    if hasattr(queue, "_tasks"):
        for task in queue._tasks.values():
            info = _task_info(task, include_detail=include_detail)
            infos.append(info)
            seen.add(info.task_id)

    for info in _external_task_infos(include_detail=include_detail):
        if info.task_id not in seen:
            infos.append(info)
            seen.add(info.task_id)

    existing_asset_ids = {
        (info.result or {}).get("asset_id")
        for info in infos
        if info.task_type == "download" and info.result
    }
    for info in _recent_asset_download_infos(include_detail=include_detail):
        asset_id = (info.result or {}).get("asset_id")
        if info.task_id not in seen and asset_id not in existing_asset_ids:
            infos.append(info)
            seen.add(info.task_id)

    infos.sort(key=lambda item: item.created_at or "", reverse=True)
    return infos


def _find_external_task(task_id: str, include_detail: bool = True) -> TaskInfo | None:
    try:
        from app.api.v1 import download

        data = getattr(download, "_download_tasks", {}).get(task_id)
        if isinstance(data, dict):
            return _download_task_info(task_id, data, include_detail=include_detail)
    except Exception as exc:
        logger.debug("Failed to find external task %s: %s", task_id, exc)
    if task_id.startswith("asset_download_"):
        asset_id = task_id.removeprefix("asset_download_")
        try:
            from app.db.database import SessionLocal
            from app.db.models.asset import Asset

            with SessionLocal() as session:
                asset = session.query(Asset).filter(Asset.id == asset_id).one_or_none()
            if asset:
                return _asset_download_task_info(asset, include_detail=include_detail)
        except Exception as exc:
            logger.debug("Failed to find asset-backed task %s: %s", task_id, exc)
    return None


def _cancel_external_task(task_id: str) -> TaskInfo | None:
    try:
        from app.api.v1 import download

        data = getattr(download, "_download_tasks", {}).get(task_id)
        if isinstance(data, dict):
            status = _normalize_status(data.get("status"))
            if status in {"done", "failed", "cancelled"}:
                return _download_task_info(task_id, data, include_detail=True)
            data["status"] = "CANCELLED"
            data["progress_message"] = "已取消"
            data["completed_at"] = datetime.now().timestamp()
            return _download_task_info(task_id, data, include_detail=True)
    except Exception as exc:
        logger.debug("Failed to cancel external task %s: %s", task_id, exc)
    return None


def _delete_external_task(task_id: str) -> TaskInfo | None:
    try:
        from app.api.v1 import download

        tasks = getattr(download, "_download_tasks", {})
        data = tasks.pop(task_id, None)
        if isinstance(data, dict):
            return _download_task_info(task_id, data, include_detail=True)
    except Exception as exc:
        logger.debug("Failed to delete external task %s: %s", task_id, exc)
    return None


def _asset_download_task_id(asset_id: str) -> str:
    return f"asset_download_{asset_id}"


def _asset_download_task_info(asset: Any, include_detail: bool = False) -> TaskInfo:
    payload = {
        "source_url": getattr(asset, "source_url", ""),
        "platform": getattr(asset, "platform", ""),
        "title": getattr(asset, "title", ""),
    }
    payload = {key: value for key, value in payload.items() if value}
    result = {
        "asset_id": getattr(asset, "id", ""),
        "file_path": getattr(asset, "file_path", ""),
    }
    result = {key: value for key, value in result.items() if value}

    timing = {
        "created_at": getattr(asset, "created_at", None),
        "completed_at": getattr(asset, "updated_at", None),
    }
    return TaskInfo(
        task_id=_asset_download_task_id(asset.id),
        task_type="download",
        status="done",
        progress=100,
        progress_message="下载完成，已入素材库",
        created_at=_format_timestamp(getattr(asset, "created_at", None)),
        started_at=_format_timestamp(getattr(asset, "created_at", None)),
        completed_at=_format_timestamp(getattr(asset, "updated_at", None)),
        duration_seconds=_duration_seconds(timing),
        payload=payload if include_detail else None,
        result=result or None,
        error=None,
    )


def _recent_asset_download_infos(include_detail: bool = False, limit: int = 30) -> list[TaskInfo]:
    """Backfill completed download tasks from recent parsed media assets."""
    try:
        from sqlalchemy import func

        from app.db.database import SessionLocal
        from app.db.models.asset import Asset

        with SessionLocal() as session:
            assets = (
                session.query(Asset)
                .filter(Asset.source_type == "parse")
                .filter(Asset.status == "READY")
                .filter(Asset.deleted_at.is_(None))
                .filter(func.lower(Asset.type).in_(["video", "audio"]))
                .order_by(Asset.updated_at.desc())
                .limit(limit)
                .all()
            )
        return [_asset_download_task_info(asset, include_detail=include_detail) for asset in assets]
    except Exception as exc:
        logger.debug("Failed to collect recent asset download tasks: %s", exc)
        return []


@router.get("", response_model=TaskListResponse, summary="任务列表")
async def list_tasks():
    """
    返回所有活跃任务（内存视图）。
    当前聚合 core.task_queue 以及仍在迁移中的下载任务表。
    """
    return TaskListResponse(success=True, tasks=_all_task_infos())


@router.get("/stats", response_model=TaskStatsResponse, summary="任务统计")
async def get_task_stats():
    """返回任务统计数据，用于 Dashboard"""
    tasks = _all_task_infos()

    total = len(tasks)
    completed = 0
    pending = 0
    running = 0
    failed = 0
    images = 0
    videos = 0
    characters = 0
    stories = 0
    today_count = 0
    week_count = 0

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    for task in tasks:
        status = task.status

        if status in {"done", "completed", "succeeded"}:
            completed += 1
        elif status == "pending":
            pending += 1
        elif status == "running":
            running += 1
        elif status == "failed":
            failed += 1

        if task.created_at:
            try:
                created_date = datetime.fromisoformat(task.created_at)
            except ValueError:
                created_date = None
            if created_date and created_date >= today_start:
                today_count += 1
            if created_date and created_date >= week_start:
                week_count += 1

        task_type = task.task_type.lower()
        if "image" in task_type:
            images += 1
        elif "video" in task_type or task_type == "download":
            videos += 1
        elif "character" in task_type:
            characters += 1
        elif "story" in task_type:
            stories += 1

    return TaskStatsResponse(
        success=True,
        stats=TaskStats(
            total=total,
            completed=completed,
            pending=pending,
            running=running,
            failed=failed,
            images=images,
            videos=videos,
            characters=characters,
            stories=stories,
            today_count=today_count,
            week_count=week_count,
        ),
    )


@router.get("/{task_id}", response_model=TaskDetailResponse, summary="任务详情")
async def get_task_detail(task_id: str):
    """返回指定任务的详细信息"""
    queue = get_task_queue()
    task = await queue.get_task(task_id)
    if task:
        return TaskDetailResponse(success=True, task=_task_info(task, include_detail=True))

    external_task = _find_external_task(task_id, include_detail=True)
    if external_task:
        return TaskDetailResponse(success=True, task=external_task)

    return TaskDetailResponse(success=False, task=None)


@router.post("/{task_id}/cancel", response_model=TaskActionResponse, summary="取消任务")
async def cancel_task(task_id: str):
    """
    将任务标记为取消。

    当前队列没有持有底层 asyncio.Task 的句柄，因此这里提供的是状态级取消：
    业务执行器如果已在运行，可能仍会继续完成；任务中心会立即反映用户取消意图。
    """
    queue = get_task_queue()
    task = await queue.get_task(task_id)
    if task:
        status = _task_status(task)
        if status in {"done", "completed", "failed", "cancelled"}:
            return TaskActionResponse(success=False, message=f"任务已处于 {status} 状态，无法取消", task=_task_info(task, True))

        task.status = "cancelled"  # type: ignore[assignment]
        task.progress_message = "已取消"
        task.completed_at = datetime.now().timestamp()
        await queue.update_task(task)
        return TaskActionResponse(success=True, message="任务已取消", task=_task_info(task, True))

    external_task = _cancel_external_task(task_id)
    if external_task:
        if external_task.status in {"done", "failed", "cancelled"} and external_task.progress_message != "已取消":
            return TaskActionResponse(success=False, message=f"任务已处于 {external_task.status} 状态，无法取消", task=external_task)
        return TaskActionResponse(success=True, message="任务已取消", task=external_task)

    raise HTTPException(status_code=404, detail="任务不存在")


@router.delete("/{task_id}", response_model=TaskActionResponse, summary="删除任务")
async def delete_task(task_id: str):
    """从当前内存任务视图中删除任务。"""
    queue = get_task_queue()
    task = await queue.get_task(task_id)
    if task:
        if hasattr(queue, "_tasks"):
            async with queue._lock:
                queue._tasks.pop(task_id, None)
        return TaskActionResponse(success=True, message="任务已删除", task=_task_info(task, True))

    external_task = _delete_external_task(task_id)
    if external_task:
        return TaskActionResponse(success=True, message="任务已删除", task=external_task)

    raise HTTPException(status_code=404, detail="任务不存在")
