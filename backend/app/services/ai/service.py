"""
YLCraft — AI 服务编排层

负责：业务流程编排（权限、日志、用量统计等横切关注点）。
不负责：Backend 选择（委托给 BackendRouter）、Backend 注册（委托给 BackendRegistry）

使用方式：
    # 启动时
    AIService.initialize(config_path, session=db_session)

    # 运行时
    service = get_ai_service()
    result = await service.chat(messages, ...)
"""

from __future__ import annotations

import logging
from typing import Optional

from app.services.ai.types import (
    LLMMessage,
    LLMGenerationResult,
    ImageGenerationRequest,
    ImageGenerationResult,
    VideoGenerationRequest,
    VideoGenerationResult,
    MediaType,
)

logger = logging.getLogger("ylcraft.ai.service")


def _coerce_message(message: LLMMessage | dict) -> LLMMessage:
    """Normalize a chat message to an ``LLMMessage``.

    Several callers (clip services, planner, subagents) pass raw OpenAI-style
    dicts instead of ``LLMMessage`` instances.  Normalizing at this boundary
    keeps every backend from having to defend against both shapes.
    """
    if isinstance(message, LLMMessage):
        return message
    if isinstance(message, dict):
        return LLMMessage(
            role=str(message.get("role") or "user"),
            content=message.get("content") or "",
        )
    return LLMMessage(
        role=str(getattr(message, "role", "user") or "user"),
        content=getattr(message, "content", "") or "",
    )


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_ai_service: AIService | None = None


def get_ai_service() -> AIService:
    """获取全局 AIService 实例（必须先调用 AIService.initialize() 初始化）"""
    global _ai_service
    if _ai_service is None:
        raise RuntimeError("AIService not initialized. Call AIService.initialize() first.")
    return _ai_service


