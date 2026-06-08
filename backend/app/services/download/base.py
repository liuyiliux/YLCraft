"""
下载器基础类

所有平台专用下载器都应继承 BaseDownloader
"""
from __future__ import annotations

import abc
from typing import Optional, Dict, List, Tuple, Any
from pydantic import BaseModel, Field


class VideoQuality(BaseModel):
    """视频清晰度"""
    quality: str       # 质量标识 (e.g., "127", "1080P", "720P")
    resolution: str    # 分辨率 (e.g., "1920x1080")
    filesize: str      # 文件大小 (e.g., "100MB")
    url: str           # 下载链接
    format_id: str = ""  # yt-dlp format_id (可选)


class VideoInfo(BaseModel):
    """视频信息"""
    title: str = ""
    author: str = ""
    platform: str = ""
    cover_url: str = ""
    duration: int = 0
    description: str = ""
    qualities: List[VideoQuality] = []
    audio_url: str = ""
    page_url: str = ""  # 原始页面URL（用于yt-dlp下载）
    raw: Dict[str, Any] = Field(default_factory=dict)


class BaseDownloader(abc.ABC):
    """平台下载器基类"""

    platform_name: str = ""  # 平台名称 (e.g., "bilibili", "twitter")

    @staticmethod
    def calculate_filesize(
        filesize_bytes: Optional[int] = None,
        bitrate_bps: Optional[int] = None,
        duration_seconds: Optional[int] = None,
    ) -> str:
        """
        计算并格式化文件大小

        Args:
            filesize_bytes: 已知文件大小（字节）
            bitrate_bps: 比特率（bps）
            duration_seconds: 视频时长（秒）

        Returns:
            格式化的文件大小字符串，例如 "100MB" 或 "~50MB"
        """
        # 优先使用已知的文件大小
        if filesize_bytes and filesize_bytes > 0:
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if filesize_bytes < 1024:
                    return f"{filesize_bytes:.1f}{unit}"
                filesize_bytes /= 1024
            return f"{filesize_bytes:.1f}PB"
        
        # 否则使用比特率估算
        if bitrate_bps and bitrate_bps > 0 and duration_seconds and duration_seconds > 0:
            # bandwidth (bps) / 1000 = tbr (kbps)
            # tbr (kbps) * duration (秒) / 8 / 1024 = MB
            estimated_size = (bitrate_bps / 1000) * duration_seconds / 8 / 1024
            return f"~{estimated_size:.1f}MB"
        
        return "未知"

    @abc.abstractmethod
    async def parse(self, url: str) -> Optional[VideoInfo]:
        """
        解析视频信息

        Args:
            url: 视频链接

        Returns:
            VideoInfo 或 None (解析失败)
        """
        pass

    @abc.abstractmethod
    async def download(
        self,
        url: str,
        quality: str = "best",
        title: Optional[str] = None,
        is_audio: bool = False,
    ) -> Tuple[str, Optional[VideoInfo]]:
        """
        下载视频，返回 (文件路径, 视频信息)

        Args:
            url: 视频链接或下载链接
            quality: 清晰度标识
            title: 自定义标题
            is_audio: 是否只下载音频

        Returns:
            (下载文件的本地路径, 视频信息)
        """
        pass

    async def get_qualities(self, url: str) -> List[VideoQuality]:
        """
        获取可选清晰度列表

        Args:
            url: 视频链接

        Returns:
            清晰度列表
        """
        info = await self.parse(url)
        return info.qualities if info else []
