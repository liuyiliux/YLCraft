"""
YLCraft — 社交媒体连接器工厂

参考 MediaCrawler 的工厂模式设计：
- 运行时动态选择平台连接器
- 支持按平台类型和认证方式创建
- 提供连接器注册机制，方便扩展

注：AI 连接器已迁移至 services/ai/backends/，此处仅保留社交媒体连接器。
"""

from __future__ import annotations

import logging
from typing import Optional, Type, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("ylcraft.connectors.factory")


# =============================================================================
# 社交媒体连接器工厂
# =============================================================================

@dataclass
class SocialConnectorInfo:
    """社交连接器信息"""
    platform_id: str
    platform_name: str
    connector_class: Type
    factory_class: Type
    supported_content_types: list
    supported_media_formats: list
    auth_types: list[str]
    description: str = ""
    # OAuth 2.0 配置（参考 Mixpost/Postiz 实现）
    oauth_auth_url: str = ""
    oauth_token_url: str = ""
    oauth_scope: str = ""
    oauth_redirect_uri: str = ""


class SocialConnectorFactory:
    """
    社交媒体连接器工厂

    使用示例：
        # 注册连接器
        SocialConnectorFactory.register("xhs", XiaoHongShuConnector, XiaoHongShuFactory)

        # 创建连接器
        connector = SocialConnectorFactory.create("xhs", {"cookie": "..."})
    """

    _connectors: Dict[str, SocialConnectorInfo] = {}

    @classmethod
    def register(
        cls,
        platform_id: str,
        connector_class: Type,
        factory_class: Type,
        supported_content_types: list = None,
        supported_media_formats: list = None,
        auth_types: list[str] = None,
        description: str = "",
        # OAuth 2.0 配置（参考 Mixpost/Postiz）
        oauth_auth_url: str = "",
        oauth_token_url: str = "",
        oauth_scope: str = "",
        oauth_redirect_uri: str = "",
    ):
        """
        注册社交媒体连接器

        Args:
            platform_id: 平台标识（如 "xhs"）
            connector_class: 连接器类
            factory_class: 工厂类
            supported_content_types: 支持的内容类型
            supported_media_formats: 支持的媒体格式
            auth_types: 支持的认证类型
            description: 描述
            oauth_auth_url: OAuth 授权 URL
            oauth_token_url: OAuth 令牌交换 URL
            oauth_scope: OAuth 权限范围
            oauth_redirect_uri: OAuth 回调地址
        """
        from app.connectors.base import ContentType, MediaFormat

        # 从连接器类获取 OAuth 配置（如果参数未提供）
        if not oauth_auth_url:
            oauth_auth_url = getattr(connector_class, 'OAUTH_AUTH_URL', "")
        if not oauth_token_url:
            oauth_token_url = getattr(connector_class, 'OAUTH_TOKEN_URL', "")
        if not oauth_scope:
            oauth_scope = getattr(connector_class, 'OAUTH_SCOPE', "")
        if not oauth_redirect_uri:
            oauth_redirect_uri = getattr(connector_class, 'OAUTH_REDIRECT_URI', "")

        info = SocialConnectorInfo(
            platform_id=platform_id,
            platform_name=getattr(connector_class, "PLATFORM_NAME", platform_id),
            connector_class=connector_class,
            factory_class=factory_class,
            supported_content_types=supported_content_types or [],
            supported_media_formats=supported_media_formats or [],
            auth_types=auth_types or ["cookie"],
            description=description,
            oauth_auth_url=oauth_auth_url,
            oauth_token_url=oauth_token_url,
            oauth_scope=oauth_scope,
            oauth_redirect_uri=oauth_redirect_uri,
        )
        cls._connectors[platform_id] = info
        logger.info(f"[SocialConnectorFactory] Registered: {platform_id}")

    @classmethod
    def unregister(cls, platform_id: str):
        """取消注册"""
        if platform_id in cls._connectors:
            del cls._connectors[platform_id]
            logger.info(f"[SocialConnectorFactory] Unregistered: {platform_id}")

    @classmethod
    def create(cls, platform_id: str, credentials: dict) -> Optional[Any]:
        """
        创建连接器实例

        Args:
            platform_id: 平台标识
            credentials: 凭证数据

        Returns:
            连接器实例或 None
        """
        info = cls._connectors.get(platform_id)
        if not info:
            logger.warning(f"[SocialConnectorFactory] Unknown platform: {platform_id}")
            return None

        try:
            return info.connector_class(credentials)
        except Exception as e:
            logger.error(f"[SocialConnectorFactory] Failed to create {platform_id}: {e}")
            return None

    @classmethod
    def create_with_factory(cls, platform_id: str, credentials: dict) -> Optional[Any]:
        """使用工厂类创建连接器"""
        info = cls._connectors.get(platform_id)
        if not info:
            return None

        try:
            factory = info.factory_class()
            return factory.create(credentials)
        except Exception as e:
            logger.error(f"[SocialConnectorFactory] Factory failed for {platform_id}: {e}")
            return None

    @classmethod
    def get_info(cls, platform_id: str) -> Optional[SocialConnectorInfo]:
        """获取连接器信息"""
        return cls._connectors.get(platform_id)

    @classmethod
    def list_platforms(cls) -> list[SocialConnectorInfo]:
        """列出所有已注册的连接器"""
        return list(cls._connectors.values())

    @classmethod
    def get_by_auth_type(cls, auth_type: str) -> list[SocialConnectorInfo]:
        """按认证类型筛选"""
        return [c for c in cls._connectors.values() if auth_type in c.auth_types]

    @classmethod
    def supports_platform(cls, platform_id: str) -> bool:
        """检查是否支持指定平台"""
        return platform_id in cls._connectors


# =============================================================================
# 连接器注册装饰器
# =============================================================================

def register_social_connector(
    platform_id: str,
    supported_content_types: list = None,
    supported_media_formats: list = None,
    auth_types: list[str] = None,
    description: str = "",
    **kwargs,  # 接受任意额外参数
):
    """注册社交媒体连接器装饰器"""
    def decorator(cls):
        # 将额外参数设置为类属性（转换为大写）
        for key, value in kwargs.items():
            attr_name = key.upper()
            setattr(cls, attr_name, value)
        
        # 提取已知的 OAuth 参数
        oauth_auth_url = kwargs.get('oauth_auth_url', '')
        oauth_token_url = kwargs.get('oauth_token_url', '')
        oauth_scope = kwargs.get('oauth_scope', '')
        oauth_redirect_uri = kwargs.get('oauth_redirect_uri', '')
        
        SocialConnectorFactory.register(
            platform_id=platform_id,
            connector_class=cls,
            factory_class=getattr(cls, "Factory", None),
            supported_content_types=supported_content_types,
            supported_media_formats=supported_media_formats,
            auth_types=auth_types,
            description=description,
            oauth_auth_url=oauth_auth_url,
            oauth_token_url=oauth_token_url,
            oauth_scope=oauth_scope,
            oauth_redirect_uri=oauth_redirect_uri,
        )
        return cls
    return decorator
