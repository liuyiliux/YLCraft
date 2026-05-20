"""
下载管理器

根据平台路由到对应的平台专用下载器
如果没有专用下载器，则使用 yt-dlp 兜底
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional, List

from app.services.download.base import BaseDownloader, VideoInfo, VideoQuality
from app.services.video.parser import get_cookie_manager, _detect_platform

logger = logging.getLogger("ylcraft.download.manager")

# 全局下载器注册表
_downloaders: Dict[str, BaseDownloader] = {}


def _auto_discover_downloaders():
    """自动发现并注册平台专用下载器"""
    global _downloaders

    # 已注册的下载器
    _downloaders.clear()

    # 动态导入 platforms 目录下的模块
    platforms_dir = Path(__file__).parent / "platforms"
    if not platforms_dir.exists():
        return

    import importlib.util

    for py_file in sorted(platforms_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"app.services.download.platforms.{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 查找模块中的 Downloader 类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseDownloader)
                    and attr is not BaseDownloader
                ):
                    downloader = attr()
                    if downloader.platform_name:
                        _downloaders[downloader.platform_name] = downloader
                        logger.info(f"[DownloadManager] 注册下载器: {downloader.platform_name} ({attr_name})")
        except Exception as e:
            logger.error(f"[DownloadManager] 加载下载器失败 {py_file}: {e}")


def get_downloader(platform: str) -> Optional[BaseDownloader]:
    """
    根据平台名称获取专用下载器

    Args:
        platform: 平台名称 (e.g., "bilibili", "twitter")

    Returns:
        平台专用下载器，如果没有则返回 None
    """
    if not _downloaders:
        _auto_discover_downloaders()
    return _downloaders.get(platform)


async def parse_with_manager(url: str) -> Optional[VideoInfo]:
    """
    使用管理器解析视频信息

    1. 检测平台
    2. 如果有专用下载器，使用专用下载器
    3. 否则返回 None（让调用方使用 yt-dlp）

    Args:
        url: 视频链接

    Returns:
        VideoInfo 或 None
    """
    platform = _detect_platform(url)
    if not platform:
        return None

    downloader = get_downloader(platform)
    if downloader:
        try:
            info = await downloader.parse(url)
            if info:
                logger.info(f"[DownloadManager] 使用 {platform} 专用下载器解析: {url[:60]}")
                return info
        except Exception as e:
            logger.error(f"[DownloadManager] {platform} 专用下载器解析失败: {e}")

    return None


async def download_with_manager(
    url: str,
    quality: str = "best",
    title: Optional[str] = None,
    page_url: Optional[str] = None,
    is_audio: bool = False,
) -> Optional[str]:
    """
    使用管理器下载视频

    1. 检测平台
    2. 如果有专用下载器，使用专用下载器
    3. 否则返回 None（让调用方使用 yt-dlp）

    Args:
        url: 视频链接或下载链接
        quality: 清晰度标识
        title: 自定义标题
        page_url: 原始页面URL（用于yt-dlp）
        is_audio: 是否只下载音频

    Returns:
        下载文件的本地路径，或 None
    """
    platform = _detect_platform(url) or (page_url and _detect_platform(page_url))
    if not platform:
        return None

    downloader = get_downloader(platform)
    if downloader:
        try:
            filepath = await downloader.download(url, quality, title, is_audio)
            if filepath:
                logger.info(f"[DownloadManager] 使用 {platform} 专用下载器下载: {filepath}")
                return filepath
        except Exception as e:
            logger.error(f"[DownloadManager] {platform} 专用下载器下载失败: {e}")

    return None


def get_supported_platforms() -> List[str]:
    """获取已注册专用下载器的平台列表"""
    if not _downloaders:
        _auto_discover_downloaders()
    return list(_downloaders.keys())
