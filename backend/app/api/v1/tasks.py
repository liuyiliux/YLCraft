"""
YLCraft — 任务队列管理 API

GET  /api/v1/tasks       — 所有任务列表（简单聚合视图）
GET  /api/v1/tasks/:id   — 单个任务详情
GET  /api/v1/tasks/stats — 统计概览数据
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

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
    created_at: str | None = None


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
            created = None
            if hasattr(task, "created_at"):
                created = task.created_at.isoformat() if hasattr(task.created_at, "isoformat") else str(task.created_at)
            tasks.append(TaskInfo(
                task_id=task.task_id,
                task_type=task.task_type,
                status=task.status.value if hasattr(task.status, "value") else str(task.status),
                progress=task.progress,
                progress_message=task.progress_message,
                created_at=created,
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


@router.get("/stats", response_model=TaskStatsResponse, summary="任务统计")
async def get_task_stats():
    """返回任务统计数据，用于 Dashboard"""
    queue = get_task_queue()
    tasks = queue._tasks if hasattr(queue, "_tasks") else {}

    # 统计各状态数量
    total = len(tasks)
    completed = 0
    pending = 0
    running = 0
    failed = 0

    # 按类型统计
    images = 0
    videos = 0
    characters = 0
    stories = 0

    # 时间统计
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())

    today_count = 0
    week_count = 0

    for task_id, task in tasks.items():
        status = task.status.value if hasattr(task.status, "value") else str(task.status)

        # 状态统计
        if status == "completed":
            completed += 1
        elif status == "pending":
            pending += 1
        elif status == "running":
            running += 1
        elif status == "failed":
            failed += 1

        # 类型统计
        task_type = task.task_type.lower()
        if "image" in task_type:
            images += 1
        elif "video" in task_type:
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
