"""
YLCraft — ComfyUI 管理 API

=== 工作流模板 ===
GET    /api/v1/comfyui/workflows              — 列出可用工作流
GET    /api/v1/comfyui/workflows/{name}        — 获取工作流
POST   /api/v1/comfyui/workflows              — 保存工作流
DELETE /api/v1/comfyui/workflows/{name}        — 删除工作流

=== 工作流模板（数据库）===
GET    /api/v1/comfyui/templates              — 列出模板
GET    /api/v1/comfyui/templates/{id}          — 获取模板
POST   /api/v1/comfyui/templates              — 创建模板
PUT    /api/v1/comfyui/templates/{id}          — 更新模板
DELETE /api/v1/comfyui/templates/{id}          — 删除模板

=== 预设 ===
GET    /api/v1/comfyui/presets                — 列出预设
GET    /api/v1/comfyui/presets/{id}            — 获取预设
POST   /api/v1/comfyui/presets                — 创建预设
DELETE /api/v1/comfyui/presets/{id}            — 删除预设

=== 任务 ===
GET    /api/v1/comfyui/tasks                  — 列出任务
GET    /api/v1/comfyui/tasks/{prompt_id}       — 获取任务
GET    /api/v1/comfyui/tasks/stats            — 获取统计

=== 节点 ===
GET    /api/v1/comfyui/nodes                  — 列出节点
POST   /api/v1/comfyui/nodes                  — 添加节点
PUT    /api/v1/comfyui/nodes/{id}/default      — 设为默认
DELETE /api/v1/comfyui/nodes/{id}             — 删除节点

=== 模型 ===
GET    /api/v1/comfyui/models                 — 获取可用模型列表
GET    /api/v1/comfyui/loras                  — 获取可用 LoRA 列表
GET    /api/v1/comfyui/controlnets            — 获取可用 ControlNet 列表

=== 状态 ===
GET    /api/v1/comfyui/progress               — 获取当前进度
GET    /api/v1/comfyui/queue                  — 获取队列状态
POST   /api/v1/comfyui/interrupt              — 中断当前任务
DELETE /api/v1/comfyui/queue/{prompt_id}       — 从队列删除任务

=== WebSocket ===
WS     /api/v1/comfyui/ws/progress            — 实时进度推送
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from starlette.websockets import WebSocketState

from app.db.models.comfyui import (
    WorkflowCategory, TaskStatus, TaskPriority,
    WorkflowTemplate, WorkflowPreset, ComfyUITask, ComfyUINode,
)
from app.services.comfyui.service import (
    WorkflowService, PresetService, TaskService, NodeService,
)
from app.services.ai import get_ai_service
from app.services.ai.types import MediaType

router = APIRouter()
logger = logging.getLogger("ylcraft.comfyui")


# =============================================================================
# 请求/响应模型
# =============================================================================

class WorkflowSaveRequest(BaseModel):
    """保存工作流请求"""
    name: str
    workflow: Dict[str, Any]


class ModelInfo(BaseModel):
    """模型信息"""
    name: str
    filename: str


class ProgressResponse(BaseModel):
    """进度响应"""
    progress: float
    running: List[Dict]
    queued: List[Dict]


# =============================================================================
# 工作流管理
# =============================================================================

@router.get("/workflows", summary="列出可用工作流")
async def list_workflows():
    """
    列出所有可用的 ComfyUI 工作流

    Returns:
        工作流名称列表
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        workflow_dir = backend._config.workflow_dir
        if not workflow_dir or not Path(workflow_dir).exists():
            return {"success": True, "workflows": []}
        
        workflows = []
        for f in Path(workflow_dir).glob("*.json"):
            workflows.append({
                "name": f.stem,
                "path": str(f),
                "size": f.stat().st_size,
            })
        
        return {"success": True, "workflows": workflows}
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(500, str(e))


