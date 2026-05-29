# Video service package
# CookieManager 已迁移至 app.services.cookies.manager
# 此处保留兼容导出，不破坏现有引用
from app.services.cookies.manager import get_cookie_manager
from app.services.video.parser import _detect_platform
from app.services.video.ffmpeg import FFmpegService, get_ffmpeg_service

__all__ = ["get_cookie_manager", "_detect_platform", "FFmpegService", "get_ffmpeg_service"]
