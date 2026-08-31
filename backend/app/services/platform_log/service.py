"""Unified platform event log service.

Provides a single `record_event` entrypoint used by every AI generation call site
(image / video / model3d / llm) to persist a structured success/failed/pending event,
with sensitive-field redaction and length truncation reused from `app.core.task_queue`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

from sqlalchemy import select

from app.core.task_queue import _sanitize_event_value
from app.db.database import get_async_session
from app.db.models.platform_log import PlatformEventLog

logger = logging.getLogger("ylcraft.platform_log")

MAX_SUMMARY_LENGTH = 1000


def _truncate(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > MAX_SUMMARY_LENGTH:
        return text[:MAX_SUMMARY_LENGTH] + "...(truncated)"
    return text


def _sanitize_payload(payload: Any) -> dict[str, Any]:
    """Redact a retry payload but keep full business fields (prompt/messages/lineage)."""
    if payload is None:
        return {}
    sanitized = _sanitize_event_value(payload)
    return sanitized if isinstance(sanitized, dict) else {"value": sanitized}


async def record_event(
    *,
    scene: str,
    task_type: str = "",
    task_id: Optional[str] = None,
    level: str = "info",
    status: str = "success",
    provider: str = "",
    model: str = "",
    message: str = "",
    error: Optional[str] = None,
    request: Any = None,
    response: Any = None,
    duration_ms: int = 0,
    project_id: Optional[str] = None,
    ref_id: Optional[str] = None,
    retry_payload: Any = None,
    retry_of: Optional[str] = None,
) -> Optional[str]:
    """Persist one platform event and return its id (or None if persistence failed)."""
    event_id = f"log_{uuid.uuid4().hex}"
    record = PlatformEventLog(
        id=event_id,
        scene=scene,
        task_type=task_type,
        ref_id=ref_id,
        task_id=task_id,
        level=level,
        status=status,
        provider=provider,
        model=model,
        message=message,
        error=_truncate(error) if error else None,
        request_summary=_truncate(request) if request is not None else "",
        response_summary=_truncate(response) if response is not None else "",
        duration_ms=int(duration_ms or 0),
        project_id=project_id,
        retry_payload_json=json.dumps(
            _sanitize_payload(retry_payload), ensure_ascii=False, default=str
        )
        if retry_payload
        else "{}",
        retry_of=retry_of,
        created_at=time.time(),
    )
    try:
        async with get_async_session() as session:
            session.add(record)
        return event_id
    except Exception as exc:  # best-effort; logging must never break the main flow
        logger.warning("Could not persist platform event %s: %s", event_id, exc)
        return None


async def list_events(
    *,
    scene: Optional[str] = None,
    level: Optional[str] = None,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    project_id: Optional[str] = None,
    ref_id: Optional[str] = None,
    q: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Return (page items, total) with the given filters, newest first."""
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    try:
        async with get_async_session() as session:
            query = select(PlatformEventLog)
            if scene:
                query = query.where(PlatformEventLog.scene == scene)
            if level:
                query = query.where(PlatformEventLog.level == level)
            if status:
                query = query.where(PlatformEventLog.status == status)
            if task_type:
                query = query.where(PlatformEventLog.task_type == task_type)
            if project_id:
                query = query.where(PlatformEventLog.project_id == project_id)
            if ref_id:
                query = query.where(PlatformEventLog.ref_id == ref_id)
            if since is not None:
                query = query.where(PlatformEventLog.created_at >= since)
            if until is not None:
                query = query.where(PlatformEventLog.created_at <= until)
            if q:
                pattern = f"%{q}%"
                query = query.where(
                    (PlatformEventLog.message.ilike(pattern))
                    | (PlatformEventLog.error.ilike(pattern))
                )
            total = len((await session.scalars(query)).all())
            rows = (
                await session.scalars(
                    query.order_by(PlatformEventLog.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return [_event_to_dict(row, include_summary=False) for row in rows], total
    except Exception as exc:
        logger.debug("Could not list platform events: %s", exc)
        return [], 0


async def get_event(event_id: str) -> dict[str, Any] | None:
    try:
        async with get_async_session() as session:
            row = await session.get(PlatformEventLog, event_id)
            if row is None:
                return None
            return _event_to_dict(row, include_summary=True)
    except Exception as exc:
        logger.debug("Could not load platform event %s: %s", event_id, exc)
        return None


async def link_retried_by(original_id: str, new_id: str) -> None:
    try:
        async with get_async_session() as session:
            row = await session.get(PlatformEventLog, original_id)
            if row is not None:
                row.retried_by = new_id
    except Exception as exc:
        logger.warning("Could not link retried_by for %s: %s", original_id, exc)


def _event_to_dict(row: PlatformEventLog, *, include_summary: bool) -> dict[str, Any]:
    result = {
        "id": row.id,
        "scene": row.scene,
        "task_type": row.task_type,
        "task_id": row.task_id,
        "level": row.level,
        "status": row.status,
        "provider": row.provider,
        "model": row.model,
        "message": row.message,
        "error": row.error,
        "duration_ms": row.duration_ms,
        "project_id": row.project_id,
        "ref_id": row.ref_id,
        "retry_of": row.retry_of,
        "retried_by": row.retried_by,
        "created_at": row.created_at,
    }
    if include_summary:
        result["request_summary"] = row.request_summary
        result["response_summary"] = row.response_summary
        result["retry_payload"] = json.loads(row.retry_payload_json or "{}")
    return result
