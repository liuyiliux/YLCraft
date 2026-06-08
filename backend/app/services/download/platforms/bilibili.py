"""
B站专用下载器

优先使用 BilibiliClient（WBI签名，需 Cookie）获取高清 DASH 视频
无 Cookie 时降级到免费 Web API（无需登录，/x/player/playurl）
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
from app.services.platforms.bilibili.utils import (
    BILI_QUALITY_MAP,
    _quality_to_resolution,
    _get_filesize_for_qn,
    _normalize_resolution,
)

logger = logging.getLogger("ylcraft.download.bilibili")

# =============================================================================
# 免费 API 兜底（无需 Cookie）
# =============================================================================

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_FREE_HEADERS = {"User-Agent": _USER_AGENT, "Referer": "https://www.bilibili.com/"}


def _bilibili_download_dir() -> Path:
    savedir = ensure_download_path("bilibili")
    savedir.mkdir(parents=True, exist_ok=True)
    return savedir


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


async def _parse_with_free_api(url: str, default_qn: int = 80) -> Optional[dict]:
    """
    使用 B站免费 Web API 解析（无需 Cookie）
    返回 dict: {title, author_name, cover_url, video_url, width, height, duration, qualities}
    失败返回 None

    使用 durl 格式获取所有可用清晰度，通过解析 accept_quality / accept_description
    为每种画质获取对应 URL。
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
            f"otype=json&fnver=0&fnval=0&qn={default_qn}&bvid={bvid}"
            f"&cid={first_cid}&platform=html5"
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

        # 从 API 返回的 view 数据获取 width/height（部分视频不会返回）
        width, height = 0, 0
        p0 = (pages[0] if pages else {}) if isinstance(pages, list) else {}
        width = int(p0.get("dimension", {}).get("width") or p0.get("width") or v.get("width") or 0)
        height = int(p0.get("dimension", {}).get("height") or p0.get("height") or v.get("height") or 0)

        # 3. 解析所有可用清晰度（accept_quality / accept_description）
        accept_quality = play_data.get("accept_quality", [])
        accept_description = play_data.get("accept_description", [])
        current_qn = play_data.get("quality", default_qn)

        qualities = []

        if accept_quality and accept_description and len(accept_quality) == len(accept_description):
            # 有完整的 accept_quality / accept_description，构建多清晰度列表
            # 当前请求的 qn 已有 URL，其他 qn 需要额外请求
            urls_by_qn: dict = {}

            # 并行获取其他清晰度的 URL
            other_qns = [qn for qn in accept_quality if qn != current_qn]
            if other_qns:
                async def fetch_qn_url(qn: int) -> Optional[tuple]:
                    try:
                        q_play = await _call_free_api(
                            f"https://api.bilibili.com/x/player/playurl?"
                            f"otype=json&fnver=0&fnval=0&qn={qn}&bvid={bvid}"
                            f"&cid={first_cid}&platform=html5"
                        )
                        q_data = q_play.get("data", {})
                        q_durl = q_data.get("durl", [])
                        if q_durl:
                            return (qn, q_durl[0].get("url", ""), q_durl[0].get("size", 0))
                    except Exception as e:
                        logger.debug(f"[BilibiliDownloader] 获取qn={qn}的URL失败: {e}")
                    return None

                results = await asyncio.gather(*[fetch_qn_url(qn) for qn in other_qns])
                for r in results:
                    if r:
                        urls_by_qn[r[0]] = (r[1], r[2])  # (url, size_bytes)

            # 当前 qn 的 URL 和 size
            current_size = durl_list[0].get("size", 0) if durl_list else 0
            urls_by_qn[current_qn] = (video_url, current_size)

            # 按照 accept_quality 顺序构建 qualities（API 已按清晰度从高到低排列）
            for qn, desc in zip(accept_quality, accept_description):
                q_info = urls_by_qn.get(qn, (video_url, 0))
                q_url, q_size = q_info if isinstance(q_info, tuple) else (q_info, 0)
                # 每个 qn 用自己的分辨率：优先从映射表读取，其次用 view API 的高度推算
                q_res = _quality_to_resolution(qn, height)
                qualities.append({
                    "quality": desc,
                    "url": q_url,
                    "resolution": q_res,
                    "filesize": _get_filesize_for_qn(qn, q_size, duration),
                })
        elif len(durl_list) > 1:
            # 分段视频（极少见）
            for i, d in enumerate(durl_list):
                u = d.get("url", "")
                if u:
                    res = _quality_to_resolution(current_qn, height)
                    sz = d.get("size", 0)
                    qualities.append({
                        "quality": f"分段{i+1}",
                        "url": u,
                        "resolution": res or "",
                        "filesize": _get_filesize_for_qn(current_qn, sz, duration),
                    })
        else:
            # 无 accept_quality，仅返回一个清晰度
            label = BILI_QUALITY_MAP.get(current_qn, f"清晰度{current_qn}")
            res = _quality_to_resolution(current_qn, height)
            sz = durl_list[0].get("size", 0) if durl_list else 0
            qualities.append({
                "quality": label,
                "url": video_url,
                "resolution": res,
                "filesize": _get_filesize_for_qn(current_qn, sz, duration),
            })

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
            "aid": v.get("aid", 0),
            "cid": first_cid,
        }

    except Exception as e:
        logger.warning(f"[BilibiliDownloader] 免费API解析失败: {e}")
        return None


