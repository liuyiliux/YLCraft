"""
YLCraft - 统一模型调度器

BackendManager：从数据库或 YAML 加载配置并实例化各类型 Backend。
优先从数据库加载，如果数据库为空则回退到 YAML。
参考 ArcReel 的 Registry + Provider 注册表设计。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import yaml
from sqlalchemy.orm import Session

from app.core.contracts.types import (
    MediaType,
    LLMMessage,
    LLMGenerationResult,
    ImageGenerationRequest,
    ImageGenerationResult,
    VideoGenerationRequest,
    VideoGenerationResult,
    ImageCapability,
)
from app.db.models.ai_connector import AIConnector, AIProviderType

logger = logging.getLogger("ylcraft.llm")


# =============================================================================
# Backend 实现映射（YAML key → 实现类）
# =============================================================================

def _load_llm_backends():
    """按需导入 LLM Backend 实现类"""
    from app.services.llm.doubao import DoubaoLLMBackend
    return {
        "doubao-lite": DoubaoLLMBackend,
        "doubao-pro": DoubaoLLMBackend,
    }


def _load_video_backends():
    """按需导入 Video Backend 实现类"""
    from app.services.video_gen.minimax import MinimaxVideoBackend
    return {
        "minimax-video": MinimaxVideoBackend,
        "seedance-video": MinimaxVideoBackend,
    }


def _load_comfyui_backends():
    """按需导入 ComfyUI Backend 实现类"""
    try:
        from app.services.comfyui import ComfyUIImageBackend
        return {
            "comfyui-image": ComfyUIImageBackend,
        }
    except ImportError:
        logger.warning("ComfyUI module not available")
        return {}


# =============================================================================
# BackendManager
# =============================================================================

class BackendManager:
    """
    统一模型调度器

    从数据库或 YAML 加载所有 Provider 配置，按 media_type 分组。
    优先从数据库加载，如果数据库为空则回退到 YAML。
    """

    def __init__(self, config_path: str | None = None, session: Session | None = None):
        """
        初始化 BackendManager

        Args:
            config_path: YAML 配置文件路径（回退用）
            session: SQLAlchemy session（用于从数据库加载）
        """
        self._backends: dict[MediaType, dict[str, Any]] = {mt: {} for mt in MediaType}
        self._defaults: dict[MediaType, str] = {}
        self._loaded = False
        self._config_path = config_path
        self._session = session

        # 优先从数据库加载
        if session:
            try:
                self._load_from_db(session)
            except Exception as e:
                logger.warning(f"[Manager] 从数据库加载失败: {e}，尝试 YAML")
                if config_path:
                    self._load_from_yaml(config_path)
        elif config_path:
            self._load_from_yaml(config_path)

    def _load_from_db(self, session: Session) -> None:
        """从数据库加载 Provider 配置并实例化后端"""
        connectors = session.query(AIConnector).filter(AIConnector.is_active == True).all()

        if not connectors:
            logger.info("[Manager] 数据库中没有 Provider 配置，跳过")
            return

        logger.info(f"[Manager] 从数据库加载 {len(connectors)} 个 Provider...")

        for conn in connectors:
            try:
                self._init_backend_from_connector(conn, session)
            except Exception as e:
                logger.error(f"[Manager] 初始化 Provider {conn.name} 失败: {e}")
                continue

        self._loaded = True
        logger.info(
            f"[Manager] 数据库加载完成 - "
            f"LLM: {list(self._backends[MediaType.LLM].keys())}, "
            f"Image: {list(self._backends[MediaType.IMAGE].keys())}, "
            f"Video: {list(self._backends[MediaType.VIDEO].keys())}"
        )

    def _init_backend_from_connector(self, conn: AIConnector, session: Session) -> None:
        """
        根据 AIConnector 记录初始化 Backend

        Args:
            conn: AIConnector 数据库记录
            session: SQLAlchemy session
        """
        # 获取 provider_type（现在可能是字符串）
        provider_type = conn.provider_type
        if hasattr(provider_type, 'value'):
            provider_type = provider_type.value

        if provider_type == "llm":
            self._init_llm_backend(conn)
        elif provider_type == "image":
            self._init_image_backend(conn, session)
        elif provider_type == "video":
            self._init_video_backend(conn, session)
        else:
            logger.warning(f"[Manager] 未知的 provider_type: {provider_type}")

    def _init_llm_backend(self, conn: AIConnector) -> None:
        """初始化 LLM Backend（根据 api_format 路由）"""
        api_format = getattr(conn, 'api_format', 'custom')

        # openai_sdk / openai_sdk_responses 模式 → OpenAISDKLLMBackend
        if api_format.startswith('openai_sdk'):
            try:
                from app.services.llm.openai_sdk_backend import OpenAISDKLLMBackend
                backend = OpenAISDKLLMBackend(connector=conn)
                self._backends[MediaType.LLM][conn.name] = backend
                logger.info(f"[LLM] 已注册 OpenAISDKLLMBackend: {conn.name}")
                return
            except Exception as e:
                logger.warning(f"[LLM] SDK Backend 初始化失败，降级到 GenericBackend: {e}")

        # custom 模式（默认）→ GenericLLMBackend
        from app.services.llm.generic_backend import GenericLLMBackend
        try:
            backend = GenericLLMBackend(connector=conn, session=self._session)
            self._backends[MediaType.LLM][conn.name] = backend
            logger.info(f"[LLM] 已注册 GenericLLMBackend: {conn.name}")
        except Exception as e:
            logger.error(f"[LLM] 初始化 GenericLLMBackend 失败 {conn.name}: {e}")

    def _init_image_backend(self, conn: AIConnector, session: Session) -> None:
        """初始化 Image Backend（根据 provider 和 api_format 路由）"""
        api_format = getattr(conn, 'api_format', 'custom')

        # openai_sdk / openai_sdk_responses 模式 → OpenAISDKImageBackend
        if api_format.startswith('openai_sdk'):
            try:
                from app.services.image.openai_sdk_image_backend import OpenAISDKImageBackend
                backend = OpenAISDKImageBackend(connector=conn)
                self._backends[MediaType.IMAGE][conn.name] = backend
                logger.info(f"[Image] 已注册 OpenAISDKImageBackend: {conn.name}")
                return
            except Exception as e:
                logger.warning(f"[Image] SDK Backend 初始化失败，降级到 Gemini/Generic: {e}")

        # gemini provider → GeminiImageBackend（Google 原生图片生成 API）
        if conn.provider == 'gemini':
            try:
                from app.services.image.gemini_image_backend import GeminiImageBackend
                backend = GeminiImageBackend(connector=conn)
                self._backends[MediaType.IMAGE][conn.name] = backend
                logger.info(f"[Image] 已注册 GeminiImageBackend: {conn.name}")
                return
            except Exception as e:
                logger.warning(f"[Image] Gemini Backend 初始化失败，降级到 GenericBackend: {e}")

        # custom 模式（默认）→ GenericImageBackend
        from app.services.image.generic_backend import GenericImageBackend
        try:
            backend = GenericImageBackend(connector=conn, session=session)
            self._backends[MediaType.IMAGE][conn.name] = backend
            logger.info(f"[Image] 已注册 GenericImageBackend: {conn.name}")
        except Exception as e:
            import traceback
            logger.error(f"[Image] 初始化 GenericImageBackend 失败 {conn.name}: {e}")
            logger.error(traceback.format_exc())

    def _init_video_backend(self, conn: AIConnector, session: Session) -> None:
        """初始化 Video Backend"""
        video_impls = _load_video_backends()
        impl_cls = video_impls.get(conn.provider)
        if impl_cls:
            backend = impl_cls(
                api_key=conn.api_key,
                api_base=conn.base_url or "",
                model=conn.default_model,
            )
            self._backends[MediaType.VIDEO][conn.name] = backend
            logger.info(f"[Video] 已注册 Backend: {conn.name} (from DB)")
        else:
            logger.warning(f"[Video] 未找到实现类 for provider: {conn.provider}")

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

            # 注：Image backends 从数据库加载，YAML 不再支持
            # （统一使用 GenericImageBackend）

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

            # 实例化 LLM backends
            llm_impls = _load_llm_backends()
            for key, cfg in providers.items():
                if cfg.get("media_type") == "llm":
                    impl_cls = llm_impls.get(key)
                    if not impl_cls:
                        logger.warning(f"[LLM] 未找到实现类: {key}，跳过")
                        continue
                    api_key = self._resolve_env(cfg.get("api_key", ""))
                    if not api_key:
                        logger.warning(f"[LLM] {key} 缺少 api_key，跳过")
                        continue
                    backend = impl_cls(
                        api_key=api_key,
                        api_base=cfg.get("api_base", ""),
                        model=cfg.get("model"),
                    )
                    self._backends[MediaType.LLM][key] = backend
                    logger.info(f"[LLM] 已注册 Backend: {key}")

            # 实例化 ComfyUI backends
            comfyui_impls = _load_comfyui_backends()
            for key, cfg in providers.items():
                if cfg.get("media_type") == "comfyui":
                    impl_cls = comfyui_impls.get(key)
                    if not impl_cls:
                        logger.warning(f"[ComfyUI] 未找到实现类: {key}，跳过")
                        continue

                    # ComfyUI 使用 server_url 而不是 api_key
                    server_url = cfg.get("server_url", "http://127.0.0.1:8188")
                    workflow_dir = cfg.get("workflow_dir", "backend/app/services/comfyui/workflows")
                    output_dir = cfg.get("output_dir", "storage/comfyui/outputs")

                    from app.services.comfyui import ComfyUIImageConfig
                    config = ComfyUIImageConfig(
                        server_url=server_url,
                        workflow_dir=workflow_dir,
                        output_dir=output_dir,
                    )
                    backend = impl_cls(config=config)

                    # ComfyUI 可以作为 image 和 video 后端
                    media_types = cfg.get("provides", ["image"])
                    for mt in media_types:
                        try:
                            mt_enum = MediaType(mt)
                            self._backends[mt_enum][key] = backend
                            logger.info(f"[ComfyUI] 已注册 Backend: {key} for {mt}")
                        except ValueError:
                            logger.warning(f"[ComfyUI] 无效的 media_type: {mt}")

            self._loaded = True
            logger.info(
                f"[Manager] YAML 加载完成 - "
                f"LLM: {list(self._backends[MediaType.LLM].keys())}, "
                f"Image: {list(self._backends[MediaType.IMAGE].keys())}, "
                f"Video: {list(self._backends[MediaType.VIDEO].keys())}"
            )

        except Exception as e:
            logger.warning(f"[Manager] YAML 加载失败: {e}")

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

    def get_backend(self, media_type: MediaType, name: str | None = None) -> Any:
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

        # 判断是否为图生图请求
        is_img2img = bool(req.source_image or req.reference_images)

        # 优先指定 Provider
        if req.provider:
            backend = backends.get(req.provider)
            if backend:
                # 检查该后端是否支持图生图
                if is_img2img and not self._supports_img2img(backend):
                    return ImageGenerationResult(
                        success=False,
                        error=f"指定的 Provider '{req.provider}' 不支持图生图功能"
                    )
                return await backend.generate(req)

        # 其次默认 Provider
        default_key = self._defaults.get(MediaType.IMAGE)
        if default_key and default_key in backends:
            backend = backends[default_key]
            # 检查该后端是否支持图生图
            if is_img2img and not self._supports_img2img(backend):
                pass  # 默认不支持，跳过，使用其他后端
            else:
                result = await backend.generate(req)
                if result.success:
                    return result

        # 最后遍历降级
        for key, backend in backends.items():
            if key == default_key:
                continue
            # 检查图生图能力
            if is_img2img and not self._supports_img2img(backend):
                logger.debug(f"[Image] Backend '{key}' 不支持图生图，跳过")
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


def init_manager(config_path: str | None = None, session: Session | None = None) -> None:
    """初始化全局 BackendManager"""
    global _manager
    _manager = BackendManager(config_path=config_path, session=session)


def get_manager() -> BackendManager:
    global _manager
    if _manager is None:
        init_manager()
    return _manager
