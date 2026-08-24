"""
YLCraft — AI Backend 路由器

负责：根据请求参数（backend_name / model / provider）选择最合适的 Backend。
设计原则：只负责"选择"，不负责"注册"（注册逻辑在 registry.py）
"""

from __future__ import annotations

import json
import logging
import html
from typing import Any, Optional

from app.services.ai.types import (
    MediaType,
    LLMGenerationResult,
    ImageGenerationRequest,
    ImageGenerationResult,
    VideoGenerationRequest,
    VideoGenerationResult,
    ImageCapability,
)

logger = logging.getLogger("ylcraft.ai.router")


def _clean_identifier(value: Any) -> str:
    """Normalize UI/API identifiers before matching connector names and models."""
    if value is None:
        return ""
    return html.unescape(str(value)).replace("\u00a0", " ").strip()


class BackendRouter:
    """
    AI Backend 路由器

    为每个 media_type 提供统一的选择 + 回退策略。
    """

    def __init__(self, registry):
        self._registry = registry

    # -------------------------------------------------------------------------
    # LLM 路由
    # -------------------------------------------------------------------------

    def resolve_llm(
        self,
        backend_name: str | None = None,
        model: str | None = None,
    ) -> tuple[Any, str | None]:
        """
        解析 LLM Backend 和模型。

        优先级：
        1. 指定 backend_name → 使用该 Backend
        2. 指定 model → 在已注册 Backend 中查找支持该模型的
        3. 使用系统默认 Backend
        4. 使用第一个可用的 Backend

        Returns:
            (backend, target_model) 或 (None, None)
        """
        backend = None
        backend_name = _clean_identifier(backend_name) or None
        model = _clean_identifier(model) or None
        target_model = model
        backends = self._registry.get_all_backends(MediaType.LLM)

        if not backends:
            return None, None

        # 1. 按名称查找
        if backend_name:
            backend = backends.get(backend_name)
            if not backend:
                normalized_backend_name = backend_name.casefold()
                backend = next(
                    (candidate for name, candidate in backends.items()
                     if _clean_identifier(name).casefold() == normalized_backend_name),
                    None,
                )
            if backend:
                if not model and hasattr(backend, 'connector'):
                    target_model = getattr(backend.connector, 'default_model', None)
            else:
                # API callers historically pass either the registered connector
                # name or its provider name. Resolve the latter only when it is
                # unambiguous, preferring a candidate that explicitly supports
                # the requested model.
                provider_matches = [
                    candidate
                    for candidate in backends.values()
                    if getattr(getattr(candidate, "connector", None), "provider", None) == backend_name
                ]
                if model and provider_matches:
                    for candidate in provider_matches:
                        connector = getattr(candidate, "connector", None)
                        available_models = getattr(connector, "available_models", None)
                        if _clean_identifier(getattr(connector, "default_model", None)).casefold() == model.casefold():
                            backend = candidate
                            break
                        if available_models:
                            try:
                                if any(_clean_identifier(item).casefold() == model.casefold() for item in json.loads(available_models)):
                                    backend = candidate
                                    break
                            except Exception:
                                continue
                if not backend and len(provider_matches) == 1:
                    backend = provider_matches[0]
                if backend:
                    logger.info("[Router] 根据 provider 别名找到 LLM Backend: %s", getattr(backend, "name", backend_name))
                    if not model and hasattr(backend, "connector"):
                        target_model = getattr(backend.connector, "default_model", None)
                else:
                    logger.warning(f"[Router] 未找到指定的 LLM Backend: {backend_name}")

        # 2. 按模型查找
        if not backend and model:
            for name, b in backends.items():
                if hasattr(b, 'connector'):
                    conn = b.connector
                    if _clean_identifier(getattr(conn, 'default_model', None)).casefold() == model.casefold():
                        backend = b
                        logger.info(f"[Router] 根据 default_model 找到 LLM Backend: {name}")
                        break
                    available_str = getattr(conn, 'available_models', None)
                    if available_str:
                        try:
                            available = json.loads(available_str)
                            if any(_clean_identifier(item).casefold() == model.casefold() for item in available):
                                backend = b
                                logger.info(f"[Router] 根据 available_models 找到 LLM Backend: {name}")
                                break
                        except Exception:
                            pass

        # 3. 默认 / 第一个可用
        if not backend:
            default_name = self._registry.get_default(MediaType.LLM)
            backend = backends.get(default_name) if default_name else None
            if not backend:
                first = next(iter(backends.keys()), None)
                if first:
                    backend = backends[first]
                    if not target_model and hasattr(backend, 'connector'):
                        target_model = getattr(backend.connector, 'default_model', None)

        return backend, target_model

    # -------------------------------------------------------------------------
    # Image 路由
    # -------------------------------------------------------------------------

    async def resolve_image(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """解析 Image Backend，含回退策略（异步）"""
        backends = self._registry.get_all_backends(MediaType.IMAGE)
        if not backends:
            return ImageGenerationResult(success=False, error="没有可用的图像生成后端")

        is_img2img = bool(req.source_image or req.reference_images)

        # 1. 指定 provider
        if req.provider:
            backend = backends.get(req.provider)
            if not backend:
                return ImageGenerationResult(
                    success=False,
                    error=f"指定的 Provider '{req.provider}' 不存在或未启用"
                )
            if is_img2img and not self._supports_img2img(backend):
                return ImageGenerationResult(
                    success=False,
                    error=f"指定的 Provider '{req.provider}' 不支持图生图功能"
                )
            return await backend.generate(req)

        # 2. 默认 provider
        default_key = self._registry.get_default(MediaType.IMAGE)
        if default_key and default_key in backends:
            backend = backends[default_key]
            if not is_img2img or self._supports_img2img(backend):
                result = await backend.generate(req)
                if result.success:
                    return result

        # 3. 遍历降级
        for key, backend in backends.items():
            if key == default_key:
                continue
            if is_img2img and not self._supports_img2img(backend):
                continue
            try:
                if await backend.health_check():
                    result = await backend.generate(req)
                    if result.success:
                        return result
            except Exception:
                continue

        if is_img2img:
            return ImageGenerationResult(success=False, error="没有支持图生图功能的图像生成后端")
        return ImageGenerationResult(success=False, error="所有图像生成后端均失败")

    def _supports_img2img(self, backend: Any) -> bool:
        """检查后端是否支持图生图"""
        try:
            caps = getattr(backend, 'capabilities', set())
            return "image_to_image" in caps or ImageCapability.IMAGE_TO_IMAGE in caps
        except Exception:
            return False

    async def resolve_image_poll(self, provider: Optional[str], task_id: str) -> ImageGenerationResult:
        """轮询图像生成任务状态（异步 API 如 ModelScope）。"""
        backend = self._resolve_image_backend(provider)
        if not backend:
            return ImageGenerationResult(success=False, error="没有可用的图像生成后端")
        try:
            return await backend.poll(task_id)
        except Exception as e:
            logger.error(f"[Router] 图像轮询异常: {e}")
            return ImageGenerationResult(success=False, error=str(e))

    def _resolve_image_backend(self, provider: Optional[str] = None) -> Any | None:
        """根据 provider 查找图像后端实例。"""
        backends = self._registry.get_all_backends(MediaType.IMAGE)
        if not backends:
            return None
        if provider and provider in backends:
            return backends[provider]
        default_key = self._registry.get_default(MediaType.IMAGE)
        if default_key and default_key in backends:
            return backends[default_key]
        # 取第一个可用
        for backend in backends.values():
            return backend
        return None

    # -------------------------------------------------------------------------
    # Video 路由
    # -------------------------------------------------------------------------

    async def resolve_video(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        """解析 Video Backend，含回退策略（异步）"""
        backends = self._registry.get_all_backends(MediaType.VIDEO)
        if not backends:
            return VideoGenerationResult(success=False, error="没有可用的视频生成后端")

        # 1. 指定 provider
        if req.provider:
            backend = backends.get(req.provider)
            if backend:
                return await backend.generate(req)

        # 2. 默认 provider
        default_key = self._registry.get_default(MediaType.VIDEO)
        if default_key and default_key in backends:
            result = await backends[default_key].generate(req)
            if result.success:
                return result

        # 3. 遍历降级
        for key, backend in backends.items():
            if key == default_key:
                continue
            try:
                if await backend.health_check():
                    result = await backend.generate(req)
                    if result.success:
                        return result
            except Exception:
                continue

        return VideoGenerationResult(success=False, error="所有视频生成后端均失败")

    async def resolve_video_poll(self, provider: str | None, task_id: str) -> VideoGenerationResult:
        """解析 Video poll Backend（异步）"""
        backend = self._registry.get_backend(MediaType.VIDEO, provider)
        if not backend:
            return VideoGenerationResult(success=False, error=f"Provider not found: {provider}")
        return await backend.poll(task_id)