@router.get("/workflows/{name}", summary="获取工作流")
async def get_workflow(name: str):
    """
    获取指定工作流的配置

    Args:
        name: 工作流名称（不含 .json 后缀）
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        workflow = backend._client.load_workflow(name)
        return {"success": True, "name": name, "workflow": workflow}
    except FileNotFoundError:
        raise HTTPException(404, f"Workflow not found: {name}")
    except Exception as e:
        logger.error(f"Failed to get workflow: {e}")
        raise HTTPException(500, str(e))


@router.post("/workflows", summary="保存工作流")
async def save_workflow(request: WorkflowSaveRequest):
    """
    保存工作流配置

    Args:
        request: 包含 name 和 workflow 的请求
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        backend._client.save_workflow(request.name, request.workflow)
        return {"success": True, "message": f"Workflow '{request.name}' saved"}
    except Exception as e:
        logger.error(f"Failed to save workflow: {e}")
        raise HTTPException(500, str(e))


@router.delete("/workflows/{name}", summary="删除工作流")
async def delete_workflow(name: str):
    """
    删除指定工作流

    Args:
        name: 工作流名称（不含 .json 后缀）
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        workflow_dir = backend._config.workflow_dir
        path = Path(workflow_dir) / f"{name}.json"
        
        if not path.exists():
            raise HTTPException(404, f"Workflow not found: {name}")
        
        path.unlink()
        return {"success": True, "message": f"Workflow '{name}' deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete workflow: {e}")
        raise HTTPException(500, str(e))


# =============================================================================
# 模型管理
# =============================================================================

@router.get("/models", summary="获取可用模型列表", response_model=List[ModelInfo])
async def get_models():
    """
    获取 ComfyUI 可用的模型列表

    Returns:
        模型信息列表
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        models_data = await backend._client.get_models()
        return [
            ModelInfo(name=m["name"], filename=m["filename"])
            for m in models_data.get("model_list", [])
        ]
    except Exception as e:
        logger.error(f"Failed to get models: {e}")
        raise HTTPException(500, str(e))


@router.get("/loras", summary="获取可用 LoRA 列表", response_model=List[ModelInfo])
async def get_loras():
    """
    获取 ComfyUI 可用的 LoRA 模型列表

    Returns:
        LoRA 模型信息列表
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        loras_data = await backend._client.get_lora_models()
        return [
            ModelInfo(name=m["name"], filename=m["filename"])
            for m in loras_data.get("lora_list", [])
        ]
    except Exception as e:
        logger.error(f"Failed to get LoRAs: {e}")
        raise HTTPException(500, str(e))


@router.get("/controlnets", summary="获取可用 ControlNet 列表", response_model=List[ModelInfo])
async def get_controlnets():
    """
    获取 ComfyUI 可用的 ControlNet 模型列表

    Returns:
        ControlNet 模型信息列表
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        cn_data = await backend._client.get_controlnet_models()
        return [
            ModelInfo(name=m["name"], filename=m["filename"])
            for m in cn_data.get("control_net_list", [])
        ]
    except Exception as e:
        logger.error(f"Failed to get ControlNets: {e}")
        raise HTTPException(500, str(e))


# =============================================================================
# 任务管理
# =============================================================================

@router.get("/progress", summary="获取当前进度", response_model=ProgressResponse)
async def get_progress():
    """
    获取 ComfyUI 当前执行进度

    Returns:
        进度信息（0.0 - 1.0）
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        progress_data = await backend._client.get_progress()
        return ProgressResponse(
            progress=progress_data.get("progress", 0.0),
            running=progress_data.get("running", []),
            queued=progress_data.get("queued", []),
        )
    except Exception as e:
        logger.error(f"Failed to get progress: {e}")
        raise HTTPException(500, str(e))


@router.get("/queue", summary="获取队列状态")
async def get_queue():
    """
    获取 ComfyUI 队列状态

    Returns:
        队列信息（运行中、待处理）
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        queue_data = await backend._client.get_queue()
        return {"success": True, **queue_data}
    except Exception as e:
        logger.error(f"Failed to get queue: {e}")
        raise HTTPException(500, str(e))


