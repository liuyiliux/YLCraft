"""
B站专用下载器

优先使用 BilibiliClient（WBI签名，需 Cookie）获取高清 DASH 视频
无 Cookie 时降级到免费 Web API（无需登录，/x/player/playurl）
返回 (文件路径, VideoInfo) 元组
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

import httpx

from app.services.download.base import BaseDownloader, VideoInfo, VideoQuality
from app.services.video.parser import get_cookie_manager
from app.core.config import ensure_download_path, get_ffmpeg_path
from app.services.platforms.types import ClientConfig
from app.services.platforms.bilibili.client import BilibiliClient

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


# =============================================================================
# 免费 API 兜底（无需 Cookie）
# =============================================================================

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_FREE_HEADERS = {"User-Agent": _USER_AGENT, "Referer": "https://www.bilibili.com/"}


def _extract_bvid_free(url: str) -> Optional[str]:
    for p in [r"/video/(BV[\w]{10})", r"bvid=(BV[\w]{10})", r"/(BV[\w]{10})"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


async def _call_free_api(url: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_FREE_HEADERS)
        resp.raise_for_status()
        return resp.json()


async def _parse_with_free_api(url: str) -> Optional[dict]:
    """
    使用 B站免费 Web API 解析（无需 Cookie）
    返回 dict: {title, author_name, cover_url, video_url, width, height, duration, qualities, bvid}
    失败返回 None
    """
    try:
        bvid = _extract_bvid_free(url)
        if not bvid:
            return None

        # 1. 获取视频元信息
        view = await _call_free_api(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
        if not isinstance(view.get("data"), dict) or view.get("code") != 0:
            return None

        v = view["data"]
        title = v.get("title", "")
        cover_url = v.get("pic", "")
        duration = int(v.get("duration", 0) or 0)

        owner = v.get("owner") or {}
        author_name = (owner.get("name") or "") if isinstance(owner, dict) else ""

        pages = v.get("pages") or []
        first_cid = (pages[0].get("cid") if pages else v.get("cid")) if isinstance(pages, list) else v.get("cid")
        if not first_cid:
            return None

        # 2. 获取播放地址（durl 格式，音视频合一）
        play = await _call_free_api(
            f"https://api.bilibili.com/x/player/playurl?"
            f"otype=json&fnver=0&fnval=0&qn=80&bvid={bvid}&cid={first_cid}&platform=html5"
        )
        play_data = play.get("data") or {}
        if not isinstance(play_data, dict) or play_data.get("code", 0) != 0:
            return None

        durl_list = play_data.get("durl") or []
        if not durl_list:
            return None

        best = durl_list[0]
        video_url = best.get("url", "") or ""
        if not video_url:
            return None

        # 获取分辨率
        width, height = 0, 0
        p0 = (pages[0] if pages else {}) if isinstance(pages, list) else {}
        width = int(p0.get("width") or v.get("width") or 0)
        height = int(p0.get("height") or v.get("height") or 0)

        qualities = []
        if len(durl_list) > 1:
            for i, d in enumerate(durl_list):
                u = d.get("url", "")
                if u:
                    qualities.append({"quality": f"分段{i+1}", "url": u,
                                     "resolution": f"{width}x{height}" if width and height else ""})
        else:
            qualities.append({"quality": "720P", "url": video_url,
                             "resolution": f"{width}x{height}" if width and height else ""})

        return {
            "title": title,
            "author_name": author_name,
            "cover_url": cover_url,
            "video_url": video_url,
            "width": width,
            "height": height,
            "duration": duration,
            "qualities": qualities,
            "bvid": bvid,
        }

    except Exception as e:
        logger.warning(f"[BilibiliDownloader] 免费API解析失败: {e}")
        return None


async def _download_file_simple(url: str, output_path: Path, max_retries: int = 3):
    """简单下载（单线程，带重试）"""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("GET", url, headers=_FREE_HEADERS) as resp:
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
    raise ValueError(f"下载失败（已重试 {max_retries} 次）")


async def _download_with_free_api(
    url: str, quality: str, title: Optional[str], is_audio: bool
) -> Optional[Tuple[str, VideoInfo]]:
    """
    使用免费 API 获取视频直链，直接下载（无需合并音视频）
    返回 (filepath, VideoInfo) 或 None
    """
    savedir = ensure_download_path()
    bvid = _extract_bvid_free(url)
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title or bvid or "bilibili")[:100]

    # 获取视频信息和播放地址
    parse_result = await _parse_with_free_api(url)
    if not parse_result or not parse_result.get("video_url"):
        return None

    video_url = parse_result["video_url"]
    output_path = savedir / f"{safe_title}.mp4"

    logger.info(f"[BilibiliDownloader] 免费API下载: {video_url[:80]}")

    try:
        await _download_file_simple(video_url, output_path)
        logger.info(f"[BilibiliDownloader] 免费API下载完成: {output_path}")

        info = VideoInfo(
            title=parse_result["title"],
            author=parse_result["author_name"],
            platform="bilibili",
            cover_url=parse_result["cover_url"],
            duration=parse_result["duration"],
            qualities=[
                VideoQuality(
                    quality=q["quality"],
                    resolution=q["resolution"],
                    filesize="未知",
                    url=q["url"],
                )
                for q in parse_result["qualities"]
            ],
            page_url=url,
        )
        return str(output_path), info

    except Exception as e:
        logger.warning(f"[BilibiliDownloader] 免费API下载失败: {e}")
        return None


# =============================================================================
# BilibiliDownloader
# =============================================================================

class BilibiliDownloader(BaseDownloader):
    """B站专用下载器（优先 WBI 签名，无 Cookie 时降级到免费 API）"""

    platform_name = "bilibili"

    def __init__(self):
        self._client = None
        self._has_cookie = False
        self._cached_parse_result: Optional[VideoInfo] = None

    async def _get_client(self) -> Tuple[Optional[BilibiliClient], bool]:
        """
        获取 BilibiliClient 实例
        返回 (client, has_cookie)
        如果无 Cookie，client=None 但 has_cookie=False（调用方需用免费 API 兜底）
        """
        if self._client is not None:
            return self._client, self._has_cookie

        cookie = ""
        has_cookie = False

        # 方式1：从平台连接服务获取 Cookie
        try:
            from app.services.platform_connection.service import PlatformConnectionService
            service = PlatformConnectionService()
            conn = service.get_default_connection("bilibili")
            if conn:
                cookie = service.get_raw_cookie(conn.id) or ""
                has_cookie = bool(cookie)
                logger.info(f"[BilibiliDownloader] 从连接服务获取Cookie: {has_cookie}")
        except Exception as e:
            logger.warning(f"[BilibiliDownloader] 从连接服务获取Cookie失败: {e}")

        # 方式2：从 CookieManager 获取
        if not has_cookie:
            try:
                cm = get_cookie_manager()
                jar = cm.get_cookiejar_for_url("https://www.bilibili.com")
                if jar:
                    cookie = "; ".join([f"{c.name}={c.value}" for c in jar])
                    has_cookie = bool(cookie)
                    logger.info(f"[BilibiliDownloader] 从CookieManager获取Cookie: {has_cookie}")
            except Exception as e:
                logger.warning(f"[BilibiliDownloader] 从CookieManager获取Cookie失败: {e}")

        if has_cookie:
            config = ClientConfig(platform="bilibili", cookie=cookie)
            self._client = BilibiliClient(config)
            self._has_cookie = True
            logger.info("[BilibiliDownloader] 使用 WBI 签名模式（有Cookie）")
        else:
            self._client = None
            self._has_cookie = False
            logger.info("[BilibiliDownloader] 使用免费API模式（无Cookie）")

        return self._client, self._has_cookie

    async def parse(self, url: str) -> Optional[VideoInfo]:
        """
        解析B站视频信息

        优先使用 BilibiliClient（WBI签名），失败则降级到免费 API
        结果缓存到 self._cached_parse_result，供 download() 使用
        """
        bvid = self._extract_bvid(url)
        if not bvid:
            logger.error(f"[BilibiliDownloader] 无法提取 bvid: {url}")
            return None

        # 尝试方式1：BilibiliClient（需 Cookie）
        client, has_cookie = await self._get_client()
        if has_cookie and client:
            try:
                info = await self._parse_with_client(client, bvid, url)
                if info:
                    self._cached_parse_result = info
                    return info
            except Exception as e:
                logger.warning(f"[BilibiliDownloader] WBI解析失败，降级到免费API: {e}")

        # 方式2：免费 API（无需 Cookie）
        logger.info(f"[BilibiliDownloader] 使用免费API解析: {bvid}")
        free_result = await _parse_with_free_api(url)
        if free_result:
            info = VideoInfo(
                title=free_result["title"],
                author=free_result["author_name"],
                platform="bilibili",
                cover_url=free_result["cover_url"],
                duration=free_result["duration"],
                qualities=[
                    VideoQuality(
                        quality=q["quality"],
                        resolution=q["resolution"],
                        filesize="未知",
                        url=q["url"],
                    )
                    for q in free_result["qualities"]
                ],
                page_url=url,
            )
            self._cached_parse_result = info
            return info

        logger.error(f"[BilibiliDownloader] 解析失败（WBI + 免费API均失败）: {bvid}")
        return None

    async def _parse_with_client(self, client, bvid: str, url: str) -> Optional[VideoInfo]:
        """使用 BilibiliClient 解析（需 Cookie）"""
        detail = await client.get_detail(bvid)
        if not detail:
            raise RuntimeError(f"get_detail 返回空: {bvid}")

        title = getattr(detail, "title", "") or ""
        if not title:
            raise RuntimeError(f"视频标题为空: {bvid}")

        play_info = await client.get_video_play_info(bvid)
        if not play_info or (not play_info.get("dash") and not play_info.get("durl")):
            raise RuntimeError(f"获取播放地址失败: {bvid}")

        qualities = []
        seen = set()
        if play_info.get("dash"):
            dash = play_info["dash"]
            video_duration = getattr(detail, "duration", 0) or 0
            videos = sorted(dash.get("video", []), key=lambda v: v.get("id", 0), reverse=True)
            for video in videos:
                qn = video.get("id", 0)
                label = BILI_QUALITY_MAP.get(qn, f"qn{qn}")
                w = video.get("width", 0)
                h = video.get("height", 0)
                res = f"{w}x{h}"
                if res in seen:
                    continue
                seen.add(res)
                filesize = self.calculate_filesize(
                    filesize_bytes=video.get("size"),
                    bitrate_bps=video.get("bandwidth", video.get("bitrate")),
                    duration_seconds=video_duration,
                )
                qualities.append(VideoQuality(
                    quality=label,
                    resolution=res,
                    filesize=filesize,
                    url=video.get("baseUrl", ""),
                ))

        return VideoInfo(
            title=title,
            author=getattr(detail, "author", "") or "",
            platform="bilibili",
            cover_url=getattr(detail, "video_cover", "") or "",
            duration=getattr(detail, "duration", 0) or 0,
            description=getattr(detail, "desc", "") or "",
            qualities=qualities,
            page_url=url,
        )

    async def download(
        self,
        url: str,
        quality: str = "best",
        title: Optional[str] = None,
        is_audio: bool = False,
    ) -> Tuple[str, Optional[VideoInfo]]:
        """
        下载B站视频
        优先使用 BilibiliClient（DASH格式，需合并音视频）
        无 Cookie 时降级到免费 API（durl格式，音视频合一，无需合并）
        返回 (文件路径, VideoInfo)
        """
        bvid = self._extract_bvid(url)
        if not bvid:
            raise ValueError(f"无法提取 bvid: {url}")

        client, has_cookie = await self._get_client()

        # 方式1：WBI 签名（需 Cookie）→ DASH 格式
        if has_cookie and client:
            try:
                filepath = await self._download_with_client(client, bvid, url, quality, title, is_audio)
                return filepath, self._cached_parse_result
            except Exception as e:
                logger.warning(f"[BilibiliDownloader] WBI下载失败，降级到免费API: {e}")

        # 方式2：免费 API（无需 Cookie）→ durl 格式
        logger.info(f"[BilibiliDownloader] 使用免费API下载: {bvid}")
        result = await _download_with_free_api(url, quality, title, is_audio)
        if result:
            # result 已经是 (filepath, VideoInfo)
            filepath, info = result
            self._cached_parse_result = info
            return filepath, info

        raise ValueError(f"B站下载失败（WBI + 免费API均失败）: {bvid}")

    async def _download_with_client(
        self, client, bvid: str, url: str,
        quality: str, title: Optional[str], is_audio: bool,
    ) -> str:
        """使用 BilibiliClient 下载（DASH格式，需合并音视频）"""
        play_info = await client.get_video_play_info(bvid)
        if not play_info:
            raise ValueError(f"获取播放地址失败: {bvid}")

        quality_num = self._parse_quality(quality)
        video_url, audio_url = self._select_quality(play_info, quality_num, is_audio)

        if not video_url:
            raise ValueError(f"未找到对应清晰度的下载链接: {quality}")

        savedir = ensure_download_path()
        safe_title = self._safe_filename(title or bvid)
        video_path = savedir / f"{safe_title}_video.mp4"
        audio_path = savedir / f"{safe_title}_audio.m4a" if audio_url else None
        output_path = savedir / f"{safe_title}.mp4"

        try:
            logger.info(f"[BilibiliDownloader] WBI模式下载视频流: {video_url[:80]}")
            await self._download_file(video_url, video_path)

            if audio_url and not is_audio:
                logger.info(f"[BilibiliDownloader] WBI模式下载音频流: {audio_url[:80]}")
                await self._download_file(audio_url, audio_path)

            if audio_path and audio_path.exists():
                logger.info(f"[BilibiliDownloader] 合并音视频: {output_path}")
                await self._merge_av(video_path, audio_path, output_path)
                video_path.unlink(missing_ok=True)
                audio_path.unlink(missing_ok=True)
            else:
                os.rename(video_path, output_path)

            logger.info(f"[BilibiliDownloader] WBI模式下载完成: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"[BilibiliDownloader] WBI模式下载失败: {e}", exc_info=True)
            raise

    def _extract_bvid(self, url: str) -> Optional[str]:
        """从URL中提取 bvid"""
        for pattern in [r"/video/(BV\w+)", r"bvid=(BV\w+)", r"/(BV\w+)"]:
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
        for qn, label in BILI_QUALITY_MAP.items():
            if label == quality:
                return qn
        m = re.search(r"(\d+)", quality)
        return int(m.group(1)) if m else 80

    def _select_quality(
        self, play_info: dict, quality_num: int, is_audio: bool
    ) -> Tuple[Optional[str], Optional[str]]:
        """选择合适的清晰度"""
        dash = play_info.get("dash", {})
        if not dash:
            return play_info.get("url"), None

        if is_audio:
            audio = dash.get("audio", [])
            if audio:
                return audio[0].get("baseUrl"), None
            return None, None

        videos = dash.get("video", [])
        selected = None
        for video in videos:
            if video.get("id") <= quality_num:
                selected = video
                break
        if not selected and videos:
            selected = videos[-1]

        video_url = selected.get("baseUrl") if selected else None
        audio_url = dash.get("audio", [{}])[0].get("baseUrl") if dash.get("audio") else None
        return video_url, audio_url

    async def _download_file(self, url: str, output_path: Path, max_retries: int = 3):
        """下载文件（带重试，带 Referer）"""
        cookie_jar = get_cookie_manager().get_cookiejar_for_url(url)
        cookies_dict = {c.name: c.value for c in cookie_jar} if cookie_jar else {}

        headers = {
            "User-Agent": _USER_AGENT,
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
            os.rename(video_path, output_path)
            return

        cmd = [str(ffmpeg), "-i", str(video_path), "-i", str(audio_path), "-c", "copy", "-y", str(output_path)]
        import subprocess
        loop = asyncio.get_running_loop()

        def run_ffmpeg():
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            return result.returncode, result.stderr

        returncode, stderr = await loop.run_in_executor(None, run_ffmpeg)
        if returncode != 0:
            raise ValueError(f"ffmpeg 合并失败: {stderr[:200]}")

    def _safe_filename(self, name: str) -> str:
        """生成安全的文件名"""
        return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:100]
