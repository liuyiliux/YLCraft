"""
YLCraft — Core Type Contracts

定义全项目共用的数据类型：
- MediaType（媒体类型枚举）
- LLMMessage / ImageGenerationRequest 等请求响应结构
- Protocol 接口定义
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, TYPE_CHECKING, TypeVar

import httpx

logger = logging.getLogger("ylcraft.contracts")

if TYPE_CHECKING:
    pass

T = TypeVar("T")


class StrEnum(str, Enum):
    """兼容 Python 3.9 的 StrEnum"""
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
    GENERATE_AUDIO = "generate_audio"
    NEGATIVE_PROMPT = "negative_prompt"


class LLMCapability(StrEnum):
    TEXT_GENERATION = "text_generation"
    VISION = "vision"
    STRUCTURED_OUTPUT = "structured_output"


# ==================== 图片请求/响应 ====================

@dataclass
class ImageGenerationRequest:
    """图片生成请求"""
    prompt: str
    output_path: Path | None = None
    negative_prompt: str = ""
    size: str = "1024x1024"
    aspect_ratio: str = "9:16"
    style: str = ""
    n: int = 1
    seed: int | None = None
    model: str = ""
    provider: str = ""
    reference_images: list[str] = field(default_factory=list)
    # ComfyUI 扩展参数
    source_image: str = ""  # 图生图的源图片路径
    steps: int = 20  # 采样步数
    cfg_scale: float = 7.0  # CFG Scale
    batch_size: int = 1  # 批量大小
    sampler: str = "euler"  # 采样器
    lora: str = ""  # LoRA 模型
    controlnet: str = ""  # ControlNet 模型
    prompt_id: str = ""  # 任务 ID（用于 WebSocket 追踪）


@dataclass
class ImageGenerationResult:
    """图片生成结果"""
    success: bool
    image_path: Path | None = None
    url: str | None = None
    urls: list[str] | None = None
    local_path: str | None = None  # 本地存储路径
    all_local_paths: list[str] | None = None  # 所有本地路径（批量）
    task_id: str = ""  # 任务 ID
    prompt_id: str = ""  # ComfyUI prompt ID
    cost: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""
    model: str = ""
    seed: int | None = None
    usage_tokens: int | None = None
    status: str = "pending"  # pending | processing | done | error
    progress: float = 0.0  # 0.0 - 1.0
    error: str | None = None


# ==================== 视频请求/响应 ====================

@dataclass
class VideoGenerationRequest:
    """视频生成请求"""
    prompt: str
    output_path: Path | None = None
    negative_prompt: str = ""
    duration: int = 5
    resolution: str = "720p"
    aspect_ratio: str = "9:16"
    model: str = ""
    provider: str = ""
    seed: int | None = None
    fps: int = 24
    start_image: Path | None = None
    end_image: Path | None = None
    reference_images: list[Path] | None = None
    generate_audio: bool = True


@dataclass
class VideoGenerationResult:
    """视频生成结果"""
    success: bool
    video_path: Path | None = None
    task_id: str = ""
    url: str = ""
    status: str = "pending"
    progress: int = 0
    progress_message: str = ""
    cost: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""
    model: str = ""
    duration_seconds: int = 5
    seed: int | None = None
    usage_tokens: int | None = None
    error: str = ""


# ==================== LLM 请求/响应 ====================

@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str | list[dict]  # 支持纯文本或多模态数组（[{"type": "text", "text": ...}, {"type": "image_url", "image_url": {"url": ...}}]）


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
    def capabilities(self) -> set[ImageCapability]: ...
    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
    async def health_check(self) -> bool: ...


class VideoBackend(Protocol):
    """视频生成后端接口"""
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set[VideoCapability]: ...
    async def generate(self, req: VideoGenerationRequest) -> VideoGenerationResult: ...
    async def poll(self, task_id: str) -> VideoGenerationResult: ...
    async def health_check(self) -> bool: ...


class LLMBackend(Protocol):
    """LLM 后端接口"""
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set[LLMCapability]: ...
    async def chat(self, messages: list[LLMMessage], **kwargs) -> LLMGenerationResult: ...
    async def structured_output(self, schema: dict, prompt: str) -> dict: ...


# ==================== 工具函数 ====================

async def poll_with_retry(
    *,
    poll_fn: Callable[[], Awaitable[T]],
    is_done: Callable[[T], bool],
    is_failed: Callable[[T], str | None],
    poll_interval: float = 10.0,
    max_wait: float = 600.0,
    label: str = "",
    on_progress: Callable[[T, float], None] | None = None,
) -> T:
    """
    通用异步轮询辅助函数，带超时控制。

    参考 ArcReel 的 poll_with_retry 实现。
    """
    start = time.monotonic()
    prefix = f"{label} " if label else ""

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= max_wait:
            raise TimeoutError(f"{prefix}任务超时（{max_wait:.0f}秒）")

        await asyncio.sleep(poll_interval)

        result = await poll_fn()

        error_msg = is_failed(result)
        if error_msg is not None:
            raise RuntimeError(error_msg)

        if is_done(result):
            return result

        if on_progress is not None:
            on_progress(result, elapsed)


async def download_file(url: str, output_path: Path, *, timeout: int = 120) -> None:
    """从 URL 下载文件到本地"""
    await asyncio.to_thread(output_path.parent.mkdir, parents=True, exist_ok=True)
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, timeout=timeout) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                chunks.append(chunk)

            def _write_all() -> None:
                with open(output_path, "wb") as f:
                    for chunk in chunks:
                        f.write(chunk)

            await asyncio.to_thread(_write_all)


# ==================== 图片 MIME 类型映射 ====================

IMAGE_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