@router.post("/interrupt", summary="中断当前任务")
async def interrupt():
    """
    中断 ComfyUI 当前执行的任务
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        await backend._client.interrupt()
        return {"success": True, "message": "Interrupt signal sent"}
    except Exception as e:
        logger.error(f"Failed to interrupt: {e}")
        raise HTTPException(500, str(e))


@router.delete("/queue/{prompt_id}", summary="从队列删除任务")
async def delete_from_queue(prompt_id: str):
    """
    从 ComfyUI 队列中删除指定任务

    Args:
        prompt_id: 任务 ID
    """
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        
        if not backend or not hasattr(backend, '_client'):
            raise HTTPException(503, "ComfyUI backend not available")
        
        await backend._client.delete_from_queue(prompt_id)
        return {"success": True, "message": f"Task {prompt_id} removed from queue"}
    except Exception as e:
        logger.error(f"Failed to delete from queue: {e}")
        raise HTTPException(500, str(e))


# =============================================================================
# WebSocket 实时进度推送
# =============================================================================

import asyncio
import json
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # prompt_id -> set of websocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        # 全局连接（不限定 prompt_id）
        self._global_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, prompt_id: str = None):
        """接受 WebSocket 连接"""
        await websocket.accept()
        async with self._lock:
            if prompt_id:
                if prompt_id not in self._connections:
                    self._connections[prompt_id] = set()
                self._connections[prompt_id].add(websocket)
            else:
                self._global_connections.add(websocket)
    
    async def disconnect(self, websocket: WebSocket, prompt_id: str = None):
        """断开 WebSocket 连接"""
        async with self._lock:
            if prompt_id and prompt_id in self._connections:
                self._connections[prompt_id].discard(websocket)
                if not self._connections[prompt_id]:
                    del self._connections[prompt_id]
            self._global_connections.discard(websocket)
    
    async def send_progress(self, prompt_id: str, data: dict):
        """向订阅了指定 prompt_id 的连接发送进度"""
        async with self._lock:
            connections = self._connections.get(prompt_id, set()).copy()
            global_conns = self._global_connections.copy()
        
        for conn in connections | global_conns:
            try:
                if conn.client_state == WebSocketState.CONNECTED:
                    await conn.send_json(data)
            except Exception as e:
                logger.warning(f"Failed to send to websocket: {e}")
                await self.disconnect(conn, prompt_id)


# 全局连接管理器
_manager = ConnectionManager()


@router.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket, prompt_id: str = None):
    """
    WebSocket 实时进度推送
    
    连接后持续接收 ComfyUI 任务进度推送。
    
    URL: ws://localhost:8000/api/v1/comfyui/ws/progress
    URL: ws://localhost:8000/api/v1/comfyui/ws/progress?prompt_id=xxx
    
    接收消息格式:
        {"type": "progress", "prompt_id": "xxx", "progress": 0.5, "step": 10, "total": 20}
        {"type": "complete", "prompt_id": "xxx", "status": "success", "outputs": [...]}
        {"type": "error", "prompt_id": "xxx", "error": "error message"}
    """
    await _manager.connect(websocket, prompt_id)
    
    try:
        while True:
            # 保持连接，定期发送 ping
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # 解析客户端消息
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_json({"type": "heartbeat", "timestamp": asyncio.get_event_loop().time()})
                except:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await _manager.disconnect(websocket, prompt_id)


async def broadcast_progress(prompt_id: str, progress: float, step: int = 0, total: int = 0):
    """广播进度更新（供其他服务调用）"""
    await _manager.send_progress(prompt_id, {
        "type": "progress",
        "prompt_id": prompt_id,
        "progress": progress,
        "step": step,
        "total": total,
    })


async def broadcast_complete(prompt_id: str, status: str, outputs: list = None, error: str = None):
    """广播任务完成（供其他服务调用）"""
    await _manager.send_progress(prompt_id, {
        "type": "complete",
        "prompt_id": prompt_id,
        "status": status,
        "outputs": outputs or [],
        "error": error,
    })


# =============================================================================
# 数据库模板管理 API
# =============================================================================

class TemplateCreateRequest(BaseModel):
    """创建模板请求"""
    name: str
    display_name: str = ""
    description: str = ""
    category: str = "txt2img"
    workflow_json: Dict[str, Any]
    tags: List[str] = []
    node_mapping: Dict[str, str] = {}


class TemplateUpdateRequest(BaseModel):
    """更新模板请求"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    workflow_json: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    node_mapping: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


