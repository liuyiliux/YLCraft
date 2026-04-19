"""
YLCraft — LLM Manager

BackendManager：统一模型调度器，参考 ArcReel Registry + Provider 注册表设计。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.contracts.types import (
    MediaType,
    LLMMessage,
    LLMGenerationResult,
    ImageGenerationRequest,
    ImageGenerationResult,
)

logger = logging.getLogger("ylcraft.llm")


class BackendManager:
    """
    统一模型调度器（当前为最小化实现，Provider 注册表待完成）

    提供：
    - chat() — LLM 对话
    - generate_image() — 图片生成
    - get_default(media_type) — 获取默认后端
    - is_loaded() — 是否已加载配置
    """

    def __init__(self, config_path: str = "config/providers.yaml"):
        self._backends: dict[MediaType, dict[str, Any]] = {mt: {} for mt in MediaType}
        self._defaults: dict[MediaType, str] = {}
        self._loaded = False
        self._config_path = config_path
        self._load_from_yaml(config_path)

    def _load_from_yaml(self, config_path: str) -> None:
        """从 YAML 加载 Provider 配置并初始化后端"""
        try:
            import os
            import yaml
            if not os.path.exists(config_path):
                logger.warning(f"[LLM] 配置文件不存在: {config_path}，使用空配置")
                return
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            providers = config.get("providers", {}) if config else {}
            for key, cfg in providers.items():
                mt_str = cfg.get("media_type", "")
                try:
                    mt = MediaType(mt_str)
                except ValueError:
                    continue
                default_model = cfg.get("default_model", "")
                if default_model:
                    self._defaults[mt] = default_model
            self._loaded = True
            logger.info(f"[LLM] BackendManager 初始化完成，默认 LLM: {self._defaults.get(MediaType.LLM, '无')}")
        except Exception as e:
            logger.warning(f"[LLM] BackendManager 初始化失败: {e}，使用空配置")

    def is_loaded(self) -> bool:
        return self._loaded

    def get_default(self, media_type: MediaType):
        """获取指定媒体类型的默认后端名称"""
        return self._defaults.get(media_type)

    def get_backend(self, media_type: MediaType, name: str = None):
        """获取 Backend：指定名称或默认"""
        key = name or self._defaults.get(media_type)
        if not key:
            return None
        return self._backends[media_type].get(key)

    async def chat(
        self,
        messages: list[LLMMessage],
        provider: str = None,
        **kwargs
    ) -> LLMGenerationResult:
        """对话：指定 Provider 或默认"""
        backend = self.get_backend(MediaType.LLM, provider)
        if not backend:
            return LLMGenerationResult(
                success=False,
                error=f"Provider not found: {provider or self._defaults.get(MediaType.LLM)}"
            )
        return await backend.chat(messages, **kwargs)

    async def generate_image(
        self,
        req: ImageGenerationRequest,
    ) -> ImageGenerationResult:
        """生成图片（当前为 stub）"""
        return ImageGenerationResult(
            success=False,
            error="Image generation not configured"
        )


# 全局单例
_manager: BackendManager | None = None


def init_manager(config_path: str = None) -> None:
    """初始化 BackendManager（可指定配置文件路径）"""
    global _manager
    if config_path is None:
        import os
        config_path = os.environ.get(
            "YLCRAFT_CONFIG",
            "F:/PycharmProjects/YLCraft/backend/config/providers.yaml"
        )
    _manager = BackendManager(config_path)


def get_manager() -> BackendManager:
    """获取 BackendManager 全局单例"""
    global _manager
    if _manager is None:
        init_manager()
    return _manager
