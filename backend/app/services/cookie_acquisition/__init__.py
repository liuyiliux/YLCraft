"""
YLCraft — Cookie 自动获取模块

提供三种凭证获取方式：
- manual：手动粘贴
- playwright：Playwright 浏览器自动化
- qrcode：二维码扫码
"""

from app.services.cookie_acquisition.base import (
    AcquisitionMethod,
    AcquisitionStatus,
    AcquisitionSession,
    AcquisitionResult,
    PlatformDetector,
    QrcodeAdapter,
    STATUS_MESSAGES,
    get_status_message,
)
from app.services.cookie_acquisition.playwright_manager import PlaywrightAcquisitionManager
from app.services.cookie_acquisition.qrcode_manager import QrcodeAcquisitionManager

__all__ = [
    "AcquisitionMethod",
    "AcquisitionStatus",
    "AcquisitionSession",
    "AcquisitionResult",
    "PlatformDetector",
    "QrcodeAdapter",
    "STATUS_MESSAGES",
    "get_status_message",
    "PlaywrightAcquisitionManager",
    "QrcodeAcquisitionManager",
]
