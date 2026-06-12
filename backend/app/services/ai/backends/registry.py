"""
YLCraft — AI Backend 注册中心

负责：
- 从数据库 (AIConnector) 加载配置并实例化 Backend
- 从 YAML 加载 Video/ComfyUI Backend（回退）
- 提供统一的 Backend 查询接口

设计原则：单一职责 —— 只负责"注册"，不负责"选择"（选择逻辑在 router.py）
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import yaml
from sqlalchemy.orm import Session

from app.services.ai.types import MediaType
from app.db.models.ai_connector import AIConnector

logger = logging.getLogger("ylcraft.ai.registry")


# =============================================================================
# Backend 实现类映射表（api_format → 实现类）
# =============================================================================

def _load_video_backends():
    """按需导入 Video Backend 实现类"""
    from app.services.ai.backends.video.minimax import MinimaxVideoBackend
    return {
        "minimax-video": MinimaxVideoBackend,
        "seedance-video": MinimaxVideoBackend,
    }


def _load_comfyui_backends():
    """按需导入 ComfyUI Backend 实现类"""
    try:
        from app.services.comfyui.image_backend import ComfyUIImageBackend, ComfyUIImageConfig
        return {"comfyui-image": (ComfyUIImageBackend, ComfyUIImageConfig)}
    except ImportError:
        logger.warning("ComfyUI module not available")
        return {}


# =============================================================================
# Backend 路由表：根据 (media_type, api_format) 选择实现类
# =============================================================================

BACKEND_CLASS_MAP = {
    # LLM
    ("llm", "openai_sdk"): "app.services.ai.backends.llm.openai_sdk.OpenAISDKLLMBackend",
    ("llm", "openai_sdk_responses"): "app.services.ai.backends.llm.openai_sdk.OpenAISDKLLMBackend",
    ("llm", "custom"): "app.services.ai.backends.llm.generic.GenericLLMBackend",
    # Image
    ("image", "openai_sdk"): "app.services.ai.backends.image.openai_sdk.OpenAISDKImageBackend",
    ("image", "openai_sdk_responses"): "app.services.ai.backends.image.openai_sdk.OpenAISDKImageBackend",
    ("image", "gemini"): "app.services.ai.backends.image.gemini.GeminiImageBackend",
    ("image", "custom"): "app.services.ai.backends.image.generic.GenericImageBackend",
}

# 图片类 provider 特殊路由（provider == "gemini" 时优先走 gemini backend）
IMAGE_PROVIDER_OVERRIDE = {
    "gemini": "app.services.ai.backends.image.gemini.GeminiImageBackend",
}


def _import_class(dotted_path: str):
    """动态导入类"""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


# =============================================================================
# BackendRegistry
# =============================================================================

class BackendRegistry:
    """
    AI Backend 注册中心

    从数据库或 YAML 加载所有 Provider 配置，按 media_type 分组并实例化 Backend。
    """

    def __init__(self):
        self._backends: dict[MediaType, dict[str, Any]] = {mt: {} for mt in MediaType}
        self._defaults: dict[MediaType, str] = {}
        self._loaded = False

    def load_all(self, config_path: str | None = None, session: Session | None = None) -> None:
        """加载所有 Backend（DB 优先，YAML 回退）"""
        # 优先从数据库加载
        if session:
            try:
                self._load_from_db(session)
            except Exception as e:
                logger.warning(f"[Registry] 从数据库加载失败: {e}，尝试 YAML")
                if config_path:
                    self._load_from_yaml(config_path)
        elif config_path:
            self._load_from_yaml(config_path)

    # -------------------------------------------------------------------------
    # 数据库加载
    # -------------------------------------------------------------------------

    def _load_from_db(self, session: Session) -> None:
        """从数据库加载 Provider 配置并实例化后端"""
        connectors = session.query(AIConnector).filter(AIConnector.is_active == True).all()

        if not connectors:
            logger.info("[Registry] 数据库中没有 Provider 配置，跳过")
            return

        logger.info(f"[Registry] 从数据库加载 {len(connectors)} 个 Provider...")

        for conn in connectors:
            try:
                self._init_backend(conn, session)
            except Exception as e:
                logger.error(f"[Registry] 初始化 Provider {conn.name} 失败: {e}")
                continue

        self._loaded = True
        logger.info(
            f"[Registry] 数据库加载完成 - "
            f"LLM: {list(self._backends[MediaType.LLM].keys())}, "
            f"Image: {list(self._backends[MediaType.IMAGE].keys())}, "
            f"Video: {list(self._backends[MediaType.VIDEO].keys())}"
        )

    def _init_backend(self, conn: AIConnector, session: Session) -> None:
        """根据 AIConnector 记录初始化 Backend（统一入口）"""
        provider_type = conn.provider_type
        if hasattr(provider_type, 'value'):
            provider_type = provider_type.value

        if provider_type not in ("llm", "image", "video"):
            logger.warning(f"[Registry] 未知的 provider_type: {provider_type}")
            return

        media_type = MediaType(provider_type)
        api_format = getattr(conn, 'api_format', 'custom') or 'custom'

        # 图片类特殊路由：provider == "gemini" 优先走 gemini backend
        if provider_type == "image" and conn.provider in IMAGE_PROVIDER_OVERRIDE:
            class_path = IMAGE_PROVIDER_OVERRIDE[conn.provider]
        else:
            class_path = BACKEND_CLASS_MAP.get((provider_type, api_format))
            if not class_path:
                # 未匹配到，降级到 custom
                class_path = BACKEND_CLASS_MAP.get((provider_type, "custom"))

        if not class_path:
            logger.warning(f"[Registry] 未找到 Backend 实现: type={provider_type}, format={api_format}")
            return

        try:
            backend_cls = _import_class(class_path)
            import inspect
            sig = inspect.signature(backend_cls.__init__)
            if 'session' in sig.parameters:
                backend = backend_cls(connector=conn, session=session)
            else:
                backend = backend_cls(connector=conn)
            self._backends[media_type][conn.name] = backend
            if bool(getattr(conn, "is_default", False)):
                self._defaults[media_type] = conn.name
            logger.info(f"[Registry] 已注册 {provider_type.upper()} Backend: {conn.name} ({class_path.rsplit('.',1)[1]})")
        except Exception as e:
            logger.error(f"[Registry] 初始化 Backend 失败 {conn.name}: {e}")

    # -------------------------------------------------------------------------
    # YAML 回退加载
    # -------------------------------------------------------------------------

    def _load_from_yaml(self, config_path: str) -> None:
        """从 YAML 加载 Provider 配置（Video / ComfyUI 回退）"""
        try:
            if not os.path.exists(config_path):
                logger.warning(f"[Registry] 配置文件不存在: {config_path}")
                return

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            providers = config.get("providers", {}) if config else {}
            defaults = config.get("defaults", {}) if config else {}

            for mt_str, key in defaults.items():
                try:
                    mt = MediaType(mt_str)
                    self._defaults[mt] = key
                except ValueError:
                    pass

            # Video backends
            video_impls = _load_video_backends()
            for key, cfg in providers.items():
                if cfg.get("media_type") == "video":
                    impl_cls = video_impls.get(key)
                    if not impl_cls:
                        continue
                    api_key = self._resolve_env(cfg.get("api_key", ""))
                    if not api_key:
                        continue
                    backend = impl_cls(api_key=api_key, api_base=cfg.get("api_base", ""), model=cfg.get("model"))
                    self._backends[MediaType.VIDEO][key] = backend
                    logger.info(f"[Registry] 已注册 Video Backend: {key} (YAML)")

            # ComfyUI backends
            comfyui_impls = _load_comfyui_backends()
            for key, cfg in providers.items():
                if cfg.get("media_type") == "comfyui":
                    impl_pair = comfyui_impls.get(key)
                    if not impl_pair:
                        continue
                    impl_cls, config_cls = impl_pair
                    comfy_config = config_cls(
                        server_url=cfg.get("server_url", "http://127.0.0.1:8188"),
                        workflow_dir=cfg.get("workflow_dir", "backend/app/services/comfyui/workflows"),
                        output_dir=cfg.get("output_dir", "storage/comfyui/outputs"),
                    )
                    backend = impl_cls(config=comfy_config)
                    for mt in cfg.get("provides", ["image"]):
                        try:
                            mt_enum = MediaType(mt)
                            self._backends[mt_enum][key] = backend
                        except ValueError:
                            pass

            self._loaded = True
            logger.info(
                f"[Registry] YAML 加载完成 - "
                f"Video: {list(self._backends[MediaType.VIDEO].keys())}"
            )

        except Exception as e:
            logger.warning(f"[Registry] YAML 加载失败: {e}")

    @staticmethod
    def _resolve_env(value: str) -> str:
        """解析 ${ENV_VAR} 格式的环境变量引用"""
        if not value:
            return ""
        if value.startswith("${") and value.endswith("}"):
            return os.environ.get(value[2:-1], "")
        return value

    # -------------------------------------------------------------------------
    # 查询接口
    # -------------------------------------------------------------------------

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

    def get_all_backends(self, media_type: MediaType) -> dict[str, Any]:
        return dict(self._backends[media_type])


def get_default_backend(registry: BackendRegistry, media_type: MediaType):
    """获取默认 Backend 实例（给 AIService.get_default 使用）"""
    default_name = registry.get_default(media_type)
    if default_name:
        return registry.get_backend(media_type, default_name)
    # 如果没有设置默认值，返回第一个可用的
    backends = registry.get_all_backends(media_type)
    if backends:
        return next(iter(backends.values()))
    return None
