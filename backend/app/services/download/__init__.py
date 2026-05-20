"""
下载服务

各平台专用下载器
"""
from app.services.download.manager import (
    get_downloader,
    parse_with_manager,
    download_with_manager,
    get_supported_platforms,
)

__all__ = [
    "get_downloader",
    "parse_with_manager",
    "download_with_manager",
    "get_supported_platforms",
]
