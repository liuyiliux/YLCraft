r"""
Social Media Connectors Module

提供多平台社交媒体账号的凭证管理与 API 连接能力。

支持的平台:
    - 小红书 (XiaoHongShuConnector)

凭证管理:
    各 Connector 通过 `app.services.cookies` 管理平台登录态（Cookie/Session）。
    支持扫码登录态自动刷新，无需手动维护。

Usage:
    from app.connectors.social import XiaoHongShuConnector
    connector = XiaoHongShuConnector(cookie_manager=cookie_manager)
"""

from app.connectors.social.xhs import XiaoHongShuConnector

__all__ = ["XiaoHongShuConnector"]
