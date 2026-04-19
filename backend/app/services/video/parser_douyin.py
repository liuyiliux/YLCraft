"""YLCraft — 抖音视频解析器（iesdouyin.com 方案，无需 Cookie）

原理：
- 抖音的移动端分享页面（www.iesdouyin.com/share/video/{id}/）HTML 中
  嵌入了 window._ROUTER_DATA JSON，包含完整的视频元数据
- 这个页面无需登录即可访问，完全绕过 yt-dlp 的 msToken Cookie 依赖

支持的 URL 格式：
- https://v.douyin.com/xxx        （短链接，自动重定向）
- https://www.douyin.com/video/7323448304087831819
- https://www.douyin.com/jingxuan?modal_id=7616681950870326537
- https://www.iesdouyin.com/share/video/7323448304087831819/
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx

logger = logging.getLogger("ylcraft.parser.douyin")

# iesdouyin 页面请求头（只用 User-Agent，不要加 Referer，会被反爬拦截）
_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def _get_headers() -> dict:
    """请求头（只有 UA，和 skill 保持一致）"""
    return {"User-Agent": _MOBILE_UA}


def _extract_video_id(url: str) -> Optional[str]:
    """从各类抖音 URL 中提取视频 ID"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host == "v.douyin.com":
        try:
            with httpx.Client(follow_redirects=True, timeout=15.0) as client:
                resp = client.get(url, headers={"User-Agent": _MOBILE_UA})
                final_url = str(resp.url)
                final_parsed = urlparse(final_url)
                query_params = parse_qs(final_parsed.query)
                if "modal_id" in query_params:
                    return query_params["modal_id"][0]
                path = final_parsed.path.strip("/")
                return path.split("/")[-1] if path else None
        except Exception as e:
            logger.warning(f"短链接解析失败: {e}")
            return None

    if host in ("www.iesdouyin.com", "www.douyin.com", "douyin.com"):
        query_params = parse_qs(parsed.query)
        if "modal_id" in query_params:
            return query_params["modal_id"][0]
        path = parsed.path.strip("/")
        segments = path.split("/")
        if segments:
            return segments[-1]

    return None


async def _fetch_with_redirect(url: str) -> str:
    """异步请求，返回最终 URL（跟随所有重定向）"""
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(url, headers={"User-Agent": _MOBILE_UA})
        return str(resp.url)


async def _extract_video_id_async(url: str) -> Optional[str]:
    """异步版本：从各类抖音 URL 中提取视频 ID"""
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host == "v.douyin.com":
        try:
            final_url = await _fetch_with_redirect(url)
            final_parsed = urlparse(final_url)
            query_params = parse_qs(final_parsed.query)
            if "modal_id" in query_params:
                return query_params["modal_id"][0]
            path = final_parsed.path.strip("/")
            return path.split("/")[-1] if path else None
        except Exception as e:
            logger.warning(f"短链接解析失败: {e}")
            return None

    if host in ("www.iesdouyin.com", "www.douyin.com", "douyin.com", "iesdouyin.com"):
        query_params = parse_qs(parsed.query)
        if "modal_id" in query_params:
            return query_params["modal_id"][0]
        path = parsed.path.strip("/")
        segments = path.split("/")
        if segments:
            return segments[-1]

    return None


def _pick_best_video_url(url_list: list) -> str:
    """从 URL 列表中选择最佳质量（通常第一个是最高清）"""
    if not url_list:
        return ""
    return url_list[0]


async def _get_video_redirect_url(video_url: str) -> str:
    """
    获取视频最终 CDN 重定向地址。
    抖音的 play URL (无水印) 会先 302 重定向到真实 CDN 地址，
    用 follow_redirects=False 拿 location header。
    """
    if not video_url:
        return ""
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=15.0) as client:
            resp = await client.get(video_url, headers=_get_headers())
            redirect_url = resp.headers.get("location")
            return redirect_url or video_url
    except Exception:
        return video_url


def _get_str(d, key, default=""):
    """安全获取字符串字段"""
    v = d.get(key) if isinstance(d, dict) else None
    return str(v) if v is not None else default


def _get_list(d, key):
    """安全获取列表字段"""
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, list) else []


def _get_avatar_url(author):
    """安全提取作者头像 URL"""
    at = author.get("avatar_thumb") if isinstance(author, dict) else None
    if isinstance(at, dict):
        ul = at.get("url_list")
        if isinstance(ul, list) and ul:
            first = ul[0]
            if isinstance(first, dict):
                url = first.get("url")
                if url:
                    return str(url)
    return ""


