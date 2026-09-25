"""
YLCraft — 任务队列管理 API

GET  /api/v1/tasks       — 所有任务列表（简单聚合视图）
GET  /api/v1/tasks/:id   — 单个任务详情
GET  /api/v1/tasks/stats — 统计概览数据
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select, text

from app.core.external_api_auth import optional_external_api_key
from app.core.resource_auth import require_owned_or_legacy
from app.core.user_auth import (
    AuthenticatedPrincipal,
    get_authenticated_principal,
    get_authenticated_principal_optional,
)
from app.core.task_queue import get_task_queue, task_event_to_dict
from app.db.database import get_async_session
from app.db.models.external_api_key import ExternalApiKey
from app.db.models.task import Model3DGenerationTask, VideoGenerationTask

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
    """Serialize a task timestamp as an offset-aware ISO 8601 string.

    Task records use two storage shapes: POSIX epoch floats (queue / video / 3D
    ledgers) and naive UTC datetimes (Asset Hub uses ``datetime.utcnow``).
    Returning a bare naive string made browsers assume local time, so a row
    recorded at 09:06 UTC displayed as 09:06 in Beijing instead of 17:06.

    Always attach an explicit offset, and normalize every shape to the server's
    local offset so the lexicographic sort in ``_all_task_infos`` stays valid.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).astimezone().isoformat()
    if hasattr(value, "isoformat"):
        if value.tzinfo is None:
            # Naive values in this codebase are written as UTC; make it explicit
            # before converting so the instant is not silently shifted.
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone().isoformat()
    return str(value)


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a serialized task timestamp back into an aware local datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


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
        "error": "failed",
    }.get(value, value)


def _duration_seconds(task: Any) -> float | None:
    started = _get_task_value(task, "started_at") or _get_task_value(task, "created_at")
    finished = _get_task_value(task, "completed_at") or _get_task_value(task, "finished_at")
    if not started:
        return None
    status = _normalize_status(_get_task_value(task, "status", ""))
    if finished:
        end = finished
    elif status in {"done", "failed", "cancelled"}:
        # A terminal task without an end timestamp has unknown duration. Using
        # "now" here makes old failed rows look like they are still running.
        return None
    else:
        end = datetime.now().timestamp()
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