async def _download_with_free_api(
    url: str, quality: str, title: Optional[str], is_audio: bool
) -> Optional[str]:
    """
    使用免费 API 获取视频直链，直接下载（无需合并音视频）
    根据 quality 参数选择对应的清晰度 qn。
    """
    savedir = _bilibili_download_dir()
    bvid = _extract_bvid_free(url)
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title or bvid or "bilibili")[:100]

    # 解析清晰度参数 → qn 编号
    target_qn = 80  # 默认 1080P
    if quality and quality.isdigit():
        target_qn = int(quality)
    elif quality and quality != "best":
        # quality 可能是 "1080P" / "720P" 等标签
        for qn, label in BILI_QUALITY_MAP.items():
            if label == quality:
                target_qn = qn
                break

    # 获取播放地址（使用指定的 qn）
    result = await _parse_with_free_api(url, default_qn=target_qn)
    if not result or not result.get("video_url"):
        return None

    video_url = result["video_url"]
    output_path = savedir / f"{safe_title}.mp4"

    logger.info(f"[BilibiliDownloader] 免费API下载 (qn={target_qn}): {video_url[:80]}")

    try:
        await _download_file_simple(video_url, output_path)
        logger.info(f"[BilibiliDownloader] 免费API下载完成: {output_path}")
        return str(output_path)
    except Exception as e:
        logger.warning(f"[BilibiliDownloader] 免费API下载失败: {e}")
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


# =============================================================================
# BilibiliDownloader
# =============================================================================

class BilibiliDownloader(BaseDownloader):
    """B站专用下载器（优先 WBI 签名，无 Cookie 时降级到免费 API）"""

    platform_name = "bilibili"

    def __init__(self):
        self._client = None
        self._has_cookie = False

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
        """
        bvid = self._extract_bvid(url)
        if not bvid:
            logger.error(f"[BilibiliDownloader] 无法提取 bvid: {url}")
            return None

        # 尝试方式1：BilibiliClient（需 Cookie）
        client, has_cookie = await self._get_client()
        if has_cookie and client:
            try:
                return await self._parse_with_client(client, bvid, url)
            except Exception as e:
                logger.warning(f"[BilibiliDownloader] WBI解析失败，降级到免费API: {e}")

        # 方式2：免费 API（无需 Cookie）
        logger.info(f"[BilibiliDownloader] 使用免费API解析: {bvid}")
        free_result = await _parse_with_free_api(url)
        if free_result:
            return VideoInfo(
                title=free_result["title"],
                author=free_result["author_name"],
                platform="bilibili",
                cover_url=free_result["cover_url"],
                duration=free_result["duration"],
                qualities=[
                    VideoQuality(
                        quality=q["quality"],
                        resolution=q["resolution"],
                        filesize=q.get("filesize", "未知"),
                        url=q["url"],
                    )
                    for q in free_result["qualities"]
                ],
                page_url=url,
                raw={
                    "bvid": free_result.get("bvid", ""),
                    "aid": free_result.get("aid", 0),
                    "cid": free_result.get("cid", 0),
                    "width": free_result.get("width", 0),
                    "height": free_result.get("height", 0),
                },
            )

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
                res = _normalize_resolution(f"{w}x{h}")
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
            raw={
                "bvid": bvid,
                "aid": (detail.raw_data or {}).get("aid", 0) if getattr(detail, "raw_data", None) else 0,
                "cid": (
                    ((detail.raw_data or {}).get("pages") or [{}])[0].get("cid", 0)
                    if getattr(detail, "raw_data", None) else 0
                ),
                "width": (
                    (((detail.raw_data or {}).get("pages") or [{}])[0].get("dimension") or {}).get("width", 0)
                    if getattr(detail, "raw_data", None) else 0
                ),
                "height": (
                    (((detail.raw_data or {}).get("pages") or [{}])[0].get("dimension") or {}).get("height", 0)
                    if getattr(detail, "raw_data", None) else 0
                ),
            },
        )

    async def download(
        self,
        url: str,
        quality: str = "best",
        title: Optional[str] = None,
        is_audio: bool = False,
    ) -> str:
        """
        下载B站视频
        优先使用 BilibiliClient（DASH格式，需合并音视频）
        无 Cookie 时降级到免费 API（durl格式，音视频合一，无需合并）
        """
        bvid = self._extract_bvid(url)
        if not bvid:
            raise ValueError(f"无法提取 bvid: {url}")

        client, has_cookie = await self._get_client()

        # 方式1：WBI 签名（需 Cookie）→ DASH 格式
        if has_cookie and client:
            try:
                return await self._download_with_client(client, bvid, url, quality, title, is_audio)
            except Exception as e:
                logger.warning(f"[BilibiliDownloader] WBI下载失败，降级到免费API: {e}")
                # 继续到方式2

        # 方式2：免费 API（无需 Cookie）→ durl 格式
        logger.info(f"[BilibiliDownloader] 使用免费API下载: {bvid}")
        result = await _download_with_free_api(url, quality, title, is_audio)
        if result:
            return result

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

        savedir = _bilibili_download_dir()
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
