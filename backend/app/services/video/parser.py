"""YLCraft — 视频解析模块

统一使用 yt-dlp 解析所有平台（支持 1000+ 网站）。
支持平台：抖音/快手/B站/小红书/微博/YouTube/TikTok 等。

抖音特殊说明（iesdouyin.com 方案）：
- 抖音桌面端 API 需要 msToken HttpOnly Cookie，
  无法通过浏览器插件导出，改用移动端 iesdouyin.com/share/video/{id}/ 页面方案。
- 该页面 HTML 中嵌入 window._ROUTER_DATA JSON，完全无需 Cookie 即可解析。
- 参考：yby6-video-parser skill 的 douyin.py 实现。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("ylcraft.parser")


# =============================================================================
# Cookie 管理
# =============================================================================

class CookieManager:
    """
    Cookie 管理器。
    每个平台一个 .txt 文件（Netscape 格式），存放在 config/cookies/ 目录。
    """

    PLATFORM_DOMAINS: dict[str, str] = {
        "douyin": ".douyin.com",
        "tiktok": ".tiktok.com",
        "kuaishou": ".kuaishou.com",
        "bilibili": ".bilibili.com",
        "xiaohongshu": ".xiaohongshu.com",
        "weibo": ".weibo.com",
        "youtube": ".youtube.com",
    }

    def __init__(self, cookies_dir: str | None = None):
        if cookies_dir:
            self.cookies_dir = Path(cookies_dir)
        else:
            backend_dir = Path(__file__).parent.parent.parent
            self.cookies_dir = backend_dir / "config" / "cookies"
        self.cookies_dir.mkdir(parents=True, exist_ok=True)

    def get_cookie_path(self, platform: str) -> Path:
        return self.cookies_dir / f"{platform}.txt"

    def get_cookie_path_for_url(self, url: str) -> Optional[Path]:
        platform = _detect_platform(url)
        path = self.get_cookie_path(platform)
        return path if path.exists() else None

    def save_cookie(self, platform: str, cookie_content: str) -> Path:
        path = self.get_cookie_path(platform)
        path.parent.mkdir(parents=True, exist_ok=True)
        cookie_content = cookie_content.strip()

        if cookie_content.startswith("# Netscape HTTP Cookie File"):
            path.write_text(cookie_content, encoding="utf-8")
            logger.info(f"[CookieManager] 保存 {platform}（Netscape 格式）→ {path}")
            return path

        try:
            data = json.loads(cookie_content)
            if isinstance(data, list) and len(data) > 0:
                lines = ["# Netscape HTTP Cookie File", ""]
                for c in data:
                    name = c.get("name", "")
                    value = c.get("value", "")
                    domain = c.get("domain") or self.PLATFORM_DOMAINS.get(platform, ".example.com")
                    path_val = c.get("path", "/")
                    secure = "TRUE" if c.get("secure", True) else "FALSE"
                    expires = str(int(c.get("expirationDate") or c.get("expires", 0)))
                    is_dot = "TRUE" if domain.startswith(".") else "FALSE"
                    lines.append(f"{domain}\t{is_dot}\t{path_val}\t{secure}\t{expires}\t{name}\t{value}")
                path.write_text("\n".join(lines), encoding="utf-8")
                logger.info(f"[CookieManager] 保存 {platform}（JSON→Netscape，{len(data)} 条）→ {path}")
                return path
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        import time as _time
        lines = ["# Netscape HTTP Cookie File", ""]
        default_domain = self.PLATFORM_DOMAINS.get(platform, ".example.com")
        default_expires = str(int(_time.time()) + 86400 * 30)
        pairs = re.findall(r"([^=]+)=([^;]*)(?:;|$)", cookie_content)
        if pairs:
            for name, value in pairs:
                name = name.strip()
                value = value.strip()
                if not name:
                    continue
                lines.append(f"{default_domain}\tTRUE\t/\tFALSE\t{default_expires}\t{name}\t{value}")
            path.write_text("\n".join(lines), encoding="utf-8")
            logger.info(f"[CookieManager] 保存 {platform}（Raw→Netscape，{len(pairs)} 条）→ {path}")
            return path

        path.write_text(cookie_content, encoding="utf-8")
        logger.warning(f"[CookieManager] 保存 {platform}（格式未知，原文写入）→ {path}")
        return path

    def delete_cookie(self, platform: str) -> bool:
        path = self.get_cookie_path(platform)
        if path.exists():
            path.unlink()
            logger.info(f"[CookieManager] 已删除 {platform} Cookie")
            return True
        return False

    def list_cookies(self) -> dict[str, dict]:
        result = {}
        if not self.cookies_dir.exists():
            return result
        for f in self.cookies_dir.glob("*.txt"):
            platform = f.stem
            stat = f.stat()
            result[platform] = {
                "path": str(f),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        return result


_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class VideoInfo:
    """解析后的视频信息（统一格式）"""
    original_url: str
    platform: str = ""

    video_url: str = ""
    audio_url: str = ""
    cover_url: str = ""
    images: list = field(default_factory=list)

    title: str = ""
    desc: str = ""
    author_name: str = ""
    author_uid: str = ""
    author_avatar: str = ""
    duration: int = 0
    width: int = 0
    height: int = 0

    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    play_count: int = 0

    content_type: str = "video"
    qualities: list = field(default_factory=list)
    parse_method: str = ""
    raw: dict = field(default_factory=dict)

    def is_valid(self) -> bool:
        return bool(self.video_url) or bool(self.images)


# =============================================================================
# 通用工具
# =============================================================================

def _detect_platform(url: str) -> str:
    """从 URL 检测平台"""
    url_lower = url.lower()
    if any(x in url_lower for x in ["douyin.com", "iesdouyin.com", "v.douyin"]):
        return "douyin"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if any(x in url_lower for x in ["kuaishou.com", "gifshow.com", "v.kuaishou"]):
        return "kuaishou"
    if any(x in url_lower for x in ["bilibili.com", "b23.tv"]):
        return "bilibili"
    if any(x in url_lower for x in ["xiaohongshu.com", "xhslink.com"]):
        return "xiaohongshu"
    if any(x in url_lower for x in ["weibo.com", "t.cn"]):
        return "weibo"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    return "unknown"


def _extract_url_from_text(text: str) -> str:
    """从分享文本中提取 URL"""
    pattern = r"https?://[^\s\u4e00-\u9fff]+"
    matches = re.findall(pattern, text)
    if matches:
        preferred_domains = [
            "v.douyin.com", "iesdouyin.com", "douyin.com",
            "v.kuaishou.com", "kuaishou.com",
            "b23.tv", "bilibili.com",
            "xhslink.com", "xiaohongshu.com",
            "t.cn", "weibo.com",
        ]
        for domain in preferred_domains:
            for url in matches:
                if domain in url:
                    return url
        return matches[0]
    return text.strip()


def _ytdlp_best_url(data: dict) -> str:
    """从 yt-dlp 数据中选择最佳视频 URL"""
    if data.get("url"):
        return data["url"]
    formats = data.get("formats", [])
    if not formats:
        return ""
    video_fmts = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
    if not video_fmts:
        for f in reversed(formats):
            if f.get("url"):
                return f["url"]
        return ""
    mp4_fmts = [f for f in video_fmts if f.get("ext") == "mp4"]
    target = mp4_fmts or video_fmts
    target.sort(key=lambda f: f.get("height") or 0, reverse=True)
    return target[0]["url"]


async def _parse_with_ytdlp(url: str, platform: str = "unknown") -> VideoInfo:
    """使用 yt-dlp Python 模块解析任意支持平台的视频（绕过 subprocess）。"""
    info = VideoInfo(original_url=url, platform=platform)
    logger.info(f"[parser.ytdlp] called with url={url[:80]}")

    try:
        import yt_dlp as _yt_dlp

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "http_headers": {"User-Agent": "Mozilla/5.0"},
        }

        cookie_path = get_cookie_manager().get_cookie_path_for_url(url)
        if cookie_path:
            ydl_opts["cookiefile"] = str(cookie_path)
            logger.info(f"[parser] 使用 Cookie: {cookie_path}")

        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None, lambda: _yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
        )

        if data:
            info.title = data.get("title", "") or ""
            info.desc = data.get("description", "") or ""
            info.author_name = data.get("uploader") or data.get("channel") or ""
            info.author_uid = data.get("uploader_id") or data.get("channel_id") or ""
            info.duration = int(data.get("duration") or 0)
            info.like_count = int(data.get("like_count") or 0)
            info.comment_count = int(data.get("comment_count") or 0)
            info.play_count = int(data.get("view_count") or 0)
            raw_thumb = data.get("thumbnail") or data.get("thumb") or ""
            # Bilibili yt-dlp 返回的 thumbnail URL 常缺少扩展名，自动补上 .jpg
            if raw_thumb and not raw_thumb.rsplit('.', 1)[-1].lower() in ('jpg', 'jpeg', 'png', 'webp'):
                raw_thumb += '.jpg'
            info.cover_url = raw_thumb
            info.cover_url = info.cover_url.replace('http://', 'https://') if info.cover_url else ''
            logger.info(f"[parser] yt-dlp raw cover={info.cover_url[:80] if info.cover_url else '**EMPTY**'}")
            best_url = _ytdlp_best_url(data)
            info.video_url = best_url
            info.parse_method = "ytdlp" + ("+cookie" if cookie_path else "")
            info.raw = {k: v for k, v in data.items() if k not in ("formats",)}
            logger.info(f"[parser] yt-dlp raw title={info.title[:30] if info.title else '**EMPTY**'}")
        else:
            info.parse_method = "ytdlp_no_data"

    except asyncio.TimeoutError:
        info.parse_method = "ytdlp_timeout"
    except FileNotFoundError:
        info.parse_method = "ytdlp_not_found"
    except Exception as e:
        info.parse_method = f"ytdlp_exception:{e}"
        logger.warning(f"[parser.ytdlp] exception: {e}")

    return info


# =============================================================================
# 主入口
# =============================================================================

async def parse(url_or_text: str) -> VideoInfo:
    """
    解析视频链接（主入口）。
    - 抖音 → iesdouyin.com 方案（无需 Cookie）
    - B站 → 官方 API（无需 Cookie）
    - 其他平台 → yt-dlp
    """
    if not url_or_text.startswith("http"):
        url = _extract_url_from_text(url_or_text)
    else:
        url = url_or_text.strip()

    platform = _detect_platform(url)
    info = VideoInfo(original_url=url, platform=platform)

    # B站使用官方 API（无需 Cookie，比 yt-dlp 更稳定）
    if platform == "bilibili":
        try:
            from app.services.video.parser_bilibili import parse_bilibili
            result = await parse_bilibili(url)
            if result.get("video_url") or result.get("images"):
                info.video_url = result.get("video_url", "")
                info.cover_url = result.get("cover_url", "")
                info.title = result.get("title", "")
                info.author_name = result.get("author_name", "")
                info.author_uid = result.get("author_uid", "")
                info.author_avatar = result.get("author_avatar", "")
                info.duration = result.get("duration", 0)
                info.like_count = result.get("like_count", 0)
                info.comment_count = result.get("comment_count", 0)
                info.share_count = result.get("share_count", 0)
                info.play_count = result.get("play_count", 0)
                info.content_type = result.get("content_type", "video")
                info.images = result.get("images", [])
                info.qualities = result.get("qualities", [])
                info.parse_method = result.get("parse_method", "bilibili_api")
                info.raw = result.get("raw", {})
                return info
            else:
                logger.warning("[parser] B站 API 解析失败，fallback 到 yt-dlp")
        except Exception as e:
            logger.warning(f"[parser] B站 API 解析异常，fallback 到 yt-dlp: {e}")

    # 抖音使用 iesdouyin.com 移动端方案（无需 Cookie）
    if platform == "douyin":
        try:
            from app.services.video.parser_douyin import parse_douyin
            result = await parse_douyin(url)
            if result.get("video_url") or result.get("images"):
                info.video_url = result.get("video_url", "")
                info.cover_url = result.get("cover_url", "")
                info.title = result.get("title", "")
                info.author_name = result.get("author_name", "")
                info.author_uid = result.get("author_uid", "")
                info.author_avatar = result.get("author_avatar", "")
                info.duration = result.get("duration", 0)
                info.like_count = result.get("like_count", 0)
                info.comment_count = result.get("comment_count", 0)
                info.share_count = result.get("share_count", 0)
                info.play_count = result.get("play_count", 0)
                info.content_type = result.get("content_type", "video")
                info.images = result.get("images", [])
                info.qualities = result.get("qualities", [])
                info.parse_method = result.get("parse_method", "iesdouyin")
                info.raw = result.get("raw", {})
                # 覆盖为 iesdouyin 分享页 URL（yt-dlp 下载必须用这个）
                info.original_url = result.get("original_url") or info.original_url
                return info
            else:
                logger.warning("[parser] iesdouyin 解析失败，fallback 到 yt-dlp")
        except Exception as e:
            logger.warning(f"[parser] iesdouyin 解析异常，fallback 到 yt-dlp: {e}")

    # 所有平台统一用 yt-dlp 兜底
    ytdlp_info = await _parse_with_ytdlp(url, platform)
    if ytdlp_info.is_valid():
        info.video_url = ytdlp_info.video_url or info.video_url
        info.title = ytdlp_info.title or info.title
        info.author_name = ytdlp_info.author_name or info.author_name
        info.cover_url = ytdlp_info.cover_url or info.cover_url
        info.duration = ytdlp_info.duration or info.duration
        info.parse_method = ytdlp_info.parse_method
        info.raw = ytdlp_info.raw

    return info


# =============================================================================
# 下载
# =============================================================================

async def download(info: VideoInfo, output_path: str) -> bool:
    """下载视频到指定路径"""
    if not info.is_valid():
        return False
    success = await _download_with_ytdlp(info.original_url, output_path)
    if success:
        return True
    if info.video_url and info.video_url.startswith("http"):
        return await _download_direct(info.video_url, output_path)
    return False


async def _download_with_ytdlp(url: str, output_path: str) -> bool:
    """使用 yt-dlp 下载视频"""
    try:
        backend_dir = Path(__file__).parent.parent.parent
        ytdlp_exe = backend_dir / "venv" / "Scripts" / "yt-dlp.exe"

        cmd = [
            str(ytdlp_exe),
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "-o", output_path,
        ]

        cookie_path = get_cookie_manager().get_cookie_path_for_url(url)
        if cookie_path:
            cmd.extend(["--cookies", str(cookie_path)])

        cmd.append(url)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        return proc.returncode == 0
    except (asyncio.TimeoutError, FileNotFoundError, Exception):
        return False


async def _download_direct(url: str, output_path: str) -> bool:
    """直接 HTTP 下载（兜底）"""
    _UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _UA, "Referer": url},
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0),
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code == 200:
                    with open(output_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                    return True
    except Exception:
        pass
    return False


# =============================================================================
# 转为 breaker 兼容格式（向后兼容）
# =============================================================================

def to_breaker_format(info: VideoInfo) -> dict:
    """将 VideoInfo 转换为 breaker service 期望的格式"""
    return {
        "video_url": info.video_url,
        "cover_url": info.cover_url,
        "title": info.title,
        "author": {
            "name": info.author_name,
            "uid": info.author_uid,
            "avatar": info.author_avatar,
        },
        "platform": info.platform,
        "duration": info.duration,
        "like_count": info.like_count,
        "comment_count": info.comment_count,
        "share_count": info.share_count,
        "play_count": info.play_count,
        "content_type": info.content_type,
        "images": info.images,
        "parse_method": info.parse_method,
    }
