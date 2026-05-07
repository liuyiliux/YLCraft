"""
YLCraft — ComfyUI 数据模型

包含：
- WorkflowTemplate: 工作流模板
- WorkflowPreset: 工作流参数预设
- ComfyUITask: 任务执行记录
- ComfyUINode: ComfyUI 节点配置
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlmodel import SQLModel, Field


class WorkflowCategory(str, Enum):
    """工作流分类"""
    TEXT_TO_IMAGE = "txt2img"
    IMAGE_TO_IMAGE = "img2img"
    INPAINTING = "inpainting"
    UPSCALE = "upscale"
    CONTROLNET = "controlnet"
    VIDEO = "video"
    CUSTOM = "custom"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 5
    HIGH = 10
    URGENT = 20


# =============================================================================
# 工作流模板
# =============================================================================

class WorkflowTemplate(SQLModel, table=True):
    """
    工作流模板

    存储可复用的 ComfyUI 工作流配置。
    """
    __tablename__ = "comfyui_workflow_templates"

    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )
    name: str = Field(default="", index=True)
    display_name: str = Field(default="")
    description: str = Field(default="")

    # 分类和标签
    category: WorkflowCategory = Field(default=WorkflowCategory.TEXT_TO_IMAGE, index=True)
    tags: str = Field(default="[]")  # JSON array

    # 工作流定义
    workflow_json: str = Field(default="{}")  # JSON string
    workflow_version: int = Field(default=1)

    # 节点映射配置
    node_mapping: str = Field(default="{}")  # JSON: {"prompt_node": "3", "neg_node": "7", ...}

    # 元数据
    is_active: bool = Field(default=True)
    is_public: bool = Field(default=False)
    use_count: int = Field(default=0)

    # 关联预设
    default_preset_id: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="system")

    class Config:
        use_enum_values = True

    def get_workflow(self) -> Dict[str, Any]:
        """获取工作流 JSON 对象"""
        return json.loads(self.workflow_json)

    def set_workflow(self, workflow: Dict[str, Any]):
        """设置工作流 JSON 对象"""
        self.workflow_json = json.dumps(workflow, ensure_ascii=False, indent=2)

    def get_tags(self) -> List[str]:
        """获取标签列表"""
        try:
            return json.loads(self.tags)
        except:
            return []

    def set_tags(self, tags: List[str]):
        """设置标签列表"""
        self.tags = json.dumps(tags, ensure_ascii=False)

    def get_node_mapping(self) -> Dict[str, str]:
        """获取节点映射"""
        try:
            return json.loads(self.node_mapping)
        except:
            return {}


# =============================================================================
# 工作流预设
# =============================================================================

class WorkflowPreset(SQLModel, table=True):
    """
    工作流参数预设

    存储常用的生成参数组合，方便快速调用。
    """
    __tablename__ = "comfyui_workflow_presets"

    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )
    name: str = Field(default="", index=True)
    display_name: str = Field(default="")
    description: str = Field(default="")

    # 关联模板
    template_id: str = Field(default="", index=True)

    # 参数预设
    params_json: str = Field(default="{}")  # JSON object

    # 使用场景
    use_case: str = Field(default="general")  # general, portrait, landscape, anime, etc.
    is_default: bool = Field(default=False)

    use_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="system")

    def get_params(self) -> Dict[str, Any]:
        """获取参数"""
        try:
            return json.loads(self.params_json)
        except:
            return {}

    def set_params(self, params: Dict[str, Any]):
        """设置参数"""
        self.params_json = json.dumps(params, ensure_ascii=False)


# =============================================================================
# ComfyUI 任务
# =============================================================================

class ComfyUITask(SQLModel, table=True):
    """
    ComfyUI 任务记录

    存储所有 ComfyUI 生成任务的历史和状态。
    """
    __tablename__ = "comfyui_tasks"

    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )

    # ComfyUI prompt_id
    prompt_id: str = Field(default="", unique=True, index=True)

    # 关联模板和预设
    template_id: Optional[str] = Field(default=None, index=True)
    preset_id: Optional[str] = Field(default=None)

    # 任务类型
    task_type: WorkflowCategory = Field(default=WorkflowCategory.TEXT_TO_IMAGE, index=True)

    # 状态
    status: TaskStatus = Field(default=TaskStatus.PENDING, index=True)
    priority: TaskPriority = Field(default=TaskPriority.NORMAL)

    # 生成参数
    prompt: str = Field(default="")
    negative_prompt: str = Field(default="")
    params_json: str = Field(default="{}")  # steps, cfg, sampler, size, lora, controlnet, etc.

    # 源图片（图生图时）
    source_image_path: str = Field(default="")

    # 执行信息
    node_url: str = Field(default="")  # 执行该任务的 ComfyUI 节点地址
    queue_position: int = Field(default=0)

    # 进度
    progress: float = Field(default=0.0)
    current_step: int = Field(default=0)
    total_steps: int = Field(default=0)

    # 输出结果
    outputs_json: str = Field(default="[]")  # JSON array of output info
    output_images: str = Field(default="[]")  # JSON array of local paths

    # 错误信息
    error_message: str = Field(default="")

    # 性能指标
    queued_at: Optional[datetime] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    latency_ms: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True

    def get_params(self) -> Dict[str, Any]:
        """获取参数"""
        try:
            return json.loads(self.params_json)
        except:
            return {}

    def set_params(self, params: Dict[str, Any]):
        """设置参数"""
        self.params_json = json.dumps(params, ensure_ascii=False)

    def get_outputs(self) -> List[Dict[str, Any]]:
        """获取输出列表"""
        try:
            return json.loads(self.outputs_json)
        except:
            return []

    def set_outputs(self, outputs: List[Dict[str, Any]]):
        """设置输出列表"""
        self.outputs_json = json.dumps(outputs, ensure_ascii=False)

    def get_output_images(self) -> List[str]:
        """获取输出图片路径列表"""
        try:
            return json.loads(self.output_images)
        except:
            return []

    def set_output_images(self, paths: List[str]):
        """设置输出图片路径列表"""
        self.output_images = json.dumps(paths, ensure_ascii=False)

    def mark_queued(self, node_url: str):
        """标记为已入队"""
        self.status = TaskStatus.QUEUED
        self.node_url = node_url
        self.queued_at = datetime.now()

    def mark_started(self):
        """标记为开始处理"""
        self.status = TaskStatus.PROCESSING
        self.started_at = datetime.now()

    def mark_completed(self, outputs: List[Dict], output_images: List[str] = None):
        """标记为已完成"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        self.progress = 1.0
        self.set_outputs(outputs)
        if output_images:
            self.set_output_images(output_images)
        if self.started_at:
            self.latency_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)

    def mark_failed(self, error: str):
        """标记为失败"""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error
        if self.started_at:
            self.latency_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)

    def mark_cancelled(self):
        """标记为已取消"""
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now()