class PresetCreateRequest(BaseModel):
    """创建预设请求"""
    name: str
    template_id: str
    display_name: str = ""
    description: str = ""
    params: Dict[str, Any]
    use_case: str = "general"
    is_default: bool = False


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    template_id: Optional[str] = None
    preset_id: Optional[str] = None
    prompt: str
    negative_prompt: str = ""
    params: Dict[str, Any] = {}
    priority: int = 5


class NodeCreateRequest(BaseModel):
    """创建节点请求"""
    name: str
    server_url: str = "http://127.0.0.1:8188"
    display_name: str = ""
    capabilities: List[str] = ["txt2img"]
    max_resolution: int = 2048
    priority: int = 0


@router.get("/templates", summary="列出模板")
async def list_templates(
    category: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """列出数据库中的工作流模板"""
    cat = WorkflowCategory(category) if category else None
    templates, total = await WorkflowService.list_templates(
        category=cat,
        limit=limit,
        offset=offset,
    )
    return {
        "success": True,
        "templates": [t.model_dump() for t in templates],
        "total": total,
    }


@router.get("/templates/{template_id}", summary="获取模板")
async def get_template(template_id: str):
    """获取指定模板"""
    template = await WorkflowService.get_template(template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return {"success": True, "template": template.model_dump()}


@router.post("/templates", summary="创建模板")
async def create_template(request: TemplateCreateRequest):
    """创建工作流模板"""
    try:
        template = await WorkflowService.create_template(
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            category=WorkflowCategory(request.category),
            workflow_json=request.workflow_json,
            tags=request.tags,
            node_mapping=request.node_mapping,
        )
        return {"success": True, "template": template.model_dump()}
    except Exception as e:
        logger.error(f"Failed to create template: {e}")
        raise HTTPException(500, str(e))


@router.put("/templates/{template_id}", summary="更新模板")
async def update_template(template_id: str, request: TemplateUpdateRequest):
    """更新工作流模板"""
    kwargs = request.model_dump(exclude_unset=True)
    if "workflow_json" in kwargs and kwargs["workflow_json"]:
        kwargs["workflow_json"] = kwargs["workflow_json"]

    template = await WorkflowService.update_template(template_id, **kwargs)
    if not template:
        raise HTTPException(404, "Template not found")
    return {"success": True, "template": template.model_dump()}


@router.delete("/templates/{template_id}", summary="删除模板")
async def delete_template(template_id: str):
    """删除工作流模板"""
    success = await WorkflowService.delete_template(template_id)
    if not success:
        raise HTTPException(404, "Template not found")
    return {"success": True, "message": "Template deleted"}


# =============================================================================
# 预设管理 API
# =============================================================================

@router.get("/presets", summary="列出预设")
async def list_presets(template_id: str = None, use_case: str = None):
    """列出预设"""
    presets = await PresetService.list_presets(
        template_id=template_id,
        use_case=use_case,
    )
    return {"success": True, "presets": [p.model_dump() for p in presets]}


@router.get("/presets/{preset_id}", summary="获取预设")
async def get_preset(preset_id: str):
    """获取预设"""
    preset = await PresetService.get_preset(preset_id)
    if not preset:
        raise HTTPException(404, "Preset not found")
    return {"success": True, "preset": preset.model_dump()}


@router.post("/presets", summary="创建预设")
async def create_preset(request: PresetCreateRequest):
    """创建预设"""
    try:
        preset = await PresetService.create_preset(
            name=request.name,
            template_id=request.template_id,
            display_name=request.display_name,
            description=request.description,
            params=request.params,
            use_case=request.use_case,
            is_default=request.is_default,
        )
        return {"success": True, "preset": preset.model_dump()}
    except Exception as e:
        logger.error(f"Failed to create preset: {e}")
        raise HTTPException(500, str(e))


@router.delete("/presets/{preset_id}", summary="删除预设")
async def delete_preset(preset_id: str):
    """删除预设"""
    success = await PresetService.delete_preset(preset_id)
    if not success:
        raise HTTPException(404, "Preset not found")
    return {"success": True, "message": "Preset deleted"}


# =============================================================================
# 任务管理 API
# =============================================================================

@router.get("/tasks", summary="列出任务")
async def list_tasks(
    status: str = None,
    template_id: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """列出任务"""
    task_status = TaskStatus(status) if status else None
    tasks, total = await TaskService.list_tasks(
        status=task_status,
        template_id=template_id,
        limit=limit,
        offset=offset,
    )
    return {
        "success": True,
        "tasks": [t.model_dump() for t in tasks],
        "total": total,
    }


@router.get("/tasks/stats", summary="获取统计")
async def get_task_stats():
    """获取任务统计"""
    stats = await TaskService.get_stats()
    return {"success": True, "stats": stats}


@router.get("/tasks/{prompt_id}", summary="获取任务")
async def get_task(prompt_id: str):
    """获取任务"""
    task = await TaskService.get_task(prompt_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {"success": True, "task": task.model_dump()}


@router.post("/tasks", summary="创建任务")
async def create_task(request: TaskCreateRequest):
    """创建任务（仅记录，不执行）"""
    import uuid
    prompt_id = f"task_{uuid.uuid4().hex[:12]}"

    try:
        task = await TaskService.create_task(
            prompt_id=prompt_id,
            task_type=WorkflowCategory.TEXT_TO_IMAGE,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            params=request.params,
            template_id=request.template_id,
            preset_id=request.preset_id,
            priority=TaskPriority(request.priority),
        )
        return {"success": True, "task": task.model_dump()}
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(500, str(e))


@router.delete("/tasks/{prompt_id}", summary="取消任务")
async def cancel_task(prompt_id: str):
    """取消任务"""
    # 先尝试从 ComfyUI 队列删除
    try:
        manager = get_ai_service()
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        if backend and hasattr(backend, '_client'):
            await backend._client.delete_from_queue(prompt_id)
    except Exception as e:
        logger.warning(f"Failed to delete from queue: {e}")

    # 标记为已取消
    task = await TaskService.mark_cancelled(prompt_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {"success": True, "task": task.model_dump()}


# =============================================================================
# 节点管理 API
# =============================================================================

@router.get("/nodes", summary="列出节点")
async def list_nodes(capability: str = None):
    """列出节点"""
    nodes = await NodeService.list_nodes(capability=capability)
    return {"success": True, "nodes": [n.model_dump() for n in nodes]}


@router.post("/nodes", summary="添加节点")
async def create_node(request: NodeCreateRequest):
    """添加 ComfyUI 节点"""
    try:
        node = await NodeService.create_node(
            name=request.name,
            server_url=request.server_url,
            display_name=request.display_name,
            capabilities=request.capabilities,
            max_resolution=request.max_resolution,
            priority=request.priority,
        )
        return {"success": True, "node": node.model_dump()}
    except Exception as e:
        logger.error(f"Failed to create node: {e}")
        raise HTTPException(500, str(e))


@router.put("/nodes/{node_id}/default", summary="设为默认节点")
async def set_default_node(node_id: str):
    """设为默认节点"""
    success = await NodeService.set_default(node_id)
    if not success:
        raise HTTPException(404, "Node not found")
    return {"success": True, "message": "Node set as default"}


@router.delete("/nodes/{node_id}", summary="删除节点")
async def delete_node(node_id: str):
    """删除节点"""
    success = await NodeService.delete_node(node_id)
    if not success:
        raise HTTPException(404, "Node not found")
    return {"success": True, "message": "Node deleted"}


# =============================================================================
# 图像生成 API
# =============================================================================

class GenerateRequest(BaseModel):
    """图像生成请求"""
    # 工作流
    template_id: Optional[str] = None  # 使用模板
    workflow_name: Optional[str] = None  # 或使用文件名
    # 基础参数
    prompt: str = ""
    negative_prompt: str = ""
    size: str = "512x512"
    steps: int = 20
    cfg_scale: float = 7.0
    seed: Optional[int] = None
    batch_size: int = 1
    sampler: str = "euler"
    # 高级参数
    lora: Optional[str] = None
    controlnet: Optional[str] = None
    source_image: Optional[str] = None  # 图生图时的源图片路径
    # 任务控制
    priority: int = 5
    wait_for_result: bool = False  # 同步等待结果


class GenerateResponse(BaseModel):
    """图像生成响应"""
    success: bool
    prompt_id: str = ""
    task_id: str = ""
    status: str = ""
    message: str = ""
    outputs: List[Dict[str, Any]] = []


@router.post("/generate", summary="生成图像", response_model=GenerateResponse)
async def generate_image(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    提交图像生成任务

    支持两种模式：
    1. 使用数据库模板 (template_id)
    2. 使用文件工作流 (workflow_name)

    返回后立即返回 task_id，可通过 WebSocket 或轮询获取进度。
    设置 wait_for_result=true 同步等待完成（默认 5 分钟超时）。
    """
    import uuid
    from app.services.comfyui.pool import get_pool, ComfyUIScheduler

    prompt_id = f"gen_{uuid.uuid4().hex[:12]}"

    try:
        manager = get_ai_service()
        pool = get_pool()
        scheduler = ComfyUIScheduler(pool)

        # 1. 获取工作流配置
        workflow = None
        template = None

        if request.template_id:
            template = await WorkflowService.get_template(request.template_id)
            if template:
                workflow = template.get_workflow()
        elif request.workflow_name:
            backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
            if backend and hasattr(backend, '_client'):
                try:
                    workflow = backend._client.load_workflow(request.workflow_name)
                except FileNotFoundError:
                    raise HTTPException(404, f"Workflow not found: {request.workflow_name}")
        else:
            raise HTTPException(400, "template_id or workflow_name required")

        if not workflow:
            raise HTTPException(404, "Workflow not found")

        # 2. 应用参数
        params = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "size": request.size,
            "steps": request.steps,
            "cfg_scale": request.cfg_scale,
            "seed": request.seed or random_seed(),
            "batch_size": request.batch_size,
            "sampler": request.sampler,
            "lora": request.lora,
            "controlnet": request.controlnet,
            "source_image": request.source_image,
            "task_type": "img2img" if request.source_image else "txt2img",
        }

        # 应用到工作流
        backend = manager.get_backend(MediaType.IMAGE, "comfyui-image")
        if backend and hasattr(backend, '_client'):
            await backend._apply_parameters(workflow, type('Request', (), params)())

        # 3. 提交任务
        if request.wait_for_result:
            # 同步模式
            success, message = await scheduler.submit_task(
                prompt_id=prompt_id,
                workflow=workflow,
                params=params,
                template_id=request.template_id,
            )

            if success:
                # 等待完成（最多 5 分钟）
                for _ in range(300):
                    await asyncio.sleep(1)
                    task = await TaskService.get_task(prompt_id)
                    if task:
                        if task.status == TaskStatus.COMPLETED:
                            return GenerateResponse(
                                success=True,
                                prompt_id=prompt_id,
                                task_id=task.id,
                                status="completed",
                                outputs=task.get_outputs(),
                            )
                        elif task.status == TaskStatus.FAILED:
                            return GenerateResponse(
                                success=False,
                                prompt_id=prompt_id,
                                task_id=task.id,
                                status="failed",
                                message=task.error_message,
                            )
                return GenerateResponse(
                    success=True,
                    prompt_id=prompt_id,
                    status="processing",
                    message="Task timeout, still processing in background",
                )
            else:
                return GenerateResponse(success=False, message=message)
        else:
            # 异步模式
            success, message = await scheduler.submit_task(
                prompt_id=prompt_id,
                workflow=workflow,
                params=params,
                template_id=request.template_id,
            )

            return GenerateResponse(
                success=success,
                prompt_id=prompt_id,
                status="queued" if success else "failed",
                message=message,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate failed: {e}")
        raise HTTPException(500, str(e))


def random_seed() -> int:
    """生成随机种子"""
    return random.randint(0, 2147483647)
