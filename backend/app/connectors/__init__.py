"""连接器（Connectors）层

本层负责各平台 API 的低层通信（HTTP/WebSocket 客户端），不包含业务逻辑。
边界划分：
    - connectors/  → 各平台原始 API 封装（认证、请求、响应解析）
    - services/platforms/ → 平台业务路由（下载策略、限流、重试逻辑）
"""
from app.connectors.factory import (
    SocialConnectorFactory,
    SocialConnectorInfo,
    register_social_connector,
)
from app.connectors.registry import (
    ConnectorRegistry,
    get_social_connector,
    init_connectors,
)

__all__ = [
    "SocialConnectorFactory",
    "SocialConnectorInfo",
    "register_social_connector",
    "ConnectorRegistry",
    "get_social_connector",
    "init_connectors",
]
