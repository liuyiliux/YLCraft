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

import contextvars
import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

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

# ---------------------------------------------------------------------------
# 调用上下文与统一事件收口
#
# 事件日志此前只在各端点手写（images/videos/model3d/llm 等约 43 处），
# 任何没手写的路径（世界地图 AI 生图、批量生图、agent 工具、Live2D 等）
# 就完全不可观测。这里把记录下沉到 AIService 三个必经入口：
# 语义最完整（能拿到 scene/provider/model/耗时/错误），且 Router 内部
# 的多次降级只算一次调用。业务身份（project_id / ref_id / 自定义场景）
# 由调用方用 ai_call_context 注入。
# ---------------------------------------------------------------------------

_ai_call_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "ylcraft_ai_call_context", default={}
)

#: 请求/响应摘要的字符上限：只为排障留线索，不是事实来源（正典在实体/资产里）。
_EVENT_SUMMARY_CHARS = 2000


@contextmanager
def ai_call_context(
    *,
    project_id: str | None = None,
    ref_id: str | None = None,
    task_id: str | None = None,
    scene: str | None = None,
    task_type: str | None = None,
    label: str = "",
    retry_payload: dict[str, Any] | None = None,
    suppress_auto_event: bool = False,
) -> Iterator[None]:
    """给当前上下文里的 AI 调用注入业务身份，自动落事件日志时一并带上。

    Args:
        project_id: 关联项目（决定事件能否出现在项目视图里）
        ref_id: 关联业务对象（角色 id、地图 id 等）
        scene / task_type: 覆盖默认技术场景归类
        label: 事件标题，缺省用「<task_type> 成功/失败」
        retry_payload: 事件日志「重发」所需的原始请求负载。端点层删掉手写
            record_event 后，重发能力靠这里兜住——缺了它重发会失效。
        suppress_auto_event: 端点自己已写业务事件时置 True，避免重复记账
    """
    token = _ai_call_context.set(
        {
            "project_id": project_id,
            "ref_id": ref_id,
            "task_id": task_id,
            "scene": scene,
            "task_type": task_type,
            "label": label,
            "retry_payload": retry_payload,
            "suppress_auto_event": suppress_auto_event,
        }
    )
    try:
        yield
    finally:
        _ai_call_context.reset(token)


def _summarize_messages(messages: Any) -> str:
    """把消息列表压成可排障的摘要（角色 + 截断内容）。"""
    if not isinstance(messages, (list, tuple)):
        return ""
    parts: list[str] = []
    for item in messages:
        role = getattr(item, "role", None) or (
            item.get("role") if isinstance(item, dict) else "user"
        )
        content = getattr(item, "content", None)
        if content is None and isinstance(item, dict):
            content = item.get("content")
        parts.append(f"[{role}] {str(content or '')[:_EVENT_SUMMARY_CHARS]}")
    return "\n".join(parts)[:_EVENT_SUMMARY_CHARS]


def _summarize_result(result: Any) -> str:
    """生成结果的摘要：文本取内容，图片/视频取 URL 或任务 id。"""
    if result is None:
        return ""
    content = getattr(result, "content", None)
    if content:
        return str(content)[:_EVENT_SUMMARY_CHARS]
    for attr in ("images", "urls", "video_url", "task_id", "remote_task_id"):
        value = getattr(result, attr, None)
        if value:
            return f"{attr}={str(value)[:_EVENT_SUMMARY_CHARS]}"
    return ""


