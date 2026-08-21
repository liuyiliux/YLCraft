"""
YLCraft — AI 领域数据类型

统一管理 AI 相关的枚举、数据类、请求/响应结构。
从 app.core.contracts.types 迁移并扩展。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, TypeVar

import httpx

logger = logging.getLogger("ylcraft.ai.types")

T = TypeVar("T")


# ==================== 媒体类型 ====================

class StrEnum(str, Enum):
    """兼容 Python 3.9 的 StrEnum"""
    pass


class MediaType(StrEnum):
    LLM = "llm"
    IMAGE = "image"
    VIDEO = "video"
    TTS = "tts"


# ==================== Backend 能力枚举 ====================

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


# ==================== LLM 请求/响应 ====================

@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str | list[dict]  # 支持纯文本或多模态数组


@dataclass
class LLMGenerationResult:
    success: bool
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    cost: float = 0.0
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    error: str | None = None


# ==================== 图片请求/响应 ====================

@dataclass
class ImageGenerationRequest:
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
    source_image: str = ""
    steps: int = 20
    cfg_scale: float = 7.0
    batch_size: int = 1
    sampler: str = "euler"
    lora: str = ""
    controlnet: str = ""
    prompt_id: str = ""


@dataclass
class ImageGenerationResult:
    success: bool
    image_path: Path | None = None
    url: str | None = None
    urls: list[str] | None = None
    local_path: str | None = None
    all_local_paths: list[str] | None = None
    task_id: str = ""
    prompt_id: str = ""
    cost: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""
    model: str = ""
    seed: int | None = None
    usage_tokens: int | None = None
    status: str = "pending"
    progress: float = 0.0
    error: str | None = None


# ==================== 视频请求/响应 ====================

@dataclass
class VideoGenerationRequest:
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
    start_image: Path | str | None = None
    end_image: Path | None = None
    reference_images: list[Path] | None = None
    generate_audio: bool = True
    await_completion: bool = False


@dataclass
class VideoGenerationResult:
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
    diagnostics: dict = field(default_factory=dict)


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
    async def poll(self, task_id: str) -> ImageGenerationResult: ...
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


# ==================== Backend 信息（供前端使用） ====================

@dataclass
class BackendInfo:
    """Backend 信息，供 API 返回给前端选择"""
    provider: str
    provider_label: str
    name: str
    model: str
    available_models: list[str] = field(default_factory=list)
    support_reference_image: bool = False
    supported_sizes: list[str] = field(default_factory=list)
    support_vision_input: bool = False


# ==================== 视频能力描述 ====================

@dataclass
class VideoCapabilities:
    """视频后端支持的具体能力"""
    first_frame: bool = True
    last_frame: bool = False
    reference_images: bool = False
    max_reference_images: int = 0
    max_duration: int = 10
    supported_resolutions: list[str] = field(default_factory=list)
    supported_aspect_ratios: list[str] = field(default_factory=list)
    supported_durations: list[int] = field(default_factory=list)


# ==================== 图片 MIME 类型映射 ====================

IMAGE_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


# ==================== 工具函数 ====================

def image_to_base64_data_uri(image_path: Path) -> str:
    """将本地图片转为 base64 data URI。"""
    suffix = image_path.suffix.lower()
    mime_type = IMAGE_MIME_TYPES.get(suffix, "image/png")
    image_data = image_path.read_bytes()
    b64 = base64.b64encode(image_data).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


async def download_file(url: str, output_path: Path, *, timeout: int = 120) -> None:
    """从 URL 下载文件到本地"""
    await asyncio.to_thread(output_path.parent.mkdir, parents=True, exist_ok=True)
    async with httpx.AsyncClient(trust_env=False) as client:
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
