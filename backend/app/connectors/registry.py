"""
YLCraft — 连接器注册中心

自动加载所有已实现的连接器，参考 MediaCrawler 的入口模式：
- 应用启动时自动注册所有连接器
- 支持延迟加载
- 提供统一的连接器管理接口
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("ylcraft.connectors.registry")


class ConnectorRegistry:
    """
    连接器注册中心

    负责：
    - 自动加载所有连接器
    - 管理连接器生命周期
    - 提供统一的访问接口
    """

    _social_connectors: Dict[str, type] = {}
    _ai_connectors: Dict[str, type] = {}

    @classmethod
    def register_social(cls, platform_id: str, connector_class: type):
        """注册社交媒体连接器"""
        cls._social_connectors[platform_id] = connector_class
        logger.debug(f"[Registry] Registered social connector: {platform_id}")

    @classmethod
    def register_ai(cls, provider_id: str, connector_class: type):
        """注册 AI 连接器"""
        cls._ai_connectors[provider_id] = connector_class
        logger.debug(f"[Registry] Registered AI connector: {provider_id}")

    @classmethod
    def get_social_connector(cls, platform_id: str) -> Optional[type]:
        """获取社交媒体连接器类"""
        return cls._social_connectors.get(platform_id)

    @classmethod
    def get_ai_connector(cls, provider_id: str) -> Optional[type]:
        """获取 AI 连接器类"""
        return cls._ai_connectors.get(provider_id)

    @classmethod
    def list_social_connectors(cls) -> List[str]:
        """列出所有社交媒体连接器"""
        return list(cls._social_connectors.keys())

    @classmethod
    def list_ai_connectors(cls) -> List[str]:
        """列出所有 AI 连接器"""
        return list(cls._ai_connectors.keys())

    @classmethod
    def load_all(cls):
        """加载所有连接器（自动注册）"""
        logger.info("[Registry] Loading all connectors...")

        # 社交媒体连接器
        try:
            from app.connectors.social.xhs import XiaoHongShuConnector
            cls.register_social("xhs", XiaoHongShuConnector)
            logger.info("[Registry] Loaded: XiaoHongShuConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load XHS connector: {e}")

        try:
            from app.connectors.social.douyin import DouYinConnector
            cls.register_social("douyin", DouYinConnector)
            logger.info("[Registry] Loaded: DouYinConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load DouYin connector: {e}")

        try:
            from app.connectors.social.bilibili import BilibiliConnector
            cls.register_social("bilibili", BilibiliConnector)
            logger.info("[Registry] Loaded: BilibiliConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Bilibili connector: {e}")

        # 新增：微博连接器
        try:
            from app.connectors.social.weibo import WeiboConnector
            cls.register_social("weibo", WeiboConnector)
            logger.info("[Registry] Loaded: WeiboConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Weibo connector: {e}")

        # 新增：Twitter/X 连接器
        try:
            from app.connectors.social.twitter import TwitterConnector
            cls.register_social("twitter", TwitterConnector)
            logger.info("[Registry] Loaded: TwitterConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Twitter connector: {e}")

        # 新增：TikTok 连接器
        try:
            from app.connectors.social.tiktok import TikTokConnector
            cls.register_social("tiktok", TikTokConnector)
            logger.info("[Registry] Loaded: TikTokConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load TikTok connector: {e}")

        # 新增：Instagram 连接器
        try:
            from app.connectors.social.instagram import InstagramConnector
            cls.register_social("instagram", InstagramConnector)
            logger.info("[Registry] Loaded: InstagramConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Instagram connector: {e}")

        # 新增：Threads 连接器
        try:
            from app.connectors.social.threads import ThreadsConnector
            cls.register_social("threads", ThreadsConnector)
            logger.info("[Registry] Loaded: ThreadsConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Threads connector: {e}")

        # 新增：快手连接器
        try:
            from app.connectors.social.kuaishou import KuaishouConnector
            cls.register_social("kuaishou", KuaishouConnector)
            logger.info("[Registry] Loaded: KuaishouConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Kuaishou connector: {e}")

        # AI 连接器
        try:
            from app.connectors.ai.openai import OpenAIConnector
            cls.register_ai("openai", OpenAIConnector)
            logger.info("[Registry] Loaded: OpenAIConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load OpenAI connector: {e}")

        logger.info(f"[Registry] Loaded {len(cls._social_connectors)} social, {len(cls._ai_connectors)} AI connectors")


# =============================================================================
# 便捷函数
# =============================================================================

def get_social_connector(platform_id: str, credentials: dict):
    """
    获取社交媒体连接器实例

    Args:
        platform_id: 平台标识
        credentials: 凭证数据

    Returns:
        连接器实例
    """
    connector_class = ConnectorRegistry.get_social_connector(platform_id)
    if not connector_class:
        raise ValueError(f"Unknown social platform: {platform_id}")
    return connector_class(credentials)


def get_ai_connector(provider_id: str, api_key: str, config: dict = None):
    """
    获取 AI 连接器实例

    Args:
        provider_id: 提供商标识
        api_key: API 密钥
        config: 额外配置

    Returns:
        连接器实例
    """
    connector_class = ConnectorRegistry.get_ai_connector(provider_id)
    if not connector_class:
        raise ValueError(f"Unknown AI provider: {provider_id}")
    return connector_class(api_key, config)


def init_connectors():
    """初始化所有连接器（应用启动时调用）"""
    ConnectorRegistry.load_all()
