"""
YLCraft — Core Type Contracts

定义全项目共用的数据类型：
- MediaType（媒体类型枚举）
- LLMMessage / ImageGenerationRequest 等请求响应结构
- Protocol 接口定义
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol
from pathlib import Path


class StrEnum(str, Enum):
    """兼容 Python 3.10 的 StrEnum（3.11+ 原生支持）"""
    pass


# ==================== 媒体类型 ====================

class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    LLM = "llm"
    TTS = "tts"


# ==================== 能力枚举 ====================

class ImageCapability(StrEnum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    STYLE_CONTROL = "style_control"


class VideoCapability(StrEnum):
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    SEED_CONTROL = "seed_control"


class LLMCapability(StrEnum):
    TEXT_GENERATION = "text_generation"
    VISION = "vision"
    STRUCTURED_OUTPUT = "structured_output"


# ==================== 请求/响应 Dataclass ====================

@dataclass
class ImageGenerationRequest:
    prompt: str
    negative_prompt: str = ""
    size: str = "1024*1024"
    style: str = ""
    n: int = 1
    seed: int | None = None
    model: str = ""           # 可选，覆盖默认
    provider: str = ""        # 可选，指定 Provider


@dataclass
class ImageGenerationResult:
    success: bool
    url: str | None = None
    urls: list[str] | None = None
    local_path: Path | None = None
    cost: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""
    error: str | None = None


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMGenerationResult:
    success: bool
    content: str = ""
    usage: dict = field(default_factory=dict)
    cost: float = 0.0
    provider: str = ""
    latency_ms: float = 0.0
    error: str | None = None


# ==================== Protocol 接口 ====================

class ImageBackend(Protocol):
    """图像生成后端接口"""
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set: ...
    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
    async def health_check(self) -> bool: ...


class LLMBackend(Protocol):
    """LLM 后端接口"""
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set: ...
    async def chat(self, messages: list[LLMMessage], **kwargs) -> LLMGenerationResult: ...
    async def structured_output(self, schema: dict, prompt: str) -> dict: ...
