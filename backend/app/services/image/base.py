"""
YLCraft — 图像生成 Backend 基类

参考 ArcReel 的 image_backends/base.py 设计。
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.contracts.types import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageCapability,
    IMAGE_MIME_TYPES,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ylcraft.image.base")


def image_to_base64_data_uri(image_path: Path) -> str:
    """将本地图片转为 base64 data URI。"""
    suffix = image_path.suffix.lower()
    mime_type = IMAGE_MIME_TYPES.get(suffix, "image/png")
    image_data = image_path.read_bytes()
    b64 = base64.b64encode(image_data).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


class BaseImageBackend(ABC):
    """
    图像生成后端基类。

    子类只需实现 _generate() 方法，generate() 已由基类提供统一错误处理。
    """

    def __init__(
        self,
        name: str,
        model: str,
        api_key: str,
        api_base: str,
        cost_per_call: float = 0.0,
    ):
        self._name = name
        self._model = model
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._cost_per_call = cost_per_call
        self._capabilities: set[ImageCapability] = {ImageCapability.TEXT_TO_IMAGE}

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return self._capabilities

    async def health_check(self) -> bool:
        """健康检查：子类可覆盖"""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._api_base}/health")
                return resp.status_code < 500
        except Exception:
            return False

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """
        标准生成流程：子类实现 _generate() 即可。

        基类负责：
        - 错误捕获
        - cost / latency 记录
        - 返回值标准化
        """
        import time

        start = time.perf_counter()
        try:
            result = await self._generate(req)
            result.latency_ms = (time.perf_counter() - start) * 1000
            result.provider = self._name
            result.model = self._model
            if result.cost == 0:
                result.cost = self._cost_per_call
            return result
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error(f"[{self._name}] generate failed: {e}")
            return ImageGenerationResult(
                success=False,
                error=str(e),
                cost=self._cost_per_call,
                latency_ms=latency_ms,
                provider=self._name,
                model=self._model,
            )

    @abstractmethod
    async def _generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """子类实现此方法，调用对应的图像生成 API。"""
        ...
