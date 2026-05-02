"""
YLCraft — WebSocket 管理器

管理 WebSocket 连接池，支持：
1. 任务进度实时推送
2. 按 task_id 订阅（客户端只接收关注的事件）
3. 全局广播（所有连接）
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("ylcraft.ws")


# =============================================================================
# 消息类型定义
# =============================================================================

class WSEventType:
    """WebSocket 事件类型常量"""
    TASK_PROGRESS = "task_progress"     # 任务进度更新
    TASK_COMPLETE = "task_complete"     # 任务完成
    TASK_FAILED = "task_failed"        # 任务失败
    TASK_CREATED = "task_created"      # 新任务创建
    NOTIFICATION = "notification"       # 通用通知


@dataclass
class WSMessage:
    """WebSocket 推送消息"""
    event: str
    task_id: str | None = None
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps({
            "event": self.event,
            "task_id": self.task_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }, ensure_ascii=False)


# =============================================================================
# 连接管理器
# =============================================================================

class ConnectionManager:
    """
    WebSocket 连接管理器

    设计：
    - 每个连接可以订阅一组 task_id，只接收相关事件
    - 未订阅任何 task_id 的连接接收所有事件（全局监听）
    - 线程安全：使用 asyncio.Lock
    """

    def __init__(self):
        # websocket -> set of subscribed task_ids (空=全局)
        self._subscriptions: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """接受新连接"""
        await ws.accept()
        async with self._lock:
            self._subscriptions[ws] = set()
        logger.info(f"WS connected, total: {len(self._subscriptions)}")

    async def disconnect(self, ws: WebSocket) -> None:
        """断开连接"""
        async with self._lock:
            self._subscriptions.pop(ws, None)
        logger.info(f"WS disconnected, total: {len(self._subscriptions)}")

    async def subscribe(self, ws: WebSocket, task_ids: list[str]) -> None:
        """订阅指定任务"""
        async with self._lock:
            if ws in self._subscriptions:
                self._subscriptions[ws].update(task_ids)

    async def unsubscribe(self, ws: WebSocket, task_ids: list[str]) -> None:
        """取消订阅"""
        async with self._lock:
            if ws in self._subscriptions:
                self._subscriptions[ws] -= set(task_ids)

    async def broadcast(self, message: WSMessage) -> None:
        """
        广播消息：
        - 有 task_id → 只推送给订阅了该 task_id 的连接 + 全局监听连接
        - 无 task_id → 推送给所有连接
        """
        payload = message.to_json()
        disconnected: list[WebSocket] = []

        async with self._lock:
            targets = list(self._subscriptions.items())

        for ws, subscribed in targets:
            # 全局监听（空订阅集）或订阅了该 task_id
            if message.task_id and subscribed and message.task_id not in subscribed:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.append(ws)

        # 清理断开的连接
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._subscriptions.pop(ws, None)

    async def send_to(self, ws: WebSocket, message: WSMessage) -> None:
        """发送消息给指定连接"""
        try:
            await ws.send_text(message.to_json())
        except Exception:
            await self.disconnect(ws)

    @property
    def active_connections(self) -> int:
        return len(self._subscriptions)


# =============================================================================
# 全局单例
# =============================================================================

_manager: ConnectionManager | None = None


def get_ws_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


async def push_task_progress(
    task_id: str,
    progress: int,
    message: str = "",
    task_type: str = "",
    status: str = "",
) -> None:
    """便捷方法：推送任务进度更新"""
    mgr = get_ws_manager()
    event = (
        WSEventType.TASK_COMPLETE if status == "done"
        else WSEventType.TASK_FAILED if status == "failed"
        else WSEventType.TASK_PROGRESS
    )
    await mgr.broadcast(WSMessage(
        event=event,
        task_id=task_id,
        data={
            "progress": progress,
            "message": message,
            "task_type": task_type,
            "status": status,
        },
    ))


async def push_task_created(
    task_id: str,
    task_type: str,
    payload: dict | None = None,
) -> None:
    """便捷方法：推送新任务创建"""
    mgr = get_ws_manager()
    await mgr.broadcast(WSMessage(
        event=WSEventType.TASK_CREATED,
        task_id=task_id,
        data={
            "task_type": task_type,
            "payload": payload or {},
        },
    ))


async def push_notification(
    title: str,
    body: str,
    level: str = "info",
) -> None:
    """便捷方法：推送通用通知"""
    mgr = get_ws_manager()
    await mgr.broadcast(WSMessage(
        event=WSEventType.NOTIFICATION,
        data={
            "title": title,
            "body": body,
            "level": level,
        },
    ))
