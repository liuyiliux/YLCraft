"""
YLCraft — 任务队列管理 API

GET  /api/v1/tasks       — 所有任务列表（简单聚合视图）
GET  /api/v1/tasks/:id   — 单个任务详情
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.task_queue import get_task_queue

router = APIRouter()
logger = logging.getLogger("ylcraft.tasks")


class TaskInfo(BaseModel):
    task_id: str
    task_type: str
    status: str
    progress: int
    progress_message: str


class TaskListResponse(BaseModel):
    success: bool = True
    tasks: list[TaskInfo]


class TaskDetailResponse(BaseModel):
    success: bool = True
    task: TaskInfo | None = None


@router.get("", response_model=TaskListResponse, summary="任务列表")
async def list_tasks():
    """
    返回所有活跃任务（内存视图）。
    注意：InMemoryTaskQueue 不支持跨进程枚举，这里只返回内存中的任务。
    """
    queue = get_task_queue()
    tasks = []
    if hasattr(queue, "_tasks"):
        for task_id, task in queue._tasks.items():
            tasks.append(TaskInfo(
                task_id=task.task_id,
                task_type=task.task_type,
                status=task.status.value if hasattr(task.status, "value") else str(task.status),
                progress=task.progress,
                progress_message=task.progress_message,
            ))
    return TaskListResponse(success=True, tasks=tasks)


@router.get("/{task_id}", response_model=TaskDetailResponse, summary="任务详情")
async def get_task_detail(task_id: str):
    """返回指定任务的详细信息"""
    queue = get_task_queue()
    task = await queue.get_task(task_id)
    if not task:
        return TaskDetailResponse(success=False, task=None)
    return TaskDetailResponse(
        success=True,
        task=TaskInfo(
            task_id=task.task_id,
            task_type=task.task_type,
            status=task.status.value if hasattr(task.status, "value") else str(task.status),
            progress=task.progress,
            progress_message=task.progress_message,
        ),
    )
