"""Best-effort persistence for resumable project task records."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy import select

from app.db.database import get_async_session
from app.db.models.task import ProjectTaskRecord

logger = logging.getLogger("ylcraft.task_persistence")


def _json(value: Any, fallback: str) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return fallback


def _from_json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def should_persist(task_type: str, payload: dict[str, Any] | None) -> bool:
    """Persist only project-scoped async image work, not every transient task."""
    return task_type == "image_generation" and bool((payload or {}).get("project_id"))


async def upsert_task(task: Any) -> None:
    payload = task.payload or {}
    if not should_persist(str(task.task_type), payload):
        return
    try:
        async with get_async_session() as session:
            record = await session.get(ProjectTaskRecord, task.task_id)
            if record is None:
                record = ProjectTaskRecord(task_id=task.task_id)
                session.add(record)
            record.task_type = str(task.task_type)
            record.status = getattr(task.status, "value", str(task.status))
            record.payload_json = _json(payload, "{}")
            record.result_json = _json(task.result or {}, "{}")
            record.error = task.error
            record.progress = int(task.progress or 0)
            record.progress_message = task.progress_message or ""
            record.created_at = float(task.created_at)
            record.started_at = task.started_at
            record.completed_at = task.completed_at
            record.max_retries = int(task.max_retries or 0)
            record.events_json = _json(
                [event.__dict__ for event in (task.events or [])],
                "[]",
            )
            record.updated_at = time.time()
    except Exception as exc:
        logger.warning("Could not persist project task %s: %s", getattr(task, "task_id", ""), exc)


async def get_task(task_id: str) -> dict[str, Any] | None:
    try:
        async with get_async_session() as session:
            record = await session.get(ProjectTaskRecord, task_id)
            if record is None:
                return None
            return _record_to_dict(record)
    except Exception as exc:
        logger.debug("Could not load project task %s: %s", task_id, exc)
        return None


async def list_tasks(*, project_id: str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
    try:
        async with get_async_session() as session:
            rows = list((await session.exec(select(ProjectTaskRecord))).all())
            records = [_record_to_dict(row) for row in rows]
        if project_id:
            records = [
                item for item in records
                if str((item.get("payload") or {}).get("project_id") or "") == project_id
            ]
        if active_only:
            records = [item for item in records if item.get("status") in {"pending", "running"}]
        return records
    except Exception as exc:
        logger.debug("Could not list project tasks: %s", exc)
        return []


def _record_to_dict(record: ProjectTaskRecord) -> dict[str, Any]:
    return {
        "task_id": record.task_id,
        "task_type": record.task_type,
        "status": record.status,
        "payload": _from_json(record.payload_json, {}),
        "result": _from_json(record.result_json, {}),
        "error": record.error,
        "progress": record.progress,
        "progress_message": record.progress_message,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "max_retries": record.max_retries,
        "events": _from_json(record.events_json, []),
    }
