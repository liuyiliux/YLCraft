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


#: 需要持久化的任务类型：项目级生成工作（进程重启后仍可在任务中心看到并恢复轮询）。
#: ``world_domain_expansion`` 为 AI 渐进世界构建的域级细化（异步，按 task_id 轮询）；
#: ``world_map_visual`` 为世界地图 AI 视觉成图（同步长任务，失败需要留痕）。
PERSISTED_TASK_TYPES = {
    "image_generation",
    "creative_writing",
    "world_domain_expansion",
    "world_map_visual",
}

#: 不挂项目、但仍需留痕的任务类型。这类任务没有 project_id（小说下载属于
#: 书架资产，不归属创作项目），若也要求 project_id 就永远落不了库：
#: 进程一重启任务即从任务中心消失，用户看不到下载结果与失败原因。
PERSISTED_STANDALONE_TASK_TYPES = frozenset({"novel_download", "live2d_processing"})


def should_persist(task_type: str, payload: dict[str, Any] | None) -> bool:
    """Persist project-scoped generation work, not transient UI-only tasks.

    不落库时说明原因：此前静默返回 False，新增任务类型忘了登记白名单
    （或忘了带 project_id）时表现为"任务凭空消失"，无从排查。
    """
    if task_type in PERSISTED_STANDALONE_TASK_TYPES:
        return True
    if task_type not in PERSISTED_TASK_TYPES:
        logger.info(
            "任务类型 %s 不在持久化白名单内，只存内存（重启即失）；"
            "确需持久化请登记 PERSISTED_TASK_TYPES",
            task_type,
        )
        return False
    if not bool((payload or {}).get("project_id")):
        logger.info(
            "任务 %s 缺少 project_id，只存内存（重启即失）；建任务时请带上项目归属",
            task_type,
        )
        return False
    return True


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
            # This private field is injected by authenticated route handlers,
            # never accepted from a client request body.
            record.owner_user_id = str(payload.get("_owner_user_id") or "") or None
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
