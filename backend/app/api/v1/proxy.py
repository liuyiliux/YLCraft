"""
YLCraft — 通用图片代理 API

GET /api/v1/proxy/image?url=...  — 通用图片代理，解决各平台 CDN 防盗链问题
"""

from __future__ import annotations

import logging
import mimetypes
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from starlette.responses import Response

router = APIRouter()
logger = logging.getLogger("ylcraft.proxy")

# 域名 → Referer 映射
_REFERER_MAP = {
    "bilibili.com": "https://www.bilibili.com",
    "hdslb.com": "https://www.bilibili.com",
    "xiaohongshu.com": "https://www.xiaohongshu.com",
    "xhscdn.com": "https://www.xiaohongshu.com",
    "douyin.com": "https://www.douyin.com",
    "douyincdn.com": "https://www.douyin.com",
    "douyinpic.com": "https://www.douyin.com",
    "kuaishou.com": "https://www.kuaishou.com",
    "kwai.com": "https://www.kuaishou.com",
    "weibo.com": "https://weibo.com",
    "sinaimg.cn": "https://weibo.com",
    "twitter.com": "https://twitter.com",
    "x.com": "https://x.com",
    "twimg.com": "https://twitter.com",
    "youtube.com": "https://www.youtube.com",
    "ytimg.com": "https://www.youtube.com",
}

# 通用浏览器 UA
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def _guess_referer(url: str) -> str:
    """根据 URL 域名猜 Referer"""
    hostname = urlparse(url).hostname or ""
    for domain, referer in _REFERER_MAP.items():
        if domain in hostname:
            return referer
    # 默认返回源站首页
    scheme = urlparse(url).scheme
    return f"{scheme}://{hostname}" if hostname else "https://www.google.com"


@router.get("/image", summary="通用图片代理（解决各平台 CDN 防盗链）")
async def proxy_image(
    url: str = Query(..., description="图片 URL，需要 URL编码"),
):
    """
    通用图片代理，解决各平台 CDN 防盗链 403 问题。
    后端携带正确 Referer 请求，将图片流式返回给前端。
    支持缓存（Cache-Control: public, max-age=86400）。
    """
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="无效的图片 URL")

    referer = _guess_referer(url)
    headers = {
        "Referer": referer,
        "User-Agent": _BROWSER_UA,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            content = resp.content

        mime = mimetypes.guess_type(url)[0] or resp.headers.get("content-type", "image/jpeg")
        return Response(
            content=content,
            media_type=mime,
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except httpx.HTTPStatusError as e:
        logger.warning(f"[proxy/image] HTTP {e.response.status_code} for {url[:80]}")
        raise HTTPException(status_code=e.response.status_code, detail=f"图片请求失败: {e}")
    except Exception as e:
        logger.error(f"[proxy/image] 错误: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail=f"图片代理失败: {type(e).__name__}")
