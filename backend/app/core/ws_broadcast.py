"""
YLCraft — WebSocket 广播工具

提供 broadcast_progress / broadcast_complete，解除 comfyui 循环引用。
"""
from __future__ import annotations

from app.core.ws_manager import get_ws_manager


async def broadcast_progress(prompt_id: str, progress: float, step: int = 0, total: int = 0):
    """广播 ComfyUI 进度到 WebSocket 客户端"""
    mgr = get_ws_manager()
    await mgr.send_progress(prompt_id, {
        "type": "progress",
        "prompt_id": prompt_id,
        "progress": progress,
        "step": step,
        "total": total,
    })


async def broadcast_complete(prompt_id: str, status: str, outputs: list = None, error: str = None):
    """广播 ComfyUI 完成状态到 WebSocket 客户端"""
    mgr = get_ws_manager()
    await mgr.send_progress(prompt_id, {
        "type": "complete",
        "prompt_id": prompt_id,
        "status": status,
        "outputs": outputs or [],
        "error": error,
    })
