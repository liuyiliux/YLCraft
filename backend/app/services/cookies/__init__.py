"""
YLCraft — Cookie 模块（统一管理 + 获取）

Cookie 管理：
- CookieManager: 统一的 Cookie 存储/读取/同步（PlatformConnection DB + 磁盘文件）
- get_cookie_manager(): 全局单例

Cookie 获取（三种方式）：
- manual: 手动粘贴
- patchright: Patchright 浏览器自动化（替代 Playwright，内置 Stealth）
- qrcode: 二维码扫码
"""

from app.db.models.platform_connection import AcquisitionMethod

from app.services.cookies.base import (
    AcquisitionStatus,
    AcquisitionSession,
    AcquisitionResult,
    PlatformDetector,
    QrcodeAdapter,
    STATUS_MESSAGES,
    get_status_message,
    get_platform_domains,
)
from app.services.cookies.manager import CookieManager, get_cookie_manager
from app.services.cookies.patchright_manager import PatchrightAcquisitionManager
from app.services.cookies.qrcode_manager import QrcodeAcquisitionManager

__all__ = [
    # 数据模型
    "AcquisitionMethod",
    "AcquisitionStatus",
    "AcquisitionSession",
    "AcquisitionResult",
    "PlatformDetector",
    "QrcodeAdapter",
    "STATUS_MESSAGES",
    "get_status_message",
    "get_platform_domains",
    # Cookie 管理
    "CookieManager",
    "get_cookie_manager",
    # Cookie 获取
    "PatchrightAcquisitionManager",
    "QrcodeAcquisitionManager",
]