class AIService:
    """
    AI 服务编排层

    统一入口，对外提供 chat / generate_image / generate_video 等接口。
    内部委托给 BackendRegistry（注册）和 BackendRouter（选择）。
    """

    def __init__(self, registry, router):
        self._registry = registry
        self._router = router

    # -------------------------------------------------------------------------
    # 全局单例管理
    # -------------------------------------------------------------------------

    @classmethod
    def initialize(
        cls,
        config_path: str | None = None,
        session=None,
    ) -> AIService:
        """
        初始化全局 AIService 实例。

        Args:
            config_path: providers.yaml 路径（可选，用于 Video/ComfyUI 等非 DB 配置）
            session: 数据库 session（用于加载 AIConnector 表）

        Returns:
            初始化后的 AIService 实例
        """
        global _ai_service

        from app.services.ai.backends.registry import BackendRegistry
        from app.services.ai.backends.router import BackendRouter

        registry = BackendRegistry()
        registry.load_all(config_path=config_path, session=session)

        router = BackendRouter(registry)

        _ai_service = cls(registry=registry, router=router)
        logger.info(
            "AIService initialized: LLM=%d, Image=%d, Video=%d",
            len(registry.get_all_backends(MediaType.LLM)),
            len(registry.get_all_backends(MediaType.IMAGE)),
            len(registry.get_all_backends(MediaType.VIDEO)),
        )
        return _ai_service

    @classmethod
    def get_instance(cls) -> AIService:
        """获取全局 AIService 实例（同 get_ai_service()）"""
        return get_ai_service()

    # -------------------------------------------------------------------------
    # 状态检查
    # -------------------------------------------------------------------------

    def is_loaded(self) -> bool:
        """检查 Backend 是否已加载（兼容旧 BackendManager 接口）"""
        return True  # AIService 创建即表示已加载

    # -------------------------------------------------------------------------
    # LLM
    # -------------------------------------------------------------------------

    async def chat(
        self,
        messages: list[LLMMessage],
        backend_name: str | None = None,
        model: str | None = None,
        **kwargs
    ) -> LLMGenerationResult:
        """
        调用 LLM 生成响应。

        Args:
            messages: 消息列表
            backend_name: 指定 Backend 名称（可选）
            model: 指定模型（可选，会覆盖 Backend 默认模型）
        """
        # 兼容旧代码：provider 作为 backend_name 的别名
        if not backend_name and 'provider' in kwargs:
            backend_name = kwargs.pop('provider')

        backend, target_model = self._router.resolve_llm(
            backend_name=backend_name,
            model=model,
        )

        if not backend:
            return LLMGenerationResult(
                success=False,
                error=f"No available LLM Backend. Backend: {backend_name}, Model: {model}",
                model=model or "",
                provider="",
            )

        backend_label = getattr(backend, 'name', 'unknown')
        logger.info("[AIService] 调用 LLM Backend: %s, 模型: %s", backend_label, target_model or 'default')

        normalized = [_coerce_message(m) for m in messages]
        return await backend.chat(normalized, model=target_model, **kwargs)

    # -------------------------------------------------------------------------
    # Image
    # -------------------------------------------------------------------------

    async def generate_image(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """生成图片"""
        logger.info("[AIService] 图片生成请求: provider=%s, model=%s", req.provider, req.model)
        result = await self._router.resolve_image(req)
        if result.success:
            logger.info("[AIService] 图片生成成功: provider=%s", result.provider)
        else:
            logger.warning("[AIService] 图片生成失败: %s", result.error)
        return result

    # -------------------------------------------------------------------------
    # Video
    # -------------------------------------------------------------------------

    async def generate_video(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        """生成视频"""
        logger.info("[AIService] 视频生成请求: provider=%s", req.provider)
        result = await self._router.resolve_video(req)
        if result.success:
            logger.info("[AIService] 视频生成成功: provider=%s", result.provider)
        else:
            logger.warning("[AIService] 视频生成失败: %s", result.error)
        return result

    async def poll_video(self, provider: str | None, task_id: str) -> VideoGenerationResult:
        """轮询视频生成任务状态"""
        return await self._router.resolve_video_poll(provider, task_id)

    async def poll_image(self, provider: str | None, task_id: str) -> ImageGenerationResult:
        """轮询图像生成任务状态（异步 API 如 ModelScope）"""
        return await self._router.resolve_image_poll(provider, task_id)

    # -------------------------------------------------------------------------
    # 查询接口
    # -------------------------------------------------------------------------

    def list_backends(self, media_type) -> list[str]:
        """列出指定类型的 Backend 名称"""
        return self._registry.list_backends(media_type)

    def get_backend(self, media_type, name: str):
        """
        获取指定 Backend 实例（供 comfyui 等直接访问）。

        Args:
            media_type: MediaType 枚举值
            name: Backend 名称，如 "comfyui-image"

        Returns:
            Backend 实例，未找到返回 None
        """
        backends = self._registry.get_all_backends(media_type)
        return backends.get(name)

    def get_default(self, media_type):
        """
        获取指定类型的默认 Backend。

        Args:
            media_type: MediaType 枚举值

        Returns:
            默认 Backend 实例，未找到返回 None
        """
        from app.services.ai.backends.registry import get_default_backend
        return get_default_backend(self._registry, media_type)

    def get_backend_info(self, media_type) -> list:
        """
        获取 Backend 信息列表（供前端选择）。

        Returns:
            list[BackendInfo]
        """
        from app.services.ai.types import BackendInfo

        backends = self._registry.get_all_backends(media_type)
        result = []
        for name, backend in backends.items():
            if hasattr(backend, 'connector'):
                conn = backend.connector
                available_models = []
                available_str = getattr(conn, 'available_models', None)
                if available_str:
                    try:
                        import json
                        available_models = json.loads(available_str)
                    except Exception:
                        pass

                supported_sizes = []
                sizes_str = getattr(conn, 'supported_sizes', None)
                if sizes_str:
                    try:
                        import json
                        supported_sizes = json.loads(sizes_str)
                    except Exception:
                        pass

                result.append(BackendInfo(
                    provider=conn.provider or "",
                    provider_label=getattr(conn, 'provider_label', None) or conn.provider or "",
                    name=conn.name,
                    model=getattr(conn, 'default_model', '') or '',
                    available_models=available_models,
                    support_reference_image=bool(getattr(conn, 'support_reference_image', False)),
                    supported_sizes=supported_sizes,
                    support_vision_input=bool(getattr(conn, 'support_vision_input', False)),
                ))
        return result