async def parse_douyin(url: str) -> dict:
    """
    用 iesdouyin.com 方案解析抖音视频。

    返回 dict（兼容 VideoInfo 字段）：
    {
        "video_url": "...",        # 无水印直链
        "cover_url": "...",        # 封面图
        "title": "...",
        "author_name": "...",
        "duration": 0,
        "platform": "douyin",
        "qualities": [...],
        "parse_method": "iesdouyin",
        "raw": {...}
    }

    解析失败返回空 dict，外层会 fallback 到 yt-dlp。
    """
    import traceback as _tb

    try:
        # 1. 提取视频 ID
        video_id = await _extract_video_id_async(url)
        if not video_id:
            logger.warning(f"[douyin] 无法从 URL 提取视频ID: {url}")
            return {}

        logger.info(f"[douyin] 视频ID: {video_id}")

        # 2. 请求移动端分享页面
        share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
        headers = _get_headers()

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(share_url, headers=headers)

        if resp.status_code != 200:
            logger.warning(f"[douyin] iesdouyin 页面返回 {resp.status_code}: {share_url}")
            return {}

        # 3. 从 HTML 提取 window._ROUTER_DATA
        pattern = re.compile(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", re.DOTALL)
        match = pattern.search(resp.text)

        if not match or not match.group(1).strip():
            logger.warning("[douyin] 无法提取 _ROUTER_DATA，页面可能需要登录或被反爬拦截")
            return {}

        json_str = match.group(1).strip()
        data = json.loads(json_str)

        # 4. 提取视频信息
        loader_data = data.get("loaderData", {})
        if not isinstance(loader_data, dict):
            logger.warning(f"[douyin] loader_data 类型异常: {type(loader_data).__name__}")
            return {}

        video_page_key = "video_(id)/page"
        if video_page_key not in loader_data:
            logger.warning(f"[douyin] 非视频页面类型，loaderData keys: {list(loader_data.keys())}")
            return {}

        video_info_res = loader_data[video_page_key].get("videoInfoRes", {})
        item_list = video_info_res.get("item_list", []) if isinstance(video_info_res, dict) else []

        if not item_list:
            logger.warning("[douyin] item_list 为空，账号或视频可能受限")
            return {}

        video_data = item_list[0]
        if not isinstance(video_data, dict):
            logger.warning("[douyin] video_data 格式异常")
            return {}

        desc = _get_str(video_data, "desc")
        author = video_data.get("author") if isinstance(video_data, dict) else {}
        nickname = _get_str(author if isinstance(author, dict) else {}, "nickname", "未知作者")

        # 视频信息
        video_info = video_data.get("video") if isinstance(video_data, dict) else {}
        if not isinstance(video_info, dict):
            video_info = {}

        play_addr = video_info.get("play_addr") if isinstance(video_info, dict) else None
        play_addr = play_addr if isinstance(play_addr, dict) else {}
        url_list_raw = play_addr.get("url_list") if isinstance(play_addr, dict) else None
        url_list = url_list_raw if isinstance(url_list_raw, list) else []

        # 无水印 URL：把 playwm 替换为 play，再获取最终重定向地址
        wm_url = _pick_best_video_url(url_list)
        wm_url = wm_url.replace("playwm", "play") if wm_url else ""
        video_url = await _get_video_redirect_url(wm_url) if wm_url else ""

        # 封面
        cover = video_info.get("cover") if isinstance(video_info, dict) else None
        cover = cover if isinstance(cover, dict) else {}
        cover_url_list_raw = cover.get("url_list") if isinstance(cover, dict) else None
        cover_url_list = cover_url_list_raw if isinstance(cover_url_list_raw, list) else []
        cover_url = next((u for u in cover_url_list if not u.endswith(".webp")), cover_url_list[0] if cover_url_list else "")

        # 时长（毫秒转秒）
        duration_ms = video_info.get("duration", 0) or 0
        duration = int(duration_ms / 1000) if duration_ms else 0

        # 统计
        statistics = video_data.get("statistics") if isinstance(video_data, dict) else {}
        statistics = statistics if isinstance(statistics, dict) else {}
        play_count = int(statistics.get("play_count", 0) or 0)
        like_count = int(statistics.get("digg_count", 0) or 0)
        comment_count = int(statistics.get("comment_count", 0) or 0)
        share_count = int(statistics.get("share_count", 0) or 0)

        # 清晰度列表
        qualities = []
        if url_list:
            for i, src_url in enumerate(url_list):
                clean_url = src_url.replace("playwm", "play")
                final_url = await _get_video_redirect_url(clean_url)
                quality_label = "1080P" if i == 0 else ("720P" if i == 1 else f"{i * 360}P")
                qualities.append({
                    "quality": quality_label,
                    "url": final_url,
                    "resolution": "",
                    "filesize": "未知",
                })

        logger.info(f"[douyin] 解析成功 | title={desc[:30]} | video_url={bool(video_url)}")

        return {
            "video_url": video_url,
            "cover_url": cover_url,
            "title": desc,
            "author_name": nickname,
            "author_uid": str(author.get("uid", "")) if isinstance(author, dict) else "",
            "author_avatar": _get_avatar_url(author),
            "duration": duration,
            "platform": "douyin",
            "like_count": like_count,
            "comment_count": comment_count,
            "share_count": share_count,
            "play_count": play_count,
            "content_type": "video",
            "images": [],
            "qualities": qualities,
            "parse_method": "iesdouyin",
            "raw": video_data,
        }

    except asyncio.TimeoutError:
        logger.warning("[douyin] 请求超时")
        return {}
    except Exception as e:
        logger.warning(f"[douyin] 解析异常: {e}\n{_tb.format_exc()}")
        return {}
