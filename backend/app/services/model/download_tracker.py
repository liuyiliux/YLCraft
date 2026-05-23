"""
YLCraft — 下载进度跟踪服务

提供下载任务的进度查询和管理功能。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger("ylcraft.download_progress")


class DownloadStatus(str, Enum):
    """下载状态枚举"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadTask:
    """下载任务"""
    
    def __init__(
        self,
        task_id: str,
        model_id: str,
        version_id: Optional[str] = None,
        filename: Optional[str] = None,
    ):
        self.task_id = task_id
        self.model_id = model_id
        self.version_id = version_id
        self.filename = filename
        self.status = DownloadStatus.PENDING
        self.progress = 0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.download_speed = 0  # bytes/s
        self.error_message: Optional[str] = None
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None


class DownloadProgressTracker:
    """下载进度跟踪器"""
    
    _instance: Optional["DownloadProgressTracker"] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks: Dict[str, DownloadTask] = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance
    
    @classmethod
    async def get_instance(cls) -> "DownloadProgressTracker":
        """获取单例实例"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    async def create_task(
        self,
        task_id: str,
        model_id: str,
        version_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> DownloadTask:
        """创建下载任务"""
        task = DownloadTask(
            task_id=task_id,
            model_id=model_id,
            version_id=version_id,
            filename=filename,
        )
        
        async with self._lock:
            self._tasks[task_id] = task
        
        logger.info(f"[DownloadProgress] Created task {task_id} for model {model_id}")
        return task
    
    async def update_progress(
        self,
        task_id: str,
        progress: int,
        downloaded_bytes: int,
        total_bytes: int,
        speed: Optional[float] = None,
    ) -> None:
        """更新下载进度"""
        async with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"[DownloadProgress] Task {task_id} not found")
                return
            
            task = self._tasks[task_id]
            task.progress = progress
            task.downloaded_bytes = downloaded_bytes
            task.total_bytes = total_bytes
            
            if speed is not None:
                task.download_speed = speed
            
            if task.status == DownloadStatus.PENDING:
                task.status = DownloadStatus.DOWNLOADING
                task.started_at = datetime.now()
        
        logger.debug(f"[DownloadProgress] Task {task_id}: {progress}% ({downloaded_bytes}/{total_bytes} bytes)")
    
    async def update_status(
        self,
        task_id: str,
        status: DownloadStatus,
        error_message: Optional[str] = None,
    ) -> None:
        """更新下载状态"""
        async with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"[DownloadProgress] Task {task_id} not found")
                return
            
            task = self._tasks[task_id]
            task.status = status
            task.error_message = error_message
            
            if status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED]:
                task.completed_at = datetime.now()
        
        logger.info(f"[DownloadProgress] Task {task_id} status changed to {status}")
    
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        async with self._lock:
            if task_id not in self._tasks:
                return None
            
            task = self._tasks[task_id]
            
            return {
                "task_id": task.task_id,
                "model_id": task.model_id,
                "version_id": task.version_id,
                "filename": task.filename,
                "status": task.status.value,
                "progress": task.progress,
                "downloaded_bytes": task.downloaded_bytes,
                "total_bytes": task.total_bytes,
                "download_speed": task.download_speed,
                "error_message": task.error_message,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
    
    async def list_tasks(self, status: Optional[DownloadStatus] = None) -> list:
        """列出所有任务"""
        async with self._lock:
            tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        return [await self.get_task(t.task_id) for t in tasks]
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        await self.update_status(task_id, DownloadStatus.CANCELLED)
        return True
    
    async def remove_task(self, task_id: str) -> None:
        """移除任务"""
        async with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
    
    async def cleanup_completed(self, max_age_hours: int = 24) -> int:
        """清理已完成的旧任务"""
        now = datetime.now()
        removed = 0
        
        async with self._lock:
            to_remove = []
            
            for task_id, task in self._tasks.items():
                if task.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED]:
                    if task.completed_at:
                        age_hours = (now - task.completed_at).total_seconds() / 3600
                        if age_hours > max_age_hours:
                            to_remove.append(task_id)
            
            for task_id in to_remove:
                del self._tasks[task_id]
                removed += 1
        
        if removed > 0:
            logger.info(f"[DownloadProgress] Cleaned up {removed} completed tasks")
        
        return removed


# 全局进度跟踪器实例
_tracker: Optional[DownloadProgressTracker] = None


async def get_download_tracker() -> DownloadProgressTracker:
    """获取下载进度跟踪器实例"""
    global _tracker
    if _tracker is None:
        _tracker = await DownloadProgressTracker.get_instance()
    return _tracker
