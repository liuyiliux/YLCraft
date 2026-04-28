"""
YLCraft — 统一模型调度器

BackendManager：从 YAML 加载配置并实例化各类型 Backend。
参考 ArcReel 的 Registry + Provider 注册表设计。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from app.core.contracts.types import (
    MediaType,
    LLMMessage,
    LLMGenerationResult,
    ImageGenerationRequest,
    ImageGenerationResult,
    VideoGenerationRequest,
    VideoGenerationResult,
)

logger = logging.getLogger("ylcraft.llm")


# =============================================================================
# Backend 实现映射（YAML key → 实现类）
# =============================================================================

def _load_image_backends():
    """按需导入 Image Backend 实现类"""
    from app.services.image.minimax import MinimaxImageBackend
    return {
        "seedance": MinimaxImageBackend,
        "minimax-image": MinimaxImageBackend,
    }


def _load_video_backends():
    """按需导入 Video Backend 实现类"""
    from app.services.video_gen.minimax import MinimaxVideoBackend
    return {
        "minimax-video": MinimaxVideoBackend,
        "seedance-video": MinimaxVideoBackend,
    }


# =============================================================================
# BackendManager
# =============================================================================

class BackendManager:
    """
    统一模型调度器

    从 YAML 加载所有 Provider 配置，按 media_type 分组。
    自动实例化对应的 Backend 实现类。
    """

    def __init__(self, config_path: str | None = None):
        self._backends: dict[MediaType, dict[str, Any]] = {mt: {} for mt in MediaType}
        self._defaults: dict[MediaType, str] = {}
        self._loaded = False
        self._config_path = config_path
        if config_path:
            self._load_from_yaml(config_path)

    def _load_from_yaml(self, config_path: str) -> None:
        """从 YAML 加载 Provider 配置并实例化后端"""
        try:
            if not os.path.exists(config_path):
                logger.warning(f"[Manager] 配置文件不存在: {config_path}")
                return
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            providers = config.get("providers", {}) if config else {}
            defaults = config.get("defaults", {}) if config else {}

            # 设置默认值
            for mt_str, key in defaults.items():
                try:
                    mt = MediaType(mt_str)
                    self._defaults[mt] = key
                except ValueError:
                    pass

            # 实例化 image backends
            image_impls = _load_image_backends()
            for key, cfg in providers.items():
                if cfg.get("media_type") == "image":
                    impl_cls = image_impls.get(key)
                    if not impl_cls:
                        logger.warning(f"[Image] 未找到实现类: {key}，跳过")
                        continue
                    api_key = self._resolve_env(cfg.get("api_key", ""))
                    if not api_key:
                        logger.warning(f"[Image] {key} 缺少 api_key，跳过")
                        continue
                    backend = impl_cls(
                        api_key=api_key,
                        api_base=cfg.get("api_base", ""),
                        model=cfg.get("model"),
                    )
                    self._backends[MediaType.IMAGE][key] = backend
                    logger.info(f"[Image] 已注册 Backend: {key}")

            # 实例化 video backends
            video_impls = _load_video_backends()
            for key, cfg in providers.items():
                if cfg.get("media_type") == "video":
                    impl_cls = video_impls.get(key)
                    if not impl_cls:
                        logger.warning(f"[Video] 未找到实现类: {key}，跳过")
                        continue
                    api_key = self._resolve_env(cfg.get("api_key", ""))
                    if not api_key:
                        logger.warning(f"[Video] {key} 缺少 api_key，跳过")
                        continue
                    backend = impl_cls(
                        api_key=api_key,
                        api_base=cfg.get("api_base", ""),
                        model=cfg.get("model"),
                    )
                    self._backends[MediaType.VIDEO][key] = backend
                    logger.info(f"[Video] 已注册 Backend: {key}")

            self._loaded = True
            logger.info(
                f"[Manager] 初始化完成 - "
                f"Image: {list(self._backends[MediaType.IMAGE].keys())}, "
                f"Video: {list(self._backends[MediaType.VIDEO].keys())}"
            )

        except Exception as e:
            logger.warning(f"[Manager] 初始化失败: {e}")

    def _resolve_env(self, value: str) -> str:
        """解析 ${ENV_VAR} 格式的环境变量引用"""
        if not value:
            return ""
        if value.startswith("${") and value.endswith("}"):
            var = value[2:-1]
            return os.environ.get(var, "")
        return value

    def is_loaded(self) -> bool:
        return self._loaded

    def get_default(self, media_type: MediaType) -> str | None:
        return self._defaults.get(media_type)

    def get_backend(self, media_type: MediaType, name: str = None) -> Any:
        key = name or self._defaults.get(media_type)
        if not key:
            return None
        return self._backends[media_type].get(key)

    def list_backends(self, media_type: MediaType) -> list[str]:
        return list(self._backends[media_type].keys())

    # -------------------------------------------------------------------------
    # LLM
    # -------------------------------------------------------------------------
    async def chat(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        **kwargs
    ) -> LLMGenerationResult:
        backend = self.get_backend(MediaType.LLM, provider)
        if not backend:
            return LLMGenerationResult(
                success=False,
                error=f"Provider not found: {provider or self._defaults.get(MediaType.LLM)}"
            )
        return await backend.chat(messages, **kwargs)

    # -------------------------------------------------------------------------
    # Image
    # -------------------------------------------------------------------------
    async def generate_image(
        self,
        req: ImageGenerationRequest,
    ) -> ImageGenerationResult:
        backends = self._backends[MediaType.IMAGE]
        if not backends:
            return ImageGenerationResult(success=False, error="没有可用的图像生成后端")

        # 优先指定 Provider
        if req.provider:
            backend = backends.get(req.provider)
            if backend:
                return await backend.generate(req)

        # 其次默认 Provider
        default_key = self._defaults.get(MediaType.IMAGE)
        if default_key and default_key in backends:
            result = await backends[default_key].generate(req)
            if result.success:
                return result

        # 最后遍历降级
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

        return ImageGenerationResult(success=False, error="所有图像生成后端均失败")

    # -------------------------------------------------------------------------
    # Video
    # -------------------------------------------------------------------------
    async def generate_video(
        self,
        req: VideoGenerationRequest,
    ) -> VideoGenerationResult:
        backends = self._backends[MediaType.VIDEO]
        if not backends:
            return VideoGenerationResult(success=False, error="没有可用的视频生成后端")

        if req.provider:
            backend = backends.get(req.provider)
            if backend:
                return await backend.generate(req)

        default_key = self._defaults.get(MediaType.VIDEO)
        if default_key and default_key in backends:
            result = await backends[default_key].generate(req)
            if result.success:
                return result

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

    async def poll_video(
        self,
        provider: str | None,
        task_id: str,
    ) -> VideoGenerationResult:
        backend = self.get_backend(MediaType.VIDEO, provider)
        if not backend:
            return VideoGenerationResult(success=False, error=f"Provider not found: {provider}")
        return await backend.poll(task_id)


# =============================================================================
# 全局单例
# =============================================================================

_manager: BackendManager | None = None


def init_manager(config_path: str | None = None) -> None:
    global _manager
    if config_path is None:
        config_path = os.environ.get(
            "YLCRAFT_CONFIG",
            "F:/PycharmProjects/YLCraft/backend/config/providers.yaml"
        )
    _manager = BackendManager(config_path)


def get_manager() -> BackendManager:
    global _manager
    if _manager is None:
        init_manager()
    return _manager
