"""
YLCraft — 任务队列

支持 Redis（生产环境）和内存队列（开发环境降级）。

TaskStatus: PENDING / RUNNING / DONE / FAILED
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StrEnum(str, Enum):
    """兼容 Python 3.10"""
    pass
MAX_TASK_EVENTS = 100
MAX_EVENT_STRING_LENGTH = 1000
SENSITIVE_KEYS = {"authorization", "api_key", "apikey", "token", "access_token", "secret", "password"}


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class TaskEvent:
    event_id: str
    type: str
    message: str
    level: str = "info"
    data: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class Task:
    task_id: str
    task_type: str
    payload: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    progress_message: str = ""
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    max_retries: int = 2
    events: list[TaskEvent] = field(default_factory=list)


def _sanitize_event_value(value: Any):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                sanitized[key] = "***"
            else:
                sanitized[key] = _sanitize_event_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_event_value(item) for item in value[:50]]
    if isinstance(value, str):
        if value.startswith("data:image") or len(value) > MAX_EVENT_STRING_LENGTH:
            return value[:MAX_EVENT_STRING_LENGTH] + "...(truncated)"
        return value
    return value


def task_event_to_dict(event: TaskEvent) -> dict:
    return asdict(event)


class InMemoryTaskQueue:
    """内存任务队列（开发/无Redis环境用）"""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, task_type: str, payload: dict, max_retries: int = 2) -> Task:
        task_id = str(uuid.uuid4())[:12]
        task = Task(task_id=task_id, task_type=task_type, payload=payload, max_retries=max_retries)
        async with self._lock:
            self._tasks[task_id] = task
        await self._persist(task)

        # WebSocket 实时推送新任务创建
        try:
            from app.core.ws_manager import push_task_created
            await push_task_created(task_id=task_id, task_type=task_type, payload=payload)
        except Exception:
            pass

        return task

    async def get_task(self, task_id: str) -> Task | None:
        async with self._lock:
            task = self._tasks.get(task_id)
        if task is not None:
            return task
        return await self._restore_task(task_id)

    async def update_progress(self, task_id: str, progress: int, message: str = "") -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.progress = progress
                task.progress_message = message
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()
        if task:
            await self._persist(task)

        # WebSocket 实时推送进度
        try:
            from app.core.ws_manager import push_task_progress
            t = self._tasks.get(task_id)
            await push_task_progress(
                task_id=task_id,
                progress=progress,
                message=message,
                task_type=t.task_type if t else "",
                status=t.status.value if t and hasattr(t.status, "value") else "",
            )
        except Exception:
            pass  # WS 推送失败不影响主流程

    async def update_task(self, task: Task) -> None:
        async with self._lock:
            self._tasks[task.task_id] = task
        await self._persist(task)

        # WebSocket 实时推送任务状态变更
        try:
            from app.core.ws_manager import push_task_progress
            await push_task_progress(
                task_id=task.task_id,
                progress=task.progress,
                message=task.progress_message,
                task_type=task.task_type,
                status=task.status.value if hasattr(task.status, "value") else str(task.status),
            )
        except Exception:
            pass

    async def append_event(
        self,
        task_id: str,
        type: str,
        message: str,
        level: str = "info",
        data: dict | None = None,
    ) -> TaskEvent | None:
        event = TaskEvent(
            event_id=str(uuid.uuid4())[:12],
            type=type,
            message=message,
            level=level,
            data=_sanitize_event_value(data or {}),
        )
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.events.append(event)
            if len(task.events) > MAX_TASK_EVENTS:
                task.events = task.events[-MAX_TASK_EVENTS:]

        try:
            from app.core.ws_manager import push_task_progress
            task = self._tasks.get(task_id)
            await push_task_progress(
                task_id=task_id,
                progress=task.progress if task else 0,
                message=message,
                task_type=task.task_type if task else "",
                status=task.status.value if task and hasattr(task.status, "value") else "",
            )
        except Exception:
            pass
        return event

    async def update_diagnostics(self, task_id: str, **fields) -> dict | None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            payload = task.payload or {}
            diagnostics = payload.get("diagnostics")
            if not isinstance(diagnostics, dict):
                diagnostics = {}
            diagnostics.update(_sanitize_event_value(fields))
            payload["diagnostics"] = diagnostics
            task.payload = payload
        if task:
            await self._persist(task)
            return diagnostics
        return None

    async def restore_persisted_tasks(self, *, project_id: str | None = None, active_only: bool = False) -> None:
        """Hydrate durable project tasks into the in-memory execution cache."""
        try:
            from app.services.task_persistence import list_tasks

            records = await list_tasks(project_id=project_id, active_only=active_only)
        except Exception:
            return
        for record in records:
            await self._restore_record(record)

    async def _restore_task(self, task_id: str) -> Task | None:
        try:
            from app.services.task_persistence import get_task

            record = await get_task(task_id)
        except Exception:
            return None
        return await self._restore_record(record) if record else None

    async def _restore_record(self, record: dict[str, Any] | None) -> Task | None:
        if not record:
            return None
        try:
            status = TaskStatus(str(record.get("status") or TaskStatus.PENDING.value))
        except ValueError:
            status = TaskStatus.PENDING
        events = []
        for item in record.get("events") or []:
            if isinstance(item, dict):
                try:
                    events.append(TaskEvent(**item))
                except TypeError:
                    continue
        task = Task(
            task_id=str(record.get("task_id") or ""),
            task_type=str(record.get("task_type") or ""),
            payload=record.get("payload") if isinstance(record.get("payload"), dict) else {},
            status=status,
            progress=int(record.get("progress") or 0),
            progress_message=str(record.get("progress_message") or ""),
            result=record.get("result") if isinstance(record.get("result"), dict) else None,
            error=record.get("error"),
            created_at=float(record.get("created_at") or time.time()),
            started_at=record.get("started_at"),
            completed_at=record.get("completed_at"),
            max_retries=int(record.get("max_retries") or 0),
            events=events,
        )
        if not task.task_id:
            return None
        async with self._lock:
            existing = self._tasks.get(task.task_id)
            if existing is not None:
                return existing
            self._tasks[task.task_id] = task
        return task

    async def _persist(self, task: Task) -> None:
        try:
            from app.services.task_persistence import upsert_task

            await upsert_task(task)
        except Exception:
            # Persistence must never interrupt the in-memory task workflow.
            pass


# 全局单例
_queue: InMemoryTaskQueue | None = None


def _parse_redis_url() -> dict:
    """解析 REDIS_URL 环境变量，返回 {host, port, password}"""
    import os
    from urllib.parse import urlparse

    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 6379,
        "password": parsed.password or None,
    }


def get_queue_mode() -> str:
    """
    返回当前队列运行模式。
    - "redis"：Redis 队列（生产环境）
    - "memory"：内存队列（开发/无 Redis 环境）
    检测逻辑：优先检测环境变量 YLCRAFT_QUEUE_MODE > 自动检测 Redis 可用性
    """
    import os
    mode = os.environ.get("YLCRAFT_QUEUE_MODE", "")
    if mode in ("redis", "memory"):
        return mode
    # 自动检测 Redis（从 REDIS_URL 读取连接信息）
    try:
        import redis
        cfg = _parse_redis_url()
        r = redis.Redis(
            host=cfg["host"],
            port=cfg["port"],
            password=cfg["password"],
            socket_connect_timeout=3,
        )
        r.ping()
        return "redis"
    except Exception:
        return "memory"


def init_task_queue(use_redis: bool = False) -> None:
    """初始化任务队列（强制指定模式）"""
    global _queue
    _queue = InMemoryTaskQueue()


def get_task_queue() -> InMemoryTaskQueue:
    """获取任务队列单例（当前使用内存队列）"""
    global _queue
    if _queue is None:
        _queue = InMemoryTaskQueue()
    return _queue
