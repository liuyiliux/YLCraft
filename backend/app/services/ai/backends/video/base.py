"""
YLCraft — 视频生成 Backend 基类
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.services.ai.types import (
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoCapability,
    VideoCapabilities,
    poll_with_retry,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ylcraft.video.base")


class BaseVideoBackend(ABC):
    """
    视频生成后端基类。

    子类需实现：
    - _generate(): 创建生成任务
    - _poll(): 轮询任务状态
    """

    def __init__(
        self,
        name: str,
        model: str,
        api_key: str,
        api_base: str,
        cost_per_second: float = 0.0,
    ):
        self._name = name
        self._model = model
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._cost_per_second = cost_per_second
        self._capabilities: set[VideoCapability] = {VideoCapability.TEXT_TO_VIDEO}

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def available_models(self) -> list[str]:
        """返回可用的模型列表（子类可覆盖）"""
        return [self._model]

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    @property
    def video_capabilities(self) -> VideoCapabilities:
        return VideoCapabilities()

    @property
    def enforce_video_capabilities(self) -> bool:
        """Whether declared capability limits should reject incompatible requests."""
        return True

    async def health_check(self) -> bool:
        """健康检查：子类可覆盖"""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._api_base}/health")
                return resp.status_code < 500
        except Exception:
            return False

    async def generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        """
        标准生成流程：创建任务 + 轮询等待完成。
        """
        import time

        effective_model = req.model or self._model
        start = time.perf_counter()
        try:
            # 1. 创建任务
            result = await self._generate(req)

            # 2. 如果任务需要轮询（异步 API）
            if req.await_completion and result.status == "pending" and result.task_id:
                result = await self._poll_until_done(result.task_id, req)

            result.latency_ms = (time.perf_counter() - start) * 1000
            result.provider = self._name
            result.model = effective_model
            result.cost = self._cost_per_second * req.duration
            result.success = True
            return result

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            error = str(e) or repr(e) or e.__class__.__name__
            logger.exception("[%s] generate failed: %s", self._name, error)
            return VideoGenerationResult(
                success=False,
                error=error,
                cost=self._cost_per_second * req.duration,
                latency_ms=latency_ms,
                provider=self._name,
                model=self._model,
                diagnostics={
                    "exception_type": e.__class__.__name__,
                    "exception_repr": repr(e),
                    **getattr(e, "diagnostics", {}),
                },
            )

    @abstractmethod
    async def _generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        """子类实现：创建视频生成任务"""
        ...

    async def poll(self, task_id: str) -> VideoGenerationResult:
        """轮询任务状态"""
        return await self._poll(task_id)

    @abstractmethod
    async def _poll(self, task_id: str) -> VideoGenerationResult:
        """子类实现：轮询任务状态"""
        ...

    async def _poll_until_done(
        self, task_id: str, req: VideoGenerationRequest
    ) -> VideoGenerationResult:
        """轮询直到任务完成"""
        return await poll_with_retry(
            poll_fn=lambda: self._poll(task_id),
            is_done=lambda r: r.status == "done",
            is_failed=lambda r: r.error if r.status == "error" else None,
            poll_interval=10.0,
            max_wait=600.0,
            label=self._name,
            on_progress=lambda r, elapsed: logger.info(
                f"[{self._name}] 视频生成中... 状态: {r.status}, 已等待 {int(elapsed)} 秒"
            ),
        )
