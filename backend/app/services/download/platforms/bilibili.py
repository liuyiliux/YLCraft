"""
B站专用下载器

使用 BilibiliClient（WBI签名）获取高清视频URL
支持 DASH 格式（音视频分离，需合并）
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx

from app.services.download.base import BaseDownloader, VideoInfo, VideoQuality
from app.services.video.parser import get_cookie_manager
from app.core.config import ensure_download_path, get_ffmpeg_path
from app.services.platforms.types import ClientConfig
from app.services.platforms.bilibili.client import BilibiliClient
from app.core.config import get_ffmpeg_path

logger = logging.getLogger("ylcraft.download.bilibili")

# B站清晰度映射
BILI_QUALITY_MAP = {
    127: "8K",
    126: "杜比视界",
    125: "HDR",
    120: "4K",
    116: "1080P60",
    112: "1080P+",
    80: "1080P",
    64: "720P",
    32: "480P",
    16: "360P",
    6: "240P",
}


class BilibiliDownloader(BaseDownloader):
    """B站专用下载器"""

    platform_name = "bilibili"

    def __init__(self):
        self._client = None
        self._cookie_manager = None

    async def _get_client(self):
        """获取 BilibiliClient 实例（带 Cookie）"""
        if self._client is None:
            from app.services.platforms.bilibili.client import BilibiliClient
            from app.services.platforms.types import ClientConfig
            # 从 CookieManager 获取 B站 Cookie
            cookie_manager = get_cookie_manager()
            cookie = ""
            try:
                cookie_jar = cookie_manager.get_cookiejar_for_url("https://www.bilibili.com")
                if cookie_jar:
                    cookie = "; ".join([f"{c.name}={c.value}" for c in cookie_jar])
            except Exception as e:
                logger.warning(f"[BilibiliDownloader] 获取 Cookie 失败: {e}")
            config = ClientConfig(platform="bilibili", cookie=cookie)
            self._client = BilibiliClient(config)
        return self._client

    async def parse(self, url: str) -> Optional[VideoInfo]:
        """
        解析B站视频信息

        使用 BilibiliClient 获取视频详情 + 高清播放地址
        """
        try:
            client = await self._get_client()

            # 提取 bvid
            bvid = self._extract_bvid(url)
            if not bvid:
                logger.error(f"[BilibiliDownloader] 无法提取 bvid: {url}")
                return None

            # 获取视频详情（使用 get_detail，返回 NoteDetail）
            detail = await client.get_detail(bvid)
            if not detail:
                logger.error(f"[BilibiliDownloader] 获取视频详情失败: {bvid}")
                return None

            # 获取高清播放地址（DASH格式，返回 dict）
            play_info = await client.get_video_play_info(bvid)

            # 构建清晰度列表
            qualities = []
            if play_info and play_info.get("dash"):
                dash = play_info["dash"]
                # 视频流
                for video in dash.get("video", []):
                    qn = video.get("id", 0)
                    quality_label = BILI_QUALITY_MAP.get(qn, f"qn{qn}")
                    resolution = f"{video.get('width', 0)}x{video.get('height', 0)}"
                    filesize = self._format_filesize(video.get("size", 0))
                    qualities.append(VideoQuality(
                        quality=str(qn),
                        resolution=resolution,
                        filesize=filesize,
                        url=video.get("baseUrl", ""),
                    ))
            else:
                # 降级：使用普通清晰度
                qualities = [
                    VideoQuality(quality="80", resolution="1920x1080", filesize="未知", url=""),
                    VideoQuality(quality="64", resolution="1280x720", filesize="未知", url=""),
                    VideoQuality(quality="32", resolution="854x480", filesize="未知", url=""),
                    VideoQuality(quality="16", resolution="640x360", filesize="未知", url=""),
                ]

            return VideoInfo(
                title=getattr(detail, "title", "") or "",
                author=getattr(detail, "author", "") or "",
                platform="bilibili",
                cover_url=getattr(detail, "video_cover", "") or "",
                duration=getattr(detail, "duration", 0) or 0,
                description=getattr(detail, "desc", "") or "",
                qualities=qualities,
                page_url=url,
            )

        except Exception as e:
            logger.error(f"[BilibiliDownloader] 解析失败: {e}", exc_info=True)
            return None

    async def download(
        self,
        url: str,
        quality: str = "best",
        title: Optional[str] = None,
        is_audio: bool = False,
    ) -> str:
        """
        下载B站视频

        1. 获取DASH播放地址
        2. 下载视频流 + 音频流
        3. 使用 ffmpeg 合并
        """
        client = await self._get_client()
        bvid = self._extract_bvid(url)
        if not bvid:
            raise ValueError(f"无法提取 bvid: {url}")

        # 获取播放地址（DASH格式，返回 dict）
        play_info = await client.get_video_play_info(bvid)
        if not play_info:
            raise ValueError(f"获取播放地址失败: {bvid}")

        # 选择清晰度
        quality_num = self._parse_quality(quality)
        video_url, audio_url = self._select_quality(play_info, quality_num, is_audio)

        if not video_url:
            raise ValueError(f"未找到对应清晰度的下载链接: {quality}")

        # 下载文件
        savedir = ensure_download_path()
        safe_title = self._safe_filename(title or bvid)
        video_path = savedir / f"{safe_title}_video.mp4"
        audio_path = savedir / f"{safe_title}_audio.m4a" if audio_url else None
        output_path = savedir / f"{safe_title}.mp4"

        try:
            # 下载视频流
            logger.info(f"[BilibiliDownloader] 下载视频流: {video_url[:80]}")
            await self._download_file(video_url, video_path)

            # 下载音频流（如果有）
            if audio_url and not is_audio:
                logger.info(f"[BilibiliDownloader] 下载音频流: {audio_url[:80]}")
                await self._download_file(audio_url, audio_path)

            # 合并音视频（如果需要）
            if audio_path and audio_path.exists():
                logger.info(f"[BilibiliDownloader] 合并音视频: {output_path}")
                await self._merge_av(video_path, audio_path, output_path)
                # 清理临时文件
                video_path.unlink(missing_ok=True)
                audio_path.unlink(missing_ok=True)
            else:
                # 只下载了视频流（可能已经包含音频）
                os.rename(video_path, output_path)

            logger.info(f"[BilibiliDownloader] 下载完成: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"[BilibiliDownloader] 下载失败: {e}", exc_info=True)
            raise

    def _extract_bvid(self, url: str) -> Optional[str]:
        """从URL中提取 bvid"""
        patterns = [
            r"/video/(BV\w+)",
            r"bvid=(BV\w+)",
            r"/(BV\w+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    def _parse_quality(self, quality: str) -> int:
        """解析清晰度参数为数字"""
        if quality == "best":
            return 127
        if quality.isdigit():
            return int(quality)
        # 尝试从字符串中提取数字
        m = re.search(r"(\d+)", quality)
        return int(m.group(1)) if m else 80

    def _select_quality(
        self, play_info: dict, quality_num: int, is_audio: bool
    ) -> tuple[Optional[str], Optional[str]]:
        """
        选择合适的清晰度

        Returns:
            (video_url, audio_url)
        """
        dash = play_info.get("dash", {})
        if not dash:
            # 非DASH格式，直接返回URL
            return play_info.get("url"), None

        if is_audio:
            # 只下载音频
            audio = dash.get("audio", [])
            if audio:
                return audio[0].get("baseUrl"), None
            return None, None

        # 选择视频流
        videos = dash.get("video", [])
        selected = None
        for video in videos:
            if video.get("id") <= quality_num:
                selected = video
                break
        if not selected and videos:
            selected = videos[-1]  # 取最低清晰度

        video_url = selected.get("baseUrl") if selected else None
        audio_url = None
        if dash.get("audio"):
            audio_url = dash["audio"][0].get("baseUrl")

        return video_url, audio_url

    async def _download_file(self, url: str, output_path: Path, max_retries: int = 3):
        """下载文件（带重试）"""
        cookie_jar = get_cookie_manager().get_cookiejar_for_url(url)
        cookies_dict = {c.name: c.value for c in cookie_jar} if cookie_jar else {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    async with client.stream("GET", url, headers=headers, cookies=cookies_dict) as resp:
                        resp.raise_for_status()
                        with open(output_path, "wb") as f:
                            async for chunk in resp.aiter_bytes():
                                f.write(chunk)
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"[BilibiliDownloader] 下载失败，重试 {attempt + 2}/{max_retries}: {e}")
                await asyncio.sleep(2)

        raise ValueError(f"下载失败（已重试 {max_retries} 次）: {url[:80]}")

    async def _merge_av(self, video_path: Path, audio_path: Path, output_path: Path):
        """使用 ffmpeg 合并音视频"""
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            logger.warning("[BilibiliDownloader] 未找到 ffmpeg，跳过合并")
            # 只返回视频文件
            os.rename(video_path, output_path)
            return

        cmd = [
            str(ffmpeg),
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c", "copy",
            "-y",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise ValueError(f"ffmpeg 合并失败: {stderr.decode(errors='ignore')[:200]}")

    def _format_filesize(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes <= 0:
            return "未知"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}PB"

    def _safe_filename(self, name: str) -> str:
        """生成安全的文件名"""
        return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:100]
