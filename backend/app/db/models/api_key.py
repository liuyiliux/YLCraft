"""
YLCraft — API 密钥数据模型

统一管理所有第三方 API 密钥（支持多 provider）。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field


class ApiKeyStatus(str, Enum):
    """密钥状态"""
    ACTIVE = "active"       # 启用
    DISABLED = "disabled"   # 禁用
    EXPIRED = "expired"     # 已过期

    @classmethod
    def all(cls):
        return [e.value for e in cls]


class ApiKeyCategory(str, Enum):
    """密钥分类"""
    IMAGE_PROCESSING = "image-processing"  # 图像处理（抠图、分割等）
    LLM = "llm"                          # 大语言模型
    IMAGE = "image"                      # 图像生成
    VIDEO = "video"                      # 视频生成
    TTS = "tts"                          # 语音合成
    OTHER = "other"                       # 其他

    @classmethod
    def all(cls):
        return [e.value for e in cls]


class ApiKey(SQLModel, table=True):
    """
    API 密钥表

    支持存储多个 provider 的密钥，按分类管理。
    密钥值加密存储（简化版：base64编码，后续可升级为AES加密）。
    """
    __tablename__ = "api_keys"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    name: str = Field(default="", index=True)

    # Provider 标识（与 providers.yaml 中的名称对应）
    provider: str = Field(default="", index=True, unique=True)

    # 密钥分类
    category: str = Field(default=ApiKeyCategory.OTHER.value)

    # 密钥值（加密存储）
    api_key: str = Field(default="")

    # 可选：API 密钥对应的 secret（某些 provider 需要）
    api_secret: str = Field(default="")

    # 可选：关联的 model/id
    model: str = Field(default="")

    # 配置信息（JSON 字符串，如 endpoint、额外参数）
    config: str = Field(default="{}")

    # 状态
    status: str = Field(default=ApiKeyStatus.ACTIVE.value)

    # 使用统计
    use_count: int = Field(default=0)
    last_used_at: Optional[datetime] = Field(default=None)

    # 配额信息（可选）
    quota: Optional[float] = Field(default=None)        # 总配额
    quota_used: float = Field(default=0.0)              # 已使用配额

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = Field(default=None)

    # 元数据
    extra_data: str = Field(default="{}")

    def is_active(self) -> bool:
        """检查密钥是否可用"""
        if self.status != ApiKeyStatus.ACTIVE.value:
            return False
        if self.expires_at and self.expires_at < datetime.now():
            return False
        return True

    def increment_usage(self):
        """增加使用计数"""
        self.use_count += 1
        self.last_used_at = datetime.now()
