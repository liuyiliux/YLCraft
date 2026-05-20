"""
YLCraft — Cookie 自动获取模块

提供三种凭证获取方式：
- manual：手动粘贴
- patchright：Patchright 浏览器自动化（✅ 替代 Playwright，内置 Stealth）
- qrcode：二维码扫码
"""

from app.db.models.platform_connection import AcquisitionMethod
from app.services.cookie_acquisition.base import (
    AcquisitionStatus,
    AcquisitionSession,
    AcquisitionResult,
    PlatformDetector,
    QrcodeAdapter,
    STATUS_MESSAGES,
    get_status_message,
)
from app.services.cookie_acquisition.patchright_manager import PatchrightAcquisitionManager
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
    "PatchrightAcquisitionManager",  # ✅ 改为 Patchright
    "QrcodeAcquisitionManager",
]
