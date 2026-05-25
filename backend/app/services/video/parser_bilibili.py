"""
B站官方 API 解析器（无需 Cookie，完全免登录）

参考 yby6-video-parser skill 的 bilibili.py 实现。
官方 API 比 yt-dlp 更稳定，且无需任何 Cookie。

API 端点：
1. /x/web-interface/view          — 获取视频元信息（标题、封面、作者、时长）
2. /x/player/playurl               — 获取播放直链（需要先拿到 cid）

文档：https://github.com/SocialSisterYi/bilibili-API-collect
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

import httpx
import logging

from app.services.platforms.bilibili.utils import (
    _quality_to_resolution,
    _get_filesize_for_qn,
)

logger = logging.getLogger("ylcraft.parser.bilibili")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_HEADERS = {"User-Agent": _USER_AGENT, "Referer": "https://www.bilibili.com/"}


def _extract_bvid(url: str) -> Optional[str]:
    """从 URL 提取 BVID，支持短链接 b23.tv"""
    patterns = [
        r"/video/(BV[\w]{10})",
        r"/video/(bv[\w]{10})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)  # 不做 .upper()，BVID 大小写敏感
    return None


async def _resolve_short_url(url: str) -> str:
    """解析 b23.tv 短链接，返回真实 URL"""
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=15.0) as client:
            resp = await client.get(url, headers=_HEADERS)
            location = resp.headers.get("location")
            if location:
                return location
    except Exception as e:
        logger.warning(f"[bilibili] b23.tv 短链接解析失败: {e}")
    return url


async def _get_bvid_from_url(url: str) -> Optional[str]:
    """从 URL 提取 BV id，处理短链接"""
    if "b23.tv" in url:
        real_url = await _resolve_short_url(url)
        return _extract_bvid(real_url)
    return _extract_bvid(url)


async def _call_api(url: str) -> dict:
    """发送 B站 API 请求，返回解析后的 JSON"""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=_HEADERS)
        if resp.status_code != 200:
            raise Exception(f"B站 API 返回 {resp.status_code}")
        return resp.json()


async def parse_bilibili(url: str) -> dict:
    """
    用 B站官方 API 解析视频（无需 Cookie）。

    返回 dict：
    {
        "video_url": "...", "cover_url": "...", "title": "...",
        "author_name": "...", "author_uid": "...", "author_avatar": "...",
        "duration": 0, "platform": "bilibili",
        "like_count": 0, "comment_count": 0, "share_count": 0, "play_count": 0,
        "content_type": "video", "images": [], "qualities": [...],
        "parse_method": "bilibili_api", "raw": {...}
    }

    解析失败返回空 dict，外层会 fallback 到 yt-dlp。
    """
    import traceback as _tb

    try:
        # 1. 提取 BV id
        bvid = await _get_bvid_from_url(url)
        if not bvid:
            logger.warning(f"[bilibili] 无法从 URL 提取 BVID: {url}")
            return {}

        logger.info(f"[bilibili] BVID: {bvid}")

        # 2. 获取视频元信息（cid 是获取播放链接的前置条件）
        view_api = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        view_resp = await _call_api(view_api)
        view_data = view_resp.get("data")

        if not isinstance(view_data, dict) or view_data.get("code") != 0:
            msg = view_data.get("message", "未知错误") if isinstance(view_data, dict) else "无数据"
            logger.warning(f"[bilibili] view API 错误: {msg}")
            return {}

        title = view_data.get("title", "") or ""
        cover_url = view_data.get("pic", "") or ""
        desc = view_data.get("desc", "") or ""

        # 第一分 P 的 cid（用于获取播放链接）
        pages = view_data.get("pages") or []
        first_cid = pages[0]["cid"] if pages else view_data.get("cid")
        if not first_cid:
            logger.warning("[bilibili] 无法获取视频 cid")
            return {}

        owner = view_data.get("owner") or {}
        owner = owner if isinstance(owner, dict) else {}
        author_name = owner.get("name", "") or ""
        author_uid = str(owner.get("mid", "")) or ""
        author_avatar = owner.get("face", "") or ""

        duration = int(view_data.get("duration", 0) or 0)

        stat = view_data.get("stat") or {}
        stat = stat if isinstance(stat, dict) else {}
        play_count = int(stat.get("view", 0) or 0)
        like_count = int(stat.get("like", 0) or 0)
        comment_count = int(stat.get("reply", 0) or 0)
        share_count = int(stat.get("share", 0) or 0)

        # 3. 获取播放链接（多清晰度）
        play_api = (
            f"https://api.bilibili.com/x/player/playurl?"
            f"otype=json&fnver=0&fnval=0&qn=80&bvid={bvid}"
            f"&cid={first_cid}&platform=html5"
        )
        play_resp = await _call_api(play_api)
        play_data = play_resp.get("data")

        if not isinstance(play_data, dict) or play_data.get("code") != 0:
            logger.warning("[bilibili] playurl API 错误")
            return {}

        qualities = []
        video_url = ""
        width = 0
        height = 0

        durl_list = play_data.get("durl") or []
        if isinstance(durl_list, list) and durl_list:
            best = durl_list[0]
            video_url = best.get("url", "") or ""

            # 尝试从 view_data 获取 width/height
            if isinstance(view_data, dict):
                pages = view_data.get("pages", [])
                if pages and len(pages) > 0:
                    first_page = pages[0] if isinstance(pages[0], dict) else {}
                    width = int(first_page.get("dimension", {}).get("width")
                                or first_page.get("width") or 0)
                    height = int(first_page.get("dimension", {}).get("height")
                                 or first_page.get("height") or 0)
                if not width or not height:
                    width = int(view_data.get("width") or 0)
                    height = int(view_data.get("height") or 0)

            # 从 play_data 获取可用清晰度列表
            accept_quality = play_data.get("accept_quality", [])
            accept_description = play_data.get("accept_description", [])
            current_qn = play_data.get("quality", 80)

            if accept_quality and accept_description and len(accept_quality) == len(accept_description):
                # 有完整的清晰度列表：为每个清晰度构建条目
                # 每个 qn 用自己的分辨率：优先从映射表读取
                current_size = durl_list[0].get("size", 0) if durl_list else 0
                for qn, desc in zip(accept_quality, accept_description):
                    q_res = _quality_to_resolution(qn, height)
                    # 当前 qn 已有 URL，其他 qn 暂用当前 URL
                    q_url = video_url if qn == current_qn else ""
                    q_size = current_size if qn == current_qn else 0
                    qualities.append({
                        "quality": desc,
                        "url": q_url,
                        "resolution": q_res,
                        "filesize": _get_filesize_for_qn(qn, q_size, duration),
                    })
            elif len(durl_list) > 1:
                # 分段视频
                for i, d in enumerate(durl_list):
                    segment_url = d.get("url", "") if isinstance(d, dict) else ""
                    if segment_url:
                        res = _quality_to_resolution(current_qn, height)
                        sz = d.get("size", 0) if isinstance(d, dict) else 0
                        qualities.append({
                            "quality": f"分段{i+1}",
                            "url": segment_url,
                            "resolution": res or "",
                            "filesize": _get_filesize_for_qn(current_qn, sz, duration),
                        })
            else:
                # 无 accept_quality，仅一个清晰度
                label = "1080P"  # qn=80
                res = _quality_to_resolution(current_qn, height)
                sz = durl_list[0].get("size", 0) if durl_list else 0
                qualities.append({
                    "quality": label,
                    "url": video_url,
                    "resolution": res or "",
                    "filesize": _get_filesize_for_qn(current_qn, sz, duration),
                })

        if not video_url:
            logger.warning("[bilibili] 无法获取视频直链")
            return {}

        logger.info(f"[bilibili] 解析成功 | title={title[:30]} | video_url={bool(video_url)}")

        return {
            "video_url": video_url,
            "cover_url": cover_url,
            "title": title,
            "desc": desc,
            "author_name": author_name,
            "author_uid": author_uid,
            "author_avatar": author_avatar,
            "duration": duration,
            "width": width,
            "height": height,
            "platform": "bilibili",
            "like_count": like_count,
            "comment_count": comment_count,
            "share_count": share_count,
            "play_count": play_count,
            "content_type": "video",
            "images": [],
            "qualities": qualities,
            "parse_method": "bilibili_api",
            "raw": view_data,
        }

    except asyncio.TimeoutError:
        logger.warning("[bilibili] 请求超时")
        return {}
    except Exception as e:
        logger.warning(f"[bilibili] 解析异常: {e}\n{_tb.format_exc()}")
        return {}
