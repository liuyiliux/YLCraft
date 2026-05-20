"""
Twitter/X 专用下载器

- 公开内容：直接走 yt-dlp（传 cookie 文件）
- 需要登录的内容：先尝试用 syndication API 解析，再走 yt-dlp
- Cookie 传递：始终使用 cookie 文件路径（Netscape 格式），不用内存 CookieJar
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from app.services.download.base import BaseDownloader, VideoInfo, VideoQuality
from app.services.video.parser import get_cookie_manager, _detect_platform
from app.core.config import ensure_download_path

logger = logging.getLogger("ylcraft.download.twitter")


class TwitterDownloader(BaseDownloader):
    """Twitter/X 专用下载器"""

    platform_name = "twitter"

    def __init__(self):
        self._cookie_file_path: Optional[str] = None

    def _get_cookie_file(self) -> Optional[str]:
        """
        获取 Twitter cookie 文件路径（Netscape 格式）

        yt-dlp 对 Twitter 必须用 cookie 文件，内存 CookieJar 经常失效。
        CookieManager 已将 cookie 保存为 Netscape 格式文件。
        """
        if self._cookie_file_path is not None:
            return self._cookie_file_path

        try:
            mgr = get_cookie_manager()
            # CookieManager 有 get_cookie_file_path 方法
            if hasattr(mgr, "get_cookie_file_path"):
                path = mgr.get_cookie_file_path("twitter")
            else:
                # 兜底：直接拼路径
                from app.services.video.parser import BASE_DIR
                path = BASE_DIR / "data" / "cookies" / "twitter.txt"

            if path and os.path.exists(path):
                self._cookie_file_path = str(path)
                logger.info(f"[TwitterDownloader] cookie 文件: {path}")
                return self._cookie_file_path
        except Exception as e:
            logger.warning(f"[TwitterDownloader] 获取 cookie 文件失败: {e}")
        return None

    async def parse(self, url: str) -> Optional[VideoInfo]:
        """
        解析 Twitter/X 视频信息

        策略：
        1. 先尝试 syndication API（无需登录，支持部分视频）
        2. 失败则返回 None，让调用方降级到 yt-dlp
        """
        try:
            from app.services.video.parsers.twitter import parse_twitter_syndication
            result = parse_twitter_syndication(url)
            if result and result.get("video_url"):
                qualities = []
                for v in result.get("videos", []):
                    qualities.append(VideoQuality(
                        quality=v.get("quality", "unknown"),
                        resolution=v.get("resolution", ""),
                        filesize="",
                        url=v.get("url", ""),
                    ))
                return VideoInfo(
                    title=result.get("title", ""),
                    author=result.get("author", ""),
                    platform="twitter",
                    cover_url=result.get("cover_url", ""),
                    duration=result.get("duration", 0),
                    qualities=qualities,
                    page_url=url,
                )
        except Exception as e:
            logger.warning(f"[TwitterDownloader] syndication 解析失败: {e}")

        # 返回 None → 让 download.py 降级到 yt-dlp
        return None

    async def download(
        self,
        url: str,
        quality: str = "best",
        title: Optional[str] = None,
        is_audio: bool = False,
    ) -> str:
        """
        用 yt-dlp 下载 Twitter/X 视频

        关键点：使用 cookie 文件路径，不用内存 CookieJar
        """
        import yt_dlp

        savedir = ensure_download_path()
        safe_title = self._sanitize(title or "twitter_video")
        outtmpl = str(savedir / f"twitter_{safe_title}_%(id)s.%(ext)s")

        cookie_file = self._get_cookie_file()
        ydl_opts = self._build_ydl_opts(outtmpl, quality, is_audio, cookie_file)

        logger.info(f"[TwitterDownloader] 开始下载 | url={url[:80]} | cookie_file={cookie_file or 'None'}")

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise ValueError("yt-dlp 未能获取视频信息")
                output_path = ydl.prepare_filename(info)
                if not os.path.exists(output_path):
                    #  fallback
                    candidates = list(savedir.glob(f"twitter_{safe_title}_*"))
                    if candidates:
                        output_path = str(max(candidates, key=os.path.getmtime))
                    else:
                        raise ValueError("未找到下载输出文件")
                return output_path

        loop = asyncio.get_running_loop()
        filepath = await asyncio.wait_for(
            loop.run_in_executor(None, _download),
            timeout=1800,
        )
        logger.info(f"[TwitterDownloader] 下载完成: {filepath}")
        return filepath

    def _build_ydl_opts(
        self,
        outtmpl: str,
        quality: str,
        is_audio: bool,
        cookie_file: Optional[str],
    ) -> dict:
        """构建 yt-dlp 选项，关键：传 cookiefile 而不是 cookiejar"""
        if is_audio:
            fmt = "bestaudio/best"
        elif quality and "1080" in quality:
            fmt = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        elif quality and "720" in quality:
            fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]"
        else:
            fmt = "bestvideo+bestaudio/best"

        opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "noplaylist": True,
            "restrict_filenames": True,
            "merge_output_format": "mp4",
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                "Referer": "https://x.com/",
            },
        }

        ffmpeg_path = self._get_ffmpeg_path()
        if ffmpeg_path:
            opts["ffmpeg_location"] = ffmpeg_path

        # 关键：传 cookie 文件，不传 cookiejar
        if cookie_file:
            opts["cookiefile"] = cookie_file
            logger.info(f"[TwitterDownloader] yt-dlp cookiefile={cookie_file}")

        return opts

    def _get_ffmpeg_path(self) -> Optional[str]:
        try:
            from app.core.config import get_ffmpeg_path
            return get_ffmpeg_path()
        except Exception:
            return None

    def _sanitize(self, name: str) -> str:
        import re
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()[:100]
