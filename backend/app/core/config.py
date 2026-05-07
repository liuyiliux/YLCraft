"""
YLCraft — Live2D 配置管理

管理处理模式（本地/API）和API密钥配置。
API密钥优先从数据库读取，兜底从 providers.yaml 读取。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from app.db.models.api_key import ApiKey


class ProcessingMode(str, Enum):
    """处理模式"""
    LOCAL = "local"      # 本地模型
    API = "api"          # 云端API

    @classmethod
    def all(cls) -> list[str]:
        return [e.value for e in cls]

    @classmethod
    def label(cls, value: str) -> str:
        labels = {
            "local": "本地模型",
            "api": "云端API"
        }
        return labels.get(value, value)


class ProvidersConfig:
    """
    本地 Provider 配置加载器

    从 backend/config/providers.yaml 加载默认配置。
    支持 ${ENV_VAR} 格式的环境变量替换。
    """

    _instance: Optional["ProvidersConfig"] = None

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径，默认为 backend/config/providers.yaml
        """
        if config_path is None:
            backend_dir = Path(__file__).parent.parent.parent
            config_path = backend_dir / "config" / "providers.yaml"

        self.config_path = Path(config_path)
        self._providers: Dict[str, Dict[str, Any]] = {}
        self._defaults: Dict[str, str] = {}
        self._load_config()

    def _load_config(self):
        """加载 YAML 配置文件"""
        try:
            import yaml
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self._providers = config.get("providers", {})
            self._defaults = config.get("defaults", {})
        except ImportError:
            # 如果没有 yaml 模块，尝试 JSON
            json_path = self.config_path.with_suffix(".json")
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self._providers = config.get("providers", {})
                self._defaults = config.get("defaults", {})
        except Exception:
            self._providers = {}
            self._defaults = {}

    @staticmethod
    def _resolve_env_var(value: str) -> str:
        """
        解析环境变量占位符

        支持 ${ENV_VAR} 格式，返回替换后的值。
        如果环境变量不存在，返回空字符串。
        """
        if not isinstance(value, str):
            return value

        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, value)

        for env_var in matches:
            env_value = os.environ.get(env_var, "")
            value = value.replace(f"${{{env_var}}}", env_value)

        return value

    def get_provider(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取 Provider 配置（仅用于获取默认值，不包含密钥）

        Args:
            name: Provider 名称

        Returns:
            Provider 配置字典（不含密钥）
        """
        if name not in self._providers:
            return None

        config = self._providers[name].copy()

        # 解析所有环境变量
        for key, value in config.items():
            if isinstance(value, str):
                config[key] = self._resolve_env_var(value)

        return config

    def get_default_provider(self, category: str) -> Optional[str]:
        """
        获取某类别的默认 Provider

        Args:
            category: 类别名称，如 "live2d_rembg"

        Returns:
            默认 Provider 名称
        """
        return self._defaults.get(category)

    def list_providers_by_type(self, media_type: str) -> list[str]:
        """
        按媒体类型列出 Provider

        Args:
            media_type: 媒体类型，如 "image-processing"

        Returns:
            符合类型的 Provider 名称列表
        """
        return [
            name for name, config in self._providers.items()
            if config.get("media_type") == media_type
        ]


class ApiKeyStore:
    """
    API 密钥存储器

    支持从数据库读取密钥，兜底从配置文件读取。
    """

    _instance: Optional["ApiKeyStore"] = None

    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 60  # 缓存 60 秒

    async def get_api_key(self, provider: str) -> Optional[str]:
        """
        获取 API 密钥（优先数据库，兜底配置文件）

        Args:
            provider: Provider 名称

        Returns:
            API 密钥，如果未配置则返回 None
        """
        import time

        # 检查缓存
        if provider in self._cache:
            cache_age = time.time() - self._cache_time.get(provider, 0)
            if cache_age < self._cache_ttl:
                return self._cache[provider]

        # 尝试从数据库获取
        db_key = await self._get_from_db(provider)
        if db_key:
            self._cache[provider] = db_key
            self._cache_time[provider] = time.time()
            return db_key

        # 兜底从配置文件获取
        config_key = self._get_from_config(provider)
        if config_key:
            self._cache[provider] = config_key
            self._cache_time[provider] = time.time()
            return config_key

        return None

    async def _get_from_db(self, provider: str) -> Optional[str]:
        """从数据库获取密钥"""
        try:
            from app.db.database import AsyncSessionLocal
            from app.db.models.api_key import ApiKey, ApiKeyStatus
            from sqlmodel import select

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ApiKey).where(
                        ApiKey.provider == provider,
                        ApiKey.status == ApiKeyStatus.ACTIVE.value
                    )
                )
                api_key = result.scalar_one_or_none()

                if api_key and api_key.api_key:
                    # 增加使用计数
                    api_key.increment_usage()
                    await session.commit()
                    return api_key.api_key
        except Exception:
            # 数据库可能未初始化，跳过
            pass

        return None

    def _get_from_config(self, provider: str) -> Optional[str]:
        """从配置文件获取密钥（用于开发/兜底）"""
        providers_config = ProvidersConfig()
        provider_info = providers_config.get_provider(provider)

        if provider_info:
            return provider_info.get("api_key")

        return None

    def clear_cache(self, provider: Optional[str] = None):
        """清除缓存"""
        if provider:
            self._cache.pop(provider, None)
            self._cache_time.pop(provider, None)
        else:
            self._cache.clear()
            self._cache_time.clear()


class Live2DConfig:
    """Live2D 配置管理类"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置

        Args:
            config_path: 配置文件路径，默认为 backend/config/live2d.json
        """
        if config_path is None:
            backend_dir = Path(__file__).parent.parent.parent
            config_path = backend_dir / "config" / "live2d.json"

        self.config_path = Path(config_path)
        self._config = self._load_config()
        self._providers = ProvidersConfig()
        self._api_key_store = ApiKeyStore()

    def _load_config(self) -> dict:
        """加载配置文件"""
        if not self.config_path.exists():
            return {
                "default_processing_mode": ProcessingMode.LOCAL.value,
                "processing_modes": {
                    "rembg": ProcessingMode.LOCAL.value,
                    "style_transfer": ProcessingMode.LOCAL.value,
                    "segmentation": ProcessingMode.LOCAL.value,
                },
                "providers": {},
                "local_models": {},
            }

        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_config(self):
        """保存配置到文件"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    # ---- 处理模式相关 ----

    def get_default_mode(self) -> str:
        """获取默认处理模式"""
        return self._config.get("default_processing_mode", ProcessingMode.LOCAL.value)

    def set_default_mode(self, mode: str):
        """设置默认处理模式"""
        if mode not in ProcessingMode.all():
            raise ValueError(f"无效的处理模式: {mode}")
        self._config["default_processing_mode"] = mode
        self._save_config()

    def get_processing_mode(self, service: str) -> str:
        """
        获取指定服务的处理模式

        Args:
            service: 服务名称（rembg, style_transfer, segmentation）

        Returns:
            处理模式（local 或 api）
        """
        modes = self._config.get("processing_modes", {})
        return modes.get(service, self.get_default_mode())

    def set_processing_mode(self, service: str, mode: str):
        """
        设置指定服务的处理模式

        Args:
            service: 服务名称
            mode: 处理模式
        """
        if mode not in ProcessingMode.all():
            raise ValueError(f"无效的处理模式: {mode}")

        if "processing_modes" not in self._config:
            self._config["processing_modes"] = {}

        self._config["processing_modes"][service] = mode
        self._save_config()

    # ---- Provider 相关 ----

    def get_provider_name(self, service: str) -> Optional[str]:
        """
        获取服务使用的 Provider 名称

        Args:
            service: 服务名称

        Returns:
            Provider 名称
        """
        providers = self._config.get("providers", {})
        return providers.get(service)

    def set_provider(self, service: str, provider_name: str):
        """
        设置服务使用的 Provider

        Args:
            service: 服务名称
            provider_name: Provider 名称
        """
        if "providers" not in self._config:
            self._config["providers"] = {}

        self._config["providers"][service] = provider_name
        self._save_config()

    # ---- API 配置相关（优先数据库，兜底配置文件）----

    async def get_api_key(self, service: str) -> Optional[str]:
        """
        获取 API 密钥（异步，优先数据库）

        Args:
            service: 服务名称（rembg, style_transfer, segmentation）

        Returns:
            API 密钥，如果未配置则返回 None
        """
        provider_name = self.get_provider_name(service)
        if not provider_name:
            # 尝试从默认配置获取
            default_key = f"live2d_{service}"
            provider_name = self._providers.get_default_provider(default_key)

        if provider_name:
            return await self._api_key_store.get_api_key(provider_name)

        return None

    def get_api_key_sync(self, service: str) -> Optional[str]:
        """
        同步获取 API 密钥（仅从配置文件，兜底）

        Args:
            service: 服务名称

        Returns:
            API 密钥
        """
        provider_name = self.get_provider_name(service)
        if not provider_name:
            default_key = f"live2d_{service}"
            provider_name = self._providers.get_default_provider(default_key)

        if provider_name:
            return self._api_key_store._get_from_config(provider_name)

        return None

    def get_api_endpoint(self, service: str) -> Optional[str]:
        """
        获取 API 端点 URL

        Args:
            service: 服务名称

        Returns:
            API 端点 URL
        """
        provider_name = self.get_provider_name(service)
        if not provider_name:
            default_key = f"live2d_{service}"
            provider_name = self._providers.get_default_provider(default_key)

        if provider_name:
            provider_config = self._providers.get_provider(provider_name)
            if provider_config:
                return provider_config.get("api_base")

        return None

    def get_api_model(self, service: str) -> Optional[str]:
        """
        获取 API 模型名称

        Args:
            service: 服务名称

        Returns:
            API 模型名称
        """
        provider_name = self.get_provider_name(service)
        if not provider_name:
            default_key = f"live2d_{service}"
            provider_name = self._providers.get_default_provider(default_key)

        if provider_name:
            provider_config = self._providers.get_provider(provider_name)
            if provider_config:
                return provider_config.get("model")

        return None

    async def is_api_configured(self, service: str) -> bool:
        """
        检查 API 是否已配置（密钥非空）

        Args:
            service: 服务名称

        Returns:
            是否已配置
        """
        api_key = await self.get_api_key(service)
        return bool(api_key)

    # ---- 本地模型相关 ----

    def get_local_model(self, service: str) -> Optional[str]:
        """
        获取本地模型名称

        Args:
            service: 服务名称

        Returns:
            本地模型名称
        """
        local_models = self._config.get("local_models", {})
        return local_models.get(service)

    def set_local_model(self, service: str, model_name: str):
        """
        设置本地模型名称

        Args:
            service: 服务名称
            model_name: 模型名称
        """
        if "local_models" not in self._config:
            self._config["local_models"] = {}

        self._config["local_models"][service] = model_name
        self._save_config()

    # ---- 统一接口 ----

    def get_effective_mode(self, service: str, model_config: Optional[dict] = None) -> str:
        """
        获取有效的处理模式（考虑模型级别配置覆盖）

        Args:
            service: 服务名称
            model_config: 模型级别配置（可选，来自 Live2DModel.processing_config）

        Returns:
            有效的处理模式
        """
        # 优先级：模型级别 > 服务级别 > 全局默认
        if model_config and service in model_config:
            mode = model_config[service]
            if mode in ProcessingMode.all():
                return mode

        return self.get_processing_mode(service)

    # ---- 列出可用 Provider ----

    def list_available_providers(self) -> Dict[str, list[str]]:
        """
        列出各服务可用的 Provider

        Returns:
            {服务名称: [Provider名称列表]}
        """
        result = {}
        for service in ["rembg", "style_transfer", "segmentation"]:
            providers = self._providers.list_providers_by_type("image-processing")
            result[service] = providers
        return result

    def get_provider_info(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """
        获取 Provider 详细信息

        Args:
            provider_name: Provider 名称

        Returns:
            Provider 配置（不含密钥）
        """
        return self._providers.get_provider(provider_name)


# 全局配置实例
_config_instance: Optional[Live2DConfig] = None


def get_live2d_config() -> Live2DConfig:
    """获取全局 Live2D 配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Live2DConfig()
    return _config_instance


# ---- 通用辅助函数 ----

def ensure_download_path() -> Path:
    """确保下载目录存在并返回路径"""
    backend_dir = Path(__file__).parent.parent.parent
    download_dir = backend_dir / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def get_ffmpeg_path() -> Path:
    """获取 FFmpeg 可执行文件路径"""
    backend_dir = Path(__file__).parent.parent.parent
    # 优先使用项目内的 ffmpeg
    ffmpeg_path = backend_dir / "tools" / "ffmpeg.exe"
    if ffmpeg_path.exists():
        return ffmpeg_path
    # 兜底系统 PATH 中的 ffmpeg
    import shutil
    return Path(shutil.which("ffmpeg") or "ffmpeg")


def get_settings():
    """获取设置（转发到 settings 路由模块）"""
    from app.api.v1 import settings as settings_module
    return settings_module._get_settings()


def update_settings(key: str, value: Any):
    """更新设置（转发到 settings 路由模块）"""
    from app.api.v1 import settings as settings_module
    return settings_module._update_settings(key, value)


def get(key: str, default: Any = None) -> Any:
    """获取设置值（转发到 settings 路由模块）"""
    from app.api.v1 import settings as settings_module
    return settings_module._get(key, default)
