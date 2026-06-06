r"""
YLCraft — Video service package

FFmpeg 已迁移至 app.core.ffmpeg
此处保留兼容导出，不破坏现有引用。
"""

from app.core.ffmpeg import FFmpegService, get_ffmpeg_service
from app.services.cookies.manager import get_cookie_manager
from app.services.video.parser import _detect_platform

__all__ = [
    "FFmpegService",
    "get_ffmpeg_service",
    "get_cookie_manager",
    "_detect_platform",
]