# =============================================================================
# ComfyUI 节点配置
# =============================================================================

class ComfyUINode(SQLModel, table=True):
    """
    ComfyUI 节点配置

    存储可用的 ComfyUI 服务器节点信息。
    """
    __tablename__ = "comfyui_nodes"

    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )
    name: str = Field(default="", index=True)
    display_name: str = Field(default="")

    # 连接信息
    server_url: str = Field(default="http://127.0.0.1:8188")
    api_key: str = Field(default="")

    # 能力配置
    capabilities: str = Field(default="[]")  # ["txt2img", "img2img", "video", ...]
    max_resolution: int = Field(default=2048)
    supported_models: str = Field(default="[]")

    # 状态
    is_active: bool = Field(default=True)
    is_default: bool = Field(default=False)

    # 负载配置
    max_queue_size: int = Field(default=10)
    current_load: int = Field(default=0)
    priority: int = Field(default=0)  # 数字越大优先级越高

    # 统计
    total_tasks: int = Field(default=0)
    success_tasks: int = Field(default=0)
    failed_tasks: int = Field(default=0)
    avg_latency_ms: int = Field(default=0)

    last_heartbeat: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_capabilities(self) -> List[str]:
        try:
            return json.loads(self.capabilities)
        except:
            return []

    def set_capabilities(self, caps: List[str]):
        self.capabilities = json.dumps(caps, ensure_ascii=False)

    def get_models(self) -> List[str]:
        try:
            return json.loads(self.supported_models)
        except:
            return []

    def set_models(self, models: List[str]):
        self.supported_models = json.dumps(models, ensure_ascii=False)
