"""
YLCraft — AI 连接器抽象基类

参考 MediaCrawler 的分层架构设计：
- 定义所有 AI 提供商必须遵循的接口契约
- 支持文本生成、图像生成、视频生成等多种 AI 能力
- 提供统一的使用统计、成本控制、限流等功能

所有 AI 提供商实现必须继承这些抽象基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Any, AsyncIterator, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger("ylcraft.connectors.ai")


# =============================================================================
# 数据模型
# =============================================================================

class AIModelType(str, Enum):
    """AI 模型类型"""
    TEXT = "text"              # 文本模型
    CHAT = "chat"              # 对话模型
    IMAGE = "image"            # 图像生成模型
    VIDEO = "video"            # 视频生成模型
    AUDIO = "audio"            # 音频模型
    EMBEDDING = "embedding"    # 向量模型
    MODERATION = "moderation"   # 内容审核模型


@dataclass
class TextMessage:
    """文本消息"""
    role: str = "user"  # system/user/assistant
    content: str = ""


@dataclass
class ChatRequest:
    """对话请求"""
    messages: list[TextMessage] = field(default_factory=list)
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[list[str]] = None
    stream: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class ChatResponse:
    """对话响应"""
    success: bool
    content: str = ""
    model: str = ""
    finish_reason: Optional[str] = None
    usage: dict = field(default_factory=dict)  # {prompt_tokens, completion_tokens, total_tokens}
    cost: float = 0.0
    latency_ms: int = 0
    error: Optional[str] = None


@dataclass
class ImageGenerationRequest:
    """图像生成请求"""
    prompt: str = ""
    model: str = ""
    size: str = "1024x1024"  # 尺寸
    quality: str = "standard"  # standard/hd
    style: str = "vivid"  # natural/vivid
    n: int = 1  # 生成数量
    response_format: str = "url"  # url/base64
    extra: dict = field(default_factory=dict)


@dataclass
class ImageGenerationResponse:
    """图像生成响应"""
    success: bool
    images: list[dict] = field(default_factory=list)  # [{url, base64}]
    model: str = ""
    cost: float = 0.0
    latency_ms: int = 0
    error: Optional[str] = None


@dataclass
class VideoGenerationRequest:
    """视频生成请求"""
    prompt: str = ""
    model: str = ""
    duration: int = 5  # 秒
    resolution: str = "720p"
    fps: int = 24
    extra: dict = field(default_factory=dict)


@dataclass
class VideoGenerationResponse:
    """视频生成响应"""
    success: bool
    video_url: Optional[str] = None
    video_path: Optional[str] = None
    task_id: Optional[str] = None
    status: str = "pending"
    model: str = ""
    cost: float = 0.0
    latency_ms: int = 0
    error: Optional[str] = None


@dataclass
class TTSRequest:
    """语音合成请求"""
    text: str = ""
    model: str = ""
    voice: str = ""
    speed: float = 1.0
    response_format: str = "mp3"
    extra: dict = field(default_factory=dict)


@dataclass
class TTSResponse:
    """语音合成响应"""
    success: bool
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None
    duration: float = 0.0
    model: str = ""
    cost: float = 0.0
    latency_ms: int = 0
    error: Optional[str] = None


@dataclass
class UsageStats:
    """使用统计"""
    total_requests: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    avg_latency_ms: float = 0.0
    by_model: dict = field(default_factory=dict)  # {model: {requests, tokens, cost}}


# =============================================================================
# 抽象基类
# =============================================================================

class IAIConnector(ABC):
    """
    AI 连接器抽象基类

    所有 AI 提供商连接器必须实现此接口。
    设计参考 MediaCrawler 的模块化架构。
    """

    # 提供商标识（子类必须设置）
    PROVIDER_ID: str = ""
    PROVIDER_NAME: str = ""

    def __init__(self, api_key: str, config: dict = None):
        """
        初始化 AI 连接器

        Args:
            api_key: API 密钥
            config: 额外配置（base_url, organization_id 等）
        """
        self.api_key = api_key
        self.config = config or {}
        self._initialized = False
        self._usage_stats = UsageStats()

    # -------------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------------

    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化连接器

        Returns:
            True if initialization successful
        """
        pass

    @abstractmethod
    async def close(self):
        """关闭连接器"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass

    # -------------------------------------------------------------------------
    # 文本/对话能力
    # -------------------------------------------------------------------------

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        对话生成

        Args:
            request: 对话请求

        Returns:
            对话响应
        """
        pass

    @abstractmethod
    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        流式对话生成

        Args:
            request: 对话请求

        Yields:
            生成的文本片段
        """
        pass

    # -------------------------------------------------------------------------
    # 图像生成能力
    # -------------------------------------------------------------------------

    @abstractmethod
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """
        图像生成

        Args:
            request: 图像生成请求

        Returns:
            图像生成响应
        """
        pass

    # -------------------------------------------------------------------------
    # 视频生成能力
    # -------------------------------------------------------------------------

    @abstractmethod
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """
        视频生成

        Args:
            request: 视频生成请求

        Returns:
            视频生成响应
        """
        pass

    # -------------------------------------------------------------------------
    # 语音合成能力
    # -------------------------------------------------------------------------

    @abstractmethod
    async def text_to_speech(self, request: TTSRequest) -> TTSResponse:
        """
        语音合成

        Args:
            request: 语音合成请求

        Returns:
            语音合成响应
        """
        pass

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def get_provider_id(self) -> str:
        """获取提供商标识"""
        return self.PROVIDER_ID

    def get_provider_name(self) -> str:
        """获取提供商名称"""
        return self.PROVIDER_NAME

    def supports_model_type(self, model_type: AIModelType) -> bool:
        """
        检查是否支持指定模型类型
        子类可覆盖
        """
        return True

    def get_available_models(self, model_type: AIModelType) -> list[str]:
        """
        获取指定类型的可用模型列表
        子类必须实现
        """
        return []

    def get_usage_stats(self) -> UsageStats:
        """获取使用统计"""
        return self._usage_stats

    def reset_usage_stats(self):
        """重置使用统计"""
        self._usage_stats = UsageStats()

    def _update_usage_stats(self, usage: dict, cost: float, latency_ms: int):
        """更新使用统计"""
        self._usage_stats.total_requests += 1
        self._usage_stats.total_tokens += usage.get("total_tokens", 0)
        self._usage_stats.prompt_tokens += usage.get("prompt_tokens", 0)
        self._usage_stats.completion_tokens += usage.get("completion_tokens", 0)
        self._usage_stats.total_cost += cost

        if self._usage_stats.total_requests > 0:
            self._usage_stats.avg_latency_ms = (
                (self._usage_stats.avg_latency_ms * (self._usage_stats.total_requests - 1) + latency_ms)
                / self._usage_stats.total_requests
            )


# =============================================================================
# 抽象工厂
# =============================================================================

class IAIConnectorFactory(ABC):
    """
    AI 连接器工厂抽象

    定义创建 AI 连接器实例的契约。
    """

    @abstractmethod
    def create(self, api_key: str, config: dict = None) -> IAIConnector:
        """创建连接器实例"""
        pass

    @abstractmethod
    def get_provider_id(self) -> str:
        """获取提供商标识"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """获取提供商名称"""
        pass

    @abstractmethod
    def get_supported_model_types(self) -> list[AIModelType]:
        """获取支持的模型类型"""
        pass

    @abstractmethod
    def get_default_models(self) -> dict[AIModelType, str]:
        """获取默认模型映射"""
        pass
