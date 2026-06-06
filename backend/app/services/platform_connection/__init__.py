r"""
Platform Connection Service Module

.. deprecated::
    本模块已废弃，推荐迁移到 `app.connectors.social`

迁移路径:
    旧: from app.services.platform_connection import PlatformConnectionService
    新: from app.connectors.social import XiaoHongShuConnector

    如需多平台统一的凭证管理，请查看 `app.connectors.social` 模块。
"""

from app.services.platform_connection.service import (
    PlatformConnectionService,
)

__all__ = [
    "PlatformConnectionService",
]