async def _emit_call_event(
    *,
    scene: str,
    task_type: str,
    provider: str = "",
    model: str = "",
    ok: bool,
    error: str | None = None,
    duration_ms: int = 0,
    request_text: str = "",
    response_text: str = "",
) -> None:
    """把一次 AI 调用落到平台事件日志（best-effort，失败绝不影响调用本身）。"""
    ctx = _ai_call_context.get() or {}
    if ctx.get("suppress_auto_event"):
        return
    try:
        from app.services.platform_log.service import record_event

        await record_event(
            scene=ctx.get("scene") or scene,
            task_type=ctx.get("task_type") or task_type,
            task_id=ctx.get("task_id"),
            level="info" if ok else "error",
            status="success" if ok else "failed",
            provider=provider or "",
            model=model or "",
            message=ctx.get("label") or (f"{task_type} 成功" if ok else f"{task_type} 失败"),
            error=error,
            request={"prompt": request_text} if request_text else None,
            response={"output": response_text} if response_text else None,
            duration_ms=duration_ms,
            project_id=ctx.get("project_id"),
            ref_id=ctx.get("ref_id"),
            retry_payload=ctx.get("retry_payload"),
        )
    except Exception:  # pragma: no cover - 记录失败不能打断 AI 调用
        logger.debug("[AIService] 事件日志写入失败（已忽略）", exc_info=True)


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

        started = time.perf_counter()
        backend, target_model = self._router.resolve_llm(
            backend_name=backend_name,
            model=model,
        )

        if not backend:
            error = f"No available LLM Backend. Backend: {backend_name}, Model: {model}"
            await _emit_call_event(
                scene="llm",
                task_type="llm_chat",
                provider=str(backend_name or ""),
                model=model or "",
                ok=False,
                error=error,
                duration_ms=int((time.perf_counter() - started) * 1000),
                request_text=_summarize_messages(messages),
            )
            return LLMGenerationResult(
                success=False,
                error=error,
                model=model or "",
                provider="",
            )

        backend_label = getattr(backend, 'name', 'unknown')
        logger.info("[AIService] 调用 LLM Backend: %s, 模型: %s", backend_label, target_model or 'default')

        normalized = [_coerce_message(m) for m in messages]
        request_text = _summarize_messages(normalized)
        try:
            result = await backend.chat(normalized, model=target_model, **kwargs)
        except Exception as exc:
            # 异常照旧向上抛，只补一条失败事件，保证排障有迹可循。
            await _emit_call_event(
                scene="llm",
                task_type="llm_chat",
                provider=backend_label,
                model=target_model or "",
                ok=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
                request_text=request_text,
            )
            raise
        await _emit_call_event(
            scene="llm",
            task_type="llm_chat",
            provider=getattr(result, "provider", "") or backend_label,
            model=getattr(result, "model", "") or (target_model or ""),
            ok=bool(getattr(result, "success", True)),
            error=getattr(result, "error", None) or None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            request_text=request_text,
            response_text=_summarize_result(result),
        )
        return result

    # -------------------------------------------------------------------------
    # Image
    # -------------------------------------------------------------------------

    async def generate_image(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """生成图片"""
        logger.info("[AIService] 图片生成请求: provider=%s, model=%s", req.provider, req.model)
        started = time.perf_counter()
        try:
            result = await self._router.resolve_image(req)
        except Exception as exc:
            # 异常照旧向上抛，只补一条失败事件——端点层的"生成异常"记录因此可以删掉。
            await _emit_call_event(
                scene="image",
                task_type="image_generation",
                provider=str(req.provider or ""),
                model=str(req.model or ""),
                ok=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
                request_text=str(getattr(req, "prompt", "") or "")[:_EVENT_SUMMARY_CHARS],
            )
            raise
        if result.success:
            logger.info("[AIService] 图片生成成功: provider=%s", result.provider)
        else:
            logger.warning("[AIService] 图片生成失败: %s", result.error)
        await _emit_call_event(
            scene="image",
            task_type="image_generation",
            provider=getattr(result, "provider", "") or (req.provider or ""),
            model=getattr(result, "model", "") or (req.model or ""),
            ok=bool(result.success),
            error=result.error or None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            request_text=str(getattr(req, "prompt", "") or "")[:_EVENT_SUMMARY_CHARS],
            response_text=_summarize_result(result),
        )
        return result

    # -------------------------------------------------------------------------
    # Video
    # -------------------------------------------------------------------------

    async def generate_video(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        """生成视频"""
        logger.info("[AIService] 视频生成请求: provider=%s", req.provider)
        started = time.perf_counter()
        try:
            result = await self._router.resolve_video(req)
        except Exception as exc:
            await _emit_call_event(
                scene="video",
                task_type="video_generation",
                provider=str(req.provider or ""),
                model=str(getattr(req, "model", "") or ""),
                ok=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
                request_text=str(getattr(req, "prompt", "") or "")[:_EVENT_SUMMARY_CHARS],
            )
            raise
        if result.success:
            logger.info("[AIService] 视频生成成功: provider=%s", result.provider)
        else:
            logger.warning("[AIService] 视频生成失败: %s", result.error)
        await _emit_call_event(
            scene="video",
            task_type="video_generation",
            provider=getattr(result, "provider", "") or (req.provider or ""),
            model=getattr(result, "model", "") or (getattr(req, "model", "") or ""),
            ok=bool(result.success),
            error=result.error or None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            request_text=str(getattr(req, "prompt", "") or "")[:_EVENT_SUMMARY_CHARS],
            response_text=_summarize_result(result),
        )
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
