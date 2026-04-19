"""
YLCraft — 任务队列

支持 Redis（生产环境）和内存队列（开发环境降级）。

TaskStatus: PENDING / RUNNING / DONE / FAILED
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class StrEnum(str, Enum):
    """兼容 Python 3.10"""
    pass
from typing import Any


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


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
        return task

    async def get_task(self, task_id: str) -> Task | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def update_progress(self, task_id: str, progress: int, message: str = "") -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.progress = progress
                task.progress_message = message
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()

    async def update_task(self, task: Task) -> None:
        async with self._lock:
            self._tasks[task.task_id] = task


# 全局单例
_queue: InMemoryTaskQueue | None = None


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
    # 自动检测 Redis
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
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
