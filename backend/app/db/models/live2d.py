"""
YLCraft — Live2D 模型数据模型
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field


class Live2DModelStatus(str, Enum):
    DRAFT = "draft"           # 草稿
    PROCESSING = "processing"   # 处理中
    RIGGED = "rigged"         # 已绑骨
    ANIMATED = "animated"      # 已生成动作
    COMPLETED = "completed"    # 已完成
    ERROR = "error"            # 错误

    @classmethod
    def all(cls):
        return [e.value for e in cls]

    @classmethod
    def label(cls, value: str) -> str:
        labels = {
            "draft": "草稿",
            "processing": "处理中",
            "rigged": "已绑骨",
            "animated": "已生成动作",
            "completed": "已完成",
            "error": "错误",
        }
        return labels.get(value, value)


class Live2DStyleMode(str, Enum):
    """Live2D 风格模式"""
    ANIME = "anime"           # 动漫立绘模式（输入透明底PNG/PSD）
    COSER_REAL = "coser_real"     # Coser照片模式（保持真人风格）
    COSER_ANIME = "coser_anime"   # Coser照片模式（转二次元风格）

    @classmethod
    def all(cls):
        return [e.value for e in cls]

    @classmethod
    def label(cls, value: str) -> str:
        labels = {
            "anime": "动漫立绘",
            "coser_real": "Coser（真人）",
            "coser_anime": "Coser（转二次元）",
        }
        return labels.get(value, value)

    @classmethod
    def options(cls):
        """返回选项列表（用于前端表单）"""
        return [
            {"value": cls.ANIME.value, "label": "动漫立绘模式", "desc": "上传透明底PNG/PSD立绘"},
            {"value": cls.COSER_REAL.value, "label": "Coser（真人）", "desc": "真人照片，保持真实风格"},
            {"value": cls.COSER_ANIME.value, "label": "Coser（转二次元）", "desc": "真人照片，转换为动漫风格"},
        ]


class Live2DModel(SQLModel, table=True):
    """Live2D 模型主表"""
    __tablename__ = "live2d_models"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    name: str = Field(default="", index=True)
    description: str = Field(default="")

    # 关联角色
    character_id: str = Field(default="")

    # 风格模式（v0.2.0 新增，支持Coser场景）
    style_mode: str = Field(default=Live2DStyleMode.ANIME.value)

    # 处理配置（JSON 字符串存储，记录每个环节使用本地还是API）
    # 格式：{"rembg": "local", "style_transfer": "api", "segmentation": "local"}
    processing_config: str = Field(default="{}")

    # 原始图片
    source_image_path: str = Field(default="")
    source_image_url: str = Field(default="")
    processed_image_path: str = Field(default="")  # 抠图/风格转换后的图片

    # 分层结果（JSON 字符串存储）
    layers: str = Field(default="[]")

    # 模型文件
    model_file_path: str = Field(default="")
    textures_path: str = Field(default="")
    motions_path: str = Field(default="")

    # 状态
    status: str = Field(default=Live2DModelStatus.DRAFT.value)

    # 元数据（JSON 字符串存储）- 改名为 extra_data 以避免与 SQLModel 的 metadata 冲突
    extra_data: str = Field(default="{}")

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = Field(default=None)

    # 使用统计
    use_count: int = Field(default=0)
    last_used_at: Optional[datetime] = Field(default=None)


class Live2DBone(SQLModel, table=True):
    """Live2D 骨骼数据表"""
    __tablename__ = "live2d_bones"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    model_id: str = Field(default="", index=True)

    name: str = Field(default="")
    parent_id: str = Field(default="")

    # 位置信息
    position_x: float = Field(default=0.0)
    position_y: float = Field(default=0.0)
    rotation: float = Field(default=0.0)

    # 绑定权重（JSON 字符串存储）
    weights: str = Field(default="{}")

    created_at: datetime = Field(default_factory=datetime.now)


class Live2DMotion(SQLModel, table=True):
    """Live2D 动作数据表"""
    __tablename__ = "live2d_motions"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    model_id: str = Field(default="", index=True)

    name: str = Field(default="")
    motion_type: str = Field(default="idle")

    # 动作文件
    file_path: str = Field(default="")

    # 动作参数
    duration: float = Field(default=0.0)
    loop: bool = Field(default=False)

    created_at: datetime = Field(default_factory=datetime.now)
