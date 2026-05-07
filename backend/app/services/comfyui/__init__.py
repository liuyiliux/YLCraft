"""
YLCraft — ComfyUI 服务包

导出 ComfyUI 客户端、后端实现和服务层。
"""

from .client import ComfyUIClient
from .image_backend import ComfyUIImageBackend, ComfyUIImageConfig, ComfyUIImageCapabilities
from .service import WorkflowService, PresetService, TaskService, NodeService
from .pool import ComfyUIPool, ComfyUIScheduler, get_pool

__all__ = [
    # 客户端
    "ComfyUIClient",
    # 后端
    "ComfyUIImageBackend",
    "ComfyUIImageConfig",
    "ComfyUIImageCapabilities",
    # 服务层
    "WorkflowService",
    "PresetService",
    "TaskService",
    "NodeService",
    # 连接池
    "ComfyUIPool",
    "ComfyUIScheduler",
    "get_pool",
]
