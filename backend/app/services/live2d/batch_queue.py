"""
YLCraft — 批量处理队列服务

支持多个 Live2D 模型同时处理，自动排队。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from uuid import uuid4


class QueueStatus(str, Enum):
    """队列状态"""
    PENDING = "pending"      # 等待中
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled" # 已取消


@dataclass
class QueueItem:
    """队列项"""
    id: str
    model_id: str
    model_name: str
    action: str  # pipeline, segment, rig, etc.
    status: QueueStatus = QueueStatus.PENDING
    progress: int = 0
    message: str = ""
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None


@dataclass
class BatchQueue:
    """批量处理队列"""
    id: str
    name: str
    items: List[QueueItem] = field(default_factory=list)
    status: QueueStatus = QueueStatus.PENDING
    total: int = 0
    completed: int = 0
    failed: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class BatchQueueManager:
    """
    批量处理队列管理器

    使用内存存储队列，支持：
    - 创建批量处理任务
    - 添加模型到队列
    - 执行队列
    - 取消队列
    - 查询状态
    """

    def __init__(self, max_concurrent: int = 2):
        self.max_concurrent = max_concurrent
        self._queues: Dict[str, BatchQueue] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._progress_callbacks: Dict[str, Callable] = {}

    def create_queue(self, name: str, model_ids: List[str], action: str = "pipeline") -> BatchQueue:
        """
        创建批量处理队列

        Args:
            name: 队列名称
            model_ids: 模型 ID 列表
            action: 执行的动作

        Returns:
            队列对象
        """
        queue_id = uuid4().hex

        items = [
            QueueItem(
                id=uuid4().hex,
                model_id=model_id,
                model_name=f"Model_{model_id[:8]}",
                action=action,
            )
            for model_id in model_ids
        ]

        queue = BatchQueue(
            id=queue_id,
            name=name,
            items=items,
            total=len(items),
        )

        self._queues[queue_id] = queue
        return queue

    def get_queue(self, queue_id: str) -> Optional[BatchQueue]:
        """获取队列"""
        return self._queues.get(queue_id)

    def get_all_queues(self) -> List[BatchQueue]:
        """获取所有队列"""
        return list(self._queues.values())

    def cancel_queue(self, queue_id: str) -> bool:
        """
        取消队列

        Args:
            queue_id: 队列 ID

        Returns:
            是否成功取消
        """
        queue = self._queues.get(queue_id)
        if not queue:
            return False

        # 取消正在运行的任务
        if queue_id in self._running_tasks:
            task = self._running_tasks[queue_id]
            task.cancel()
            del self._running_tasks[queue_id]

        # 更新队列状态
        queue.status = QueueStatus.CANCELLED

        # 标记未完成的项目为取消
        for item in queue.items:
            if item.status == QueueStatus.PENDING:
                item.status = QueueStatus.CANCELLED

        return True

    def get_queue_stats(self, queue_id: str) -> Optional[Dict[str, Any]]:
        """获取队列统计"""
        queue = self._queues.get(queue_id)
        if not queue:
            return None

        return {
            "id": queue.id,
            "name": queue.name,
            "status": queue.status.value,
            "total": queue.total,
            "completed": queue.completed,
            "failed": queue.failed,
            "pending": sum(1 for i in queue.items if i.status == QueueStatus.PENDING),
            "running": sum(1 for i in queue.items if i.status == QueueStatus.RUNNING),
            "progress": int(queue.completed / queue.total * 100) if queue.total > 0 else 0,
        }

    def update_item_progress(self, queue_id: str, item_id: str, progress: int, message: str):
        """更新项目进度"""
        queue = self._queues.get(queue_id)
        if not queue:
            return

        for item in queue.items:
            if item.id == item_id:
                item.progress = progress
                item.message = message
                break

        # 调用进度回调
        if queue_id in self._progress_callbacks:
            self._progress_callbacks[queue_id](queue_id, item_id, progress, message)

    def update_item_status(
        self,
        queue_id: str,
        item_id: str,
        status: QueueStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """更新项目状态"""
        queue = self._queues.get(queue_id)
        if not queue:
            return

        for item in queue.items:
            if item.id == item_id:
                item.status = status
                item.result = result
                item.error = error

                if status == QueueStatus.RUNNING and not item.started_at:
                    item.started_at = datetime.now()
                elif status in [QueueStatus.COMPLETED, QueueStatus.FAILED, QueueStatus.CANCELLED]:
                    item.completed_at = datetime.now()

        # 更新队列统计
        queue.completed = sum(1 for i in queue.items if i.status == QueueStatus.COMPLETED)
        queue.failed = sum(1 for i in queue.items if i.status == QueueStatus.FAILED)

        # 检查是否全部完成
        if queue.completed + queue.failed + sum(1 for i in queue.items if i.status == QueueStatus.CANCELLED) == queue.total:
            queue.status = QueueStatus.COMPLETED
            queue.completed_at = datetime.now()

    def set_progress_callback(self, queue_id: str, callback: Callable):
        """设置进度回调"""
        self._progress_callbacks[queue_id] = callback

    def remove_progress_callback(self, queue_id: str):
        """移除进度回调"""
        if queue_id in self._progress_callbacks:
            del self._progress_callbacks[queue_id]


# 全局队列管理器实例
_batch_queue_manager: Optional[BatchQueueManager] = None


def get_batch_queue_manager() -> BatchQueueManager:
    """获取全局批量处理队列管理器"""
    global _batch_queue_manager
    if _batch_queue_manager is None:
        _batch_queue_manager = BatchQueueManager(max_concurrent=2)
    return _batch_queue_manager


def create_batch_queue(name: str, model_ids: List[str], action: str = "pipeline") -> BatchQueue:
    """便捷函数：创建批量处理队列"""
    manager = get_batch_queue_manager()
    return manager.create_queue(name, model_ids, action)


def get_batch_queue(queue_id: str) -> Optional[BatchQueue]:
    """便捷函数：获取队列"""
    manager = get_batch_queue_manager()
    return manager.get_queue(queue_id)


def cancel_batch_queue(queue_id: str) -> bool:
    """便捷函数：取消队列"""
    manager = get_batch_queue_manager()
    return manager.cancel_queue(queue_id)


__all__ = [
    "QueueStatus",
    "QueueItem",
    "BatchQueue",
    "BatchQueueManager",
    "get_batch_queue_manager",
    "create_batch_queue",
    "get_batch_queue",
    "cancel_batch_queue",
]