def _media_task_diagnostics(
    *,
    payload: dict[str, Any] | None,
    result: dict[str, Any] | None,
    provider: str = "",
    model: str = "",
    status: str = "",
) -> dict[str, Any] | None:
    """Merge provider diagnostics with the task center's stable display fields.

    Durable video/3D ledgers store the provider-specific submit or poll payload
    under ``result.diagnostics``. Older image-oriented consumers also look for a
    small set of normalized fields, so expose both here instead of making every
    UI rediscover them.
    """
    result = result if isinstance(result, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    payload_diagnostics = payload.get("diagnostics")
    result_diagnostics = result.get("diagnostics")
    diagnostics = {
        **(payload_diagnostics if isinstance(payload_diagnostics, dict) else {}),
        **(result_diagnostics if isinstance(result_diagnostics, dict) else {}),
    }

    planning = payload.get("planning_summary")
    planning = planning if isinstance(planning, dict) else {}
    resolved_provider = (
        provider
        or str(planning.get("provider") or "")
        or str(payload.get("provider") or "")
    )
    resolved_model = (
        model
        or str(planning.get("model") or "")
        or str(payload.get("model") or "")
    )
    external_task_id = (
        str(diagnostics.get("external_task_id") or "")
        or str(result.get("provider_task_id") or "")
        or str(payload.get("external_task_id") or "")
    )

    normalized = diagnostics
    if resolved_provider:
        normalized.setdefault("provider", resolved_provider)
    if resolved_model:
        normalized.setdefault("model", resolved_model)
    if external_task_id:
        normalized.setdefault("external_task_id", external_task_id)
    if status:
        normalized.setdefault("last_remote_status", status)
    response_excerpt = diagnostics.get("response_excerpt")
    if response_excerpt and not normalized.get("last_response_excerpt"):
        normalized["last_response_excerpt"] = response_excerpt
    return normalized or None


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


async def _video_task_infos(include_detail: bool = False) -> list[TaskInfo]:
    """Expose standalone video workspace records in the global task center."""
    try:
        async with get_async_session() as session:
            rows = (await session.execute(
                select(VideoGenerationTask).order_by(VideoGenerationTask.created_at.desc()).limit(100)
            )).scalars().all()
    except Exception as exc:
        logger.debug("Failed to collect video generation tasks: %s", exc)
        return []

    infos: list[TaskInfo] = []
    for row in rows:
        try:
            payload = json.loads(row.request_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        try:
            result = json.loads(row.result_json or "{}")
        except (TypeError, ValueError):
            result = {}
        info = TaskInfo(
            task_id=row.task_id,
            task_type="video_generation",
            status=_normalize_status(row.status),
            progress=int(row.progress or 0),
            progress_message=row.progress_message or "",
            created_at=_format_timestamp(row.created_at),
            completed_at=_format_timestamp(row.completed_at),
            duration_seconds=_duration_seconds(row),
            payload=payload if include_detail else None,
            result=result if include_detail else None,
            diagnostics=_media_task_diagnostics(
                payload=payload,
                result=result,
                provider=row.provider or "",
                model=row.model or "",
                status=_normalize_status(row.status),
            ) if include_detail else None,
            error=row.error if include_detail else None,
        )
        infos.append(info)
    return infos


async def _model3d_task_infos(include_detail: bool = False) -> list[TaskInfo]:
    """Expose configured image-to-3D jobs in the shared task center."""
    try:
        async with get_async_session() as session:
            rows = (await session.execute(
                select(Model3DGenerationTask).order_by(Model3DGenerationTask.created_at.desc()).limit(100)
            )).scalars().all()
    except Exception as exc:
        logger.debug("Failed to collect 3D generation tasks: %s", exc)
        return []

    infos: list[TaskInfo] = []
    for row in rows:
        try:
            payload = json.loads(row.request_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        try:
            result = json.loads(row.result_json or "{}")
        except (TypeError, ValueError):
            result = {}
        infos.append(TaskInfo(
            task_id=row.task_id,
            task_type="model3d_generation",
            status=_normalize_status(row.status),
            progress=int(row.progress or 0),
            progress_message=row.progress_message or "",
            created_at=_format_timestamp(row.created_at),
            completed_at=_format_timestamp(row.completed_at),
            duration_seconds=_duration_seconds(row),
            payload=payload if include_detail else None,
            result=result if include_detail else None,
            diagnostics=_media_task_diagnostics(
                payload=payload,
                result=result,
                provider=row.provider or "",
                model=row.model or "",
                status=_normalize_status(row.status),
            ) if include_detail else None,
            error=row.error if include_detail else None,
        ))
    return infos


async def _cancel_persistent_media_task(task_id: str) -> TaskInfo | None:
    async with get_async_session() as session:
        for model, task_type in ((VideoGenerationTask, "video"), (Model3DGenerationTask, "model3d")):
            row = await session.get(model, task_id)
            if row is None:
                continue
            status = _normalize_status(row.status)
            if status in {"done", "failed", "cancelled"}:
                return None
            row.status = "cancelled"
            row.progress_message = "已取消"
            row.completed_at = datetime.now().timestamp()
            row.updated_at = datetime.now().timestamp()
            await session.commit()
            if task_type == "video":
                return next((item for item in await _video_task_infos(True) if item.task_id == task_id), None)
            return next((item for item in await _model3d_task_infos(True) if item.task_id == task_id), None)
    return None


async def _delete_persistent_media_task(task_id: str) -> TaskInfo | None:
    async with get_async_session() as session:
        for model, task_type in ((VideoGenerationTask, "video"), (Model3DGenerationTask, "model3d")):
            row = await session.get(model, task_id)
            if row is None:
                continue
            info_list = await (_video_task_infos(True) if task_type == "video" else _model3d_task_infos(True))
            info = next((item for item in info_list if item.task_id == task_id), None)
            await session.delete(row)
            await session.commit()
            return info
    return None


async def _require_persistent_task_access(task_id: str, principal: AuthenticatedPrincipal) -> None:
    """Apply ownership checks where the task has a durable owner record."""
    if not isinstance(principal, AuthenticatedPrincipal):
        # Internal direct route calls predate FastAPI dependency injection.
        # Their own service/tool authorization remains the boundary.
        return
    async with get_async_session() as session:
        for model in (VideoGenerationTask, Model3DGenerationTask):
            row = await session.get(model, task_id)
            if row is not None:
                require_owned_or_legacy(owner_user_id=row.owner_user_id, principal=principal)
                return


async def _visible_persistent_task_ids(
    principal: AuthenticatedPrincipal | None,
) -> set[str] | None:
    """Return the durable task ids a human session may read.

    ``None`` means an external Agent key, whose subject mapping is intentionally
    deferred to a separate migration and which remains governed by its key
    scope. Anonymous callers only receive pre-account legacy records.
    """
    # An explicit ``None`` is an anonymous HTTP caller and may only see legacy
    # NULL-owner records. A non-principal sentinel (direct Python call without
    # dependency resolution, i.e. the Depends default) keeps the historical
    # unfiltered internal behavior.
    if principal is None:
        owner_user_id = None
    elif not isinstance(principal, AuthenticatedPrincipal):
        return None
    elif principal.external_api_key is not None:
        return None
    else:
        owner_user_id = principal.user.id if principal.user else None
    async with get_async_session() as session:
        ids: set[str] = set()
        for model in (VideoGenerationTask, Model3DGenerationTask):
            statement = select(model.task_id).where(model.owner_user_id.is_(None))
            if owner_user_id is not None:
                statement = select(model.task_id).where(
                    or_(model.owner_user_id == owner_user_id, model.owner_user_id.is_(None))
                )
            ids.update((await session.execute(statement)).scalars().all())
        return ids


def _all_task_infos(
    include_detail: bool = False,
    video_infos: list[TaskInfo] | None = None,
    model3d_infos: list[TaskInfo] | None = None,
) -> list[TaskInfo]:
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

    for info in video_infos or []:
        if info.task_id not in seen:
            infos.append(info)
            seen.add(info.task_id)

    for info in model3d_infos or []:
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

    # Compare parsed instants rather than raw strings: ISO strings with and
    # without fractional seconds do not sort chronologically as text.
    infos.sort(
        key=lambda item: _parse_timestamp(item.created_at)
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
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
        asset_row = _asset_hub_download_row(asset_id)
        if asset_row:
            return _asset_hub_download_task_info(asset_row, include_detail=include_detail)
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


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _asset_hub_download_task_info(row: Any, include_detail: bool = False) -> TaskInfo:
    node_meta = _dict_value(getattr(row, "node_metadata", None))
    params = _dict_value(getattr(row, "params", None))
    lineage = _dict_value(getattr(row, "lineage", None))
    rep_extra = _dict_value(getattr(row, "rep_extra", None))

    source_url = (
        node_meta.get("source_url")
        or lineage.get("source_url")
        or params.get("source_url")
        or rep_extra.get("source_url")
        or ""
    )
    platform = (
        node_meta.get("platform")
        or lineage.get("platform")
        or params.get("platform")
        or ""
    )
    title = getattr(row, "name", "") or node_meta.get("title") or ""
    file_path = getattr(row, "file_path", "") or ""
    created_at = getattr(row, "created_at", None)
    completed_at = getattr(row, "updated_at", None) or created_at

    payload = {
        "source_url": source_url,
        "platform": platform,
        "title": title,
    }
    payload = {key: value for key, value in payload.items() if value}
    result = {
        "asset_id": getattr(row, "id", ""),
        "file_path": file_path,
    }
    result = {key: value for key, value in result.items() if value}
    timing = {"created_at": created_at, "completed_at": completed_at}

    return TaskInfo(
        task_id=_asset_download_task_id(getattr(row, "id", "")),
        task_type="download",
        status="done",
        progress=100,
        progress_message="下载完成，已入素材库",
        created_at=_format_timestamp(created_at),
        started_at=_format_timestamp(created_at),
        completed_at=_format_timestamp(completed_at),
        duration_seconds=_duration_seconds(timing),
        payload=payload if include_detail else None,
        result=result or None,
        error=None,
    )


def _asset_hub_download_source_predicate() -> str:
    return """
    (
        an.metadata_json ->> 'source_type' IN ('parse', 'download')
        OR an.metadata_json ->> 'source' IN ('parse', 'download')
        OR av.params_json ->> 'source_type' IN ('parse', 'download')
        OR av.params_json ->> 'source' IN ('parse', 'download')
        OR av.lineage_json ->> 'source' IN ('parse', 'download')
    )
    """


def _asset_hub_media_type_predicate() -> str:
    return """
    (
        ar.mime_type ILIKE 'video/%'
        OR ar.mime_type ILIKE 'audio/%'
        OR an.asset_type IN ('VIDEO', 'AUDIO')
    )
    """


def _asset_hub_download_row(asset_id: str) -> Any | None:
    try:
        from app.db.database import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text(
                    f"""
                    SELECT
                        an.id,
                        an.name,
                        an.metadata_json AS node_metadata,
                        an.created_at,
                        an.updated_at,
                        av.params_json AS params,
                        av.lineage_json AS lineage,
                        ar.file_path,
                        ar.extra_json AS rep_extra
                    FROM asset_nodes an
                    JOIN asset_versions av ON av.asset_node_id = an.id
                    JOIN asset_representations ar ON ar.asset_version_id = av.id
                    WHERE an.id = :asset_id
                      AND {_asset_hub_download_source_predicate()}
                      AND {_asset_hub_media_type_predicate()}
                      AND COALESCE(an.metadata_json ->> 'status', 'READY') <> 'DELETED'
                    ORDER BY av.version_number DESC, ar.file_size DESC
                    LIMIT 1
                    """
                ),
                {"asset_id": asset_id},
            ).mappings().first()
        return SimpleNamespace(**dict(row)) if row else None
    except Exception as exc:
        logger.debug("Failed to find Asset Hub download task %s: %s", asset_id, exc)
        return None


def _recent_asset_hub_download_rows(limit: int = 30) -> list[Any]:
    try:
        from app.db.database import SessionLocal

        with SessionLocal() as session:
            rows = (
                session.execute(
                    text(
                        f"""
                        SELECT *
                        FROM (
                            SELECT DISTINCT ON (an.id)
                                an.id,
                                an.name,
                                an.metadata_json AS node_metadata,
                                an.created_at,
                                an.updated_at,
                                av.params_json AS params,
                                av.lineage_json AS lineage,
                                ar.file_path,
                                ar.extra_json AS rep_extra
                            FROM asset_nodes an
                            JOIN asset_versions av ON av.asset_node_id = an.id
                            JOIN asset_representations ar ON ar.asset_version_id = av.id
                            WHERE {_asset_hub_download_source_predicate()}
                              AND {_asset_hub_media_type_predicate()}
                              AND COALESCE(an.metadata_json ->> 'status', 'READY') <> 'DELETED'
                            ORDER BY an.id, an.updated_at DESC, av.version_number DESC, ar.file_size DESC
                        ) recent_download_assets
                        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
                .mappings()
                .all()
            )
        return [SimpleNamespace(**dict(row)) for row in rows]
    except Exception as exc:
        logger.debug("Failed to collect recent Asset Hub download tasks: %s", exc)
        return []


def _recent_asset_download_infos(include_detail: bool = False, limit: int = 30) -> list[TaskInfo]:
    """Backfill completed download tasks from recent Asset Hub media assets."""
    return [
        _asset_hub_download_task_info(row, include_detail=include_detail)
        for row in _recent_asset_hub_download_rows(limit=limit)
    ]


@router.get("", response_model=TaskListResponse, summary="任务列表")
async def list_tasks(
    project_id: str | None = None,
    task_type: str | None = None,
    active_only: bool = False,
    include_detail: bool = False,
    principal: AuthenticatedPrincipal | None = Depends(get_authenticated_principal_optional),
):
    """
    返回所有活跃任务（内存视图）。
    当前聚合 core.task_queue 以及仍在迁移中的下载任务表。
    """
    await get_task_queue().restore_persisted_tasks(project_id=project_id, active_only=active_only)
    # Project filtering needs payload context even when callers did not ask to
    # return the payload in the response.
    detail = include_detail or bool(project_id)
    video_infos = await _video_task_infos(include_detail=detail)
    model3d_infos = await _model3d_task_infos(include_detail=detail)
    tasks = _all_task_infos(include_detail=detail, video_infos=video_infos, model3d_infos=model3d_infos)
    visible_persistent_ids = await _visible_persistent_task_ids(principal)
    if visible_persistent_ids is not None:
        tasks = [
            task for task in tasks
            if task.task_type not in {"video_generation", "model3d_generation"}
            or task.task_id in visible_persistent_ids
        ]
    if project_id:
        tasks = [
            task for task in tasks
            if isinstance(task.payload, dict) and str(task.payload.get("project_id") or "") == project_id
        ]
    if task_type:
        tasks = [task for task in tasks if task.task_type == task_type]
    if active_only:
        tasks = [task for task in tasks if task.status in {"pending", "running"}]
    if not include_detail:
        for task in tasks:
            task.payload = None
            task.result = None
            task.diagnostics = None
            task.events = None
            task.error = None
    return TaskListResponse(success=True, tasks=tasks)


@router.get("/stats", response_model=TaskStatsResponse, summary="任务统计")
async def get_task_stats(
    principal: AuthenticatedPrincipal | None = Depends(get_authenticated_principal_optional),
):
    """返回任务统计数据，用于 Dashboard"""
    tasks = _all_task_infos(
        video_infos=await _video_task_infos(),
        model3d_infos=await _model3d_task_infos(),
    )

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

    # Task timestamps are serialized with an explicit local offset (see
    # ``_format_timestamp``), so the day boundary must carry the same offset to
    # stay comparable instead of raising naive/aware TypeError.
    now_local = datetime.now().astimezone()
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
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
            created_date = _parse_timestamp(task.created_at)
            if created_date and created_date >= today_start:
                today_count += 1
            if created_date and created_date >= week_start:
                week_count += 1

        task_type = task.task_type.lower()
        if "3d" in task_type:
            images += 1
        elif "image" in task_type:
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
async def get_task_detail(
    task_id: str,
    principal: AuthenticatedPrincipal | None = Depends(get_authenticated_principal_optional),
):
    """返回指定任务的详细信息"""
    queue = get_task_queue()
    task = await queue.get_task(task_id)
    if task:
        return TaskDetailResponse(success=True, task=_task_info(task, include_detail=True))

    external_task = _find_external_task(task_id, include_detail=True)
    if external_task:
        return TaskDetailResponse(success=True, task=external_task)

    video_tasks = await _video_task_infos(include_detail=True)
    video_task = next((item for item in video_tasks if item.task_id == task_id), None)
    if video_task:
        visible_ids = await _visible_persistent_task_ids(principal)
        if visible_ids is not None and task_id not in visible_ids:
            raise HTTPException(status_code=403, detail="无权访问其他用户的资源")
        return TaskDetailResponse(success=True, task=video_task)

    model3d_tasks = await _model3d_task_infos(include_detail=True)
    model3d_task = next((item for item in model3d_tasks if item.task_id == task_id), None)
    if model3d_task:
        visible_ids = await _visible_persistent_task_ids(principal)
        if visible_ids is not None and task_id not in visible_ids:
            raise HTTPException(status_code=403, detail="无权访问其他用户的资源")
        return TaskDetailResponse(success=True, task=model3d_task)

    return TaskDetailResponse(success=False, task=None)


@router.post("/{task_id}/cancel", response_model=TaskActionResponse, summary="取消任务")
async def cancel_task(
    task_id: str, principal: AuthenticatedPrincipal = Depends(get_authenticated_principal)
):
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

    await _require_persistent_task_access(task_id, principal)
    persistent_task = await _cancel_persistent_media_task(task_id)
    if persistent_task:
        return TaskActionResponse(success=True, message="任务已取消", task=persistent_task)

    for info in [*(await _video_task_infos(True)), *(await _model3d_task_infos(True))]:
        if info.task_id == task_id:
            return TaskActionResponse(
                success=False,
                message=f"任务已处于 {info.status} 状态，无法取消",
                task=info,
            )

    raise HTTPException(status_code=404, detail="任务不存在")


class TaskRetryResponse(BaseModel):
    success: bool = True
    message: str = ""
    task_type: str = ""
    task_id: str | None = None  # 重试产生的新任务 id
    url: str | None = None
    asset_id: str | None = None
    error: str | None = None


def _load_json(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


@router.post("/{task_id}/retry", response_model=TaskRetryResponse, summary="重试失败任务")
async def retry_task(
    task_id: str, principal: AuthenticatedPrincipal = Depends(get_authenticated_principal)
):
    """按原参数重新提交失败或取消的独立媒体任务。

    统一入口：任务中心看到失败任务即可重试，不必再去事件日志 Tab 找对应事件。
    视频与图转 3D 的完整可重放参数保存在各自任务账本的 `request_json`；
    重试直接复用各自的生成端点，因此资产入库、项目关联、事件与任务记录的行为
    与用户手动重新生成完全一致（会生成一条新任务，原任务保留可追溯）。
    图片类任务的重发在事件日志（`/api/v1/logs/{id}/retry`）已支持。
    """
    # 先按 task_type 判断（通用队列任务 id 是 uuid，前缀不可靠）；外部账本再按前缀兜底。
    await _require_persistent_task_access(task_id, principal)
    queue = get_task_queue()
    tracked = await queue.get_task(task_id)
    task_type = str(getattr(tracked, "task_type", "") or "")
    if not task_type:
        if task_id.startswith("video_"):
            task_type = "video_generation"
        elif task_id.startswith("model3d_"):
            task_type = "model3d_generation"
        elif task_id.startswith("image_"):
            task_type = "image_generation"

    if task_type == "video_generation":
        from app.api.v1.videos import VideoGenerateRequest, generate_video

        async with get_async_session() as session:
            row = await session.get(VideoGenerationTask, task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="视频任务不存在")
        ctx = _load_json(row.request_json)
        request = VideoGenerateRequest(
            prompt=row.prompt or ctx.get("prompt") or "",
            duration=ctx.get("duration") or 5,
            resolution=ctx.get("resolution") or "720p",
            aspect_ratio=ctx.get("aspect_ratio") or "9:16",
            provider=row.provider or None,
            model=row.model or None,
            seed=ctx.get("seed"),
            generate_audio=ctx.get("generate_audio", True),
            music_hint=ctx.get("music_hint") or None,
            reference_asset_ids=ctx.get("reference_asset_ids") or [],
            project_id=ctx.get("project_id") or None,
            content_id=ctx.get("content_id") or None,
            chapter_number=ctx.get("chapter_number"),
            source_type=ctx.get("source_type") or None,
            source_index=ctx.get("source_index") or None,
            source_title=ctx.get("source_title") or None,
            production_plan_id=ctx.get("production_plan_id") or None,
            production_node_id=ctx.get("production_node_id") or None,
            planning_summary=ctx.get("planning_summary") or {},
        )
        response = await generate_video(request, principal=principal)
        ok = bool(getattr(response, "success", False))
        return TaskRetryResponse(
            success=ok,
            message="已重新提交视频生成" if ok else "重试失败",
            task_type="video_generation",
            task_id=getattr(response, "task_id", None),
            url=getattr(response, "url", None),
            asset_id=getattr(response, "asset_id", None) or None,
            error=None if ok else (getattr(response, "error", None) or "视频生成失败"),
        )

    if task_type == "model3d_generation":
        from app.api.v1.model3d_workspace import Model3DGenerateRequest, generate_model3d

        async with get_async_session() as session:
            row = await session.get(Model3DGenerationTask, task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="图转 3D 任务不存在")
        if (row.kind or "generation") != "generation":
            return TaskRetryResponse(
                success=False,
                message="绑骨任务请在工作台重新发起（暂不支持一键重试）",
                task_type="model3d_generation",
            )
        ctx = _load_json(row.request_json)
        request = Model3DGenerateRequest(
            prompt=row.prompt or ctx.get("title") or "",
            provider=row.provider or "",
            model=row.model or "",
            source_asset_id=ctx.get("source_asset_id"),
            options=ctx.get("options") or {},
        )
        response = await generate_model3d(request, principal=principal)
        ok = bool(getattr(response, "success", False))
        return TaskRetryResponse(
            success=ok,
            message="已重新提交图转 3D" if ok else "重试失败",
            task_type="model3d_generation",
            task_id=getattr(response, "task_id", None),
            url=getattr(response, "url", None),
            asset_id=getattr(response, "asset_id", None) or None,
            error=None if ok else (getattr(response, "error", None) or "图转 3D 失败"),
        )

    if task_type == "image_generation":
        return TaskRetryResponse(
            success=False,
            message="图片任务请在「事件日志」Tab 对失败事件点「重发」（那里保留了完整的可重放参数）",
            task_type="image_generation",
        )

    return TaskRetryResponse(
        success=False,
        message="该任务类型暂不支持一键重试，请在对应工作台重新发起",
    )


@router.delete("/{task_id}", response_model=TaskActionResponse, summary="删除任务")
async def delete_task(
    task_id: str, principal: AuthenticatedPrincipal = Depends(get_authenticated_principal)
):
    """从当前内存任务视图中删除任务。"""
    await _require_persistent_task_access(task_id, principal)
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

    persistent_task = await _delete_persistent_media_task(task_id)
    if persistent_task:
        return TaskActionResponse(success=True, message="任务已删除", task=persistent_task)

    raise HTTPException(status_code=404, detail="任务不存在")
