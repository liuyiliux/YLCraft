"""
YLCraft — 社交媒体连接器注册中心

自动加载所有已实现的社交媒体连接器，参考 MediaCrawler 的入口模式：
- 应用启动时自动注册所有连接器
- 支持延迟加载
- 提供统一的连接器管理接口
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict

logger = logging.getLogger("ylcraft.connectors.registry")


class ConnectorRegistry:
    """
    社交媒体连接器注册中心

    负责：
    - 自动加载所有连接器
    - 管理连接器生命周期
    - 提供统一的访问接口
    """

    _connectors: Dict[str, type] = {}

    @classmethod
    def register(cls, platform_id: str, connector_class: type):
        """注册社交媒体连接器"""
        cls._connectors[platform_id] = connector_class
        logger.debug(f"[Registry] Registered social connector: {platform_id}")

    @classmethod
    def get(cls, platform_id: str) -> Optional[type]:
        """获取社交媒体连接器类"""
        return cls._connectors.get(platform_id)

    @classmethod
    def list_all(cls) -> List[str]:
        """列出所有社交媒体连接器"""
        return list(cls._connectors.keys())

    @classmethod
    def load_all(cls):
        """加载所有连接器（自动注册）"""
        logger.info("[Registry] Loading all social connectors...")

        # 社交媒体连接器
        try:
            from app.connectors.social.xhs import XiaoHongShuConnector
            cls.register("xhs", XiaoHongShuConnector)
            logger.info("[Registry] Loaded: XiaoHongShuConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load XHS connector: {e}")

        try:
            from app.connectors.social.douyin import DouYinConnector
            cls.register("douyin", DouYinConnector)
            logger.info("[Registry] Loaded: DouYinConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load DouYin connector: {e}")

        try:
            from app.connectors.social.bilibili import BilibiliConnector
            cls.register("bilibili", BilibiliConnector)
            logger.info("[Registry] Loaded: BilibiliConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Bilibili connector: {e}")

        try:
            from app.connectors.social.weibo import WeiboConnector
            cls.register("weibo", WeiboConnector)
            logger.info("[Registry] Loaded: WeiboConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Weibo connector: {e}")

        try:
            from app.connectors.social.twitter import TwitterConnector
            cls.register("twitter", TwitterConnector)
            logger.info("[Registry] Loaded: TwitterConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Twitter connector: {e}")

        try:
            from app.connectors.social.tiktok import TikTokConnector
            cls.register("tiktok", TikTokConnector)
            logger.info("[Registry] Loaded: TikTokConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load TikTok connector: {e}")

        try:
            from app.connectors.social.instagram import InstagramConnector
            cls.register("instagram", InstagramConnector)
            logger.info("[Registry] Loaded: InstagramConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Instagram connector: {e}")

        try:
            from app.connectors.social.threads import ThreadsConnector
            cls.register("threads", ThreadsConnector)
            logger.info("[Registry] Loaded: ThreadsConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Threads connector: {e}")

        try:
            from app.connectors.social.kuaishou import KuaishouConnector
            cls.register("kuaishou", KuaishouConnector)
            logger.info("[Registry] Loaded: KuaishouConnector")
        except ImportError as e:
            logger.warning(f"[Registry] Failed to load Kuaishou connector: {e}")

        logger.info(f"[Registry] Loaded {len(cls._connectors)} social connectors")


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
    connector_class = ConnectorRegistry.get(platform_id)
    if not connector_class:
        raise ValueError(f"Unknown social platform: {platform_id}")
    return connector_class(credentials)


def init_connectors():
    """初始化所有连接器（应用启动时调用）"""
    ConnectorRegistry.load_all()
