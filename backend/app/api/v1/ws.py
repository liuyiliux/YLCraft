"""
YLCraft — WebSocket API

WS  /api/v1/ws              — WebSocket 实时推送端点
GET /api/v1/ws/status       — 连接状态查询
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.ws_manager import get_ws_manager, WSMessage, WSEventType

router = APIRouter()
logger = logging.getLogger("ylcraft.ws_api")


@router.websocket("")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket 实时推送端点

    协议：
    - 连接后默认接收所有事件（全局监听）
    - 客户端可发送 JSON 消息订阅/取消订阅指定 task_id：
      {"action": "subscribe", "task_ids": ["abc123", "def456"]}
      {"action": "unsubscribe", "task_ids": ["abc123"]}
    - 服务端推送消息格式：
      {"event": "task_progress", "task_id": "abc123", "data": {...}, "timestamp": 1234567890.0}
    """
    mgr = get_ws_manager()
    await mgr.connect(ws)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await mgr.send_to(ws, WSMessage(
                    event="error",
                    data={"detail": "Invalid JSON"},
                ))
                continue

            action = msg.get("action")
            if action == "subscribe":
                task_ids = msg.get("task_ids", [])
                if isinstance(task_ids, list):
                    await mgr.subscribe(ws, [str(t) for t in task_ids])
                    await mgr.send_to(ws, WSMessage(
                        event="subscribed",
                        data={"task_ids": task_ids},
                    ))
            elif action == "unsubscribe":
                task_ids = msg.get("task_ids", [])
                if isinstance(task_ids, list):
                    await mgr.unsubscribe(ws, [str(t) for t in task_ids])
                    await mgr.send_to(ws, WSMessage(
                        event="unsubscribed",
                        data={"task_ids": task_ids},
                    ))
            elif action == "ping":
                await mgr.send_to(ws, WSMessage(
                    event="pong",
                    data={},
                ))
            else:
                await mgr.send_to(ws, WSMessage(
                    event="error",
                    data={"detail": f"Unknown action: {action}"},
                ))
    except WebSocketDisconnect:
        await mgr.disconnect(ws)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await mgr.disconnect(ws)


@router.get("/status", summary="WebSocket 连接状态")
async def ws_status():
    """返回当前 WebSocket 连接数"""
    mgr = get_ws_manager()
    return {
        "success": True,
        "active_connections": mgr.active_connections,
    }
