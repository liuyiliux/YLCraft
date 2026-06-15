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


def placeholder_image_response(label: str = "YLCraft") -> Response:
    safe_label = (label or "YLCraft")[:18]
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <rect width="320" height="180" rx="12" fill="#141820"/>
  <rect x="18" y="18" width="284" height="144" rx="10" fill="#1f2937"/>
  <text x="160" y="94" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" fill="#9ca3af">{safe_label}</text>
</svg>"""
    return Response(
        content=svg.encode("utf-8"),
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def fetch_remote_image_response(url: str, fallback_label: str | None = None) -> Response:
    if not url or not url.startswith(("http://", "https://")):
        if fallback_label is not None:
            return placeholder_image_response(fallback_label)
        raise HTTPException(status_code=400, detail="无效的图片 URL")

    referer = _guess_referer(url)
    headers = {
        "Referer": referer,
        "User-Agent": _BROWSER_UA,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
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
        if fallback_label is not None:
            return placeholder_image_response(fallback_label)
        raise HTTPException(status_code=e.response.status_code, detail=f"图片请求失败: {e}")
    except Exception as e:
        logger.error(f"[proxy/image] 错误: {type(e).__name__}: {e}")
        if fallback_label is not None:
            return placeholder_image_response(fallback_label)
        raise HTTPException(status_code=502, detail=f"图片代理失败: {type(e).__name__}")


@router.get("/image", summary="通用图片代理（解决各平台 CDN 防盗链）")
async def proxy_image(
    url: str = Query(..., description="图片 URL，需要 URL编码"),
):
    """
    通用图片代理，解决各平台 CDN 防盗链 403 问题。
    后端携带正确 Referer 请求，将图片流式返回给前端。
    支持缓存（Cache-Control: public, max-age=86400）。
    """
    return await fetch_remote_image_response(url)


# =============================================================================
# 代理抓包 API
# =============================================================================

from pydantic import BaseModel, Field
from typing import Optional as Opt
from app.services.proxy.sniffer import ProxySniffer

_sniffer: Opt[ProxySniffer] = None


def _get_sniffer() -> ProxySniffer:
    global _sniffer
    if _sniffer is None:
        _sniffer = ProxySniffer()
    return _sniffer


class SnifferStartRequest(BaseModel):
    port: int = Field(8080, description="监听端口")
    filter_domains: list[str] = Field(default_factory=list, description="过滤域名列表")
    duration: int = Field(60, description="监听时长（秒），0=手动停止")


class SnifferStatusResponse(BaseModel):
    session_id: str = ""
    running: bool = False
    port: int = 0
    started_at: str = ""
    elapsed_seconds: int = 0
    total_captured: int = 0
    filter_domains: list[str] = []
    captured_requests: list[dict] = []


@router.post("/sniffer/start", summary="启动抓包代理")
async def start_sniffer(req: SnifferStartRequest):
    """启动本地 HTTP 代理抓包"""
    sniffer = _get_sniffer()
    result = sniffer.start(port=req.port, filter_domains=req.filter_domains)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/sniffer/status/{session_id}", summary="查询抓包状态")
async def get_sniffer_status(session_id: str):
    """查询抓包代理状态 + 已捕获请求"""
    sniffer = _get_sniffer()
    status = sniffer.get_status()
    return SnifferStatusResponse(**status)


@router.post("/sniffer/stop/{session_id}", summary="停止抓包")
async def stop_sniffer(session_id: str):
    """手动停止抓包代理"""
    sniffer = _get_sniffer()
    result = sniffer.stop()
    return result


@router.get("/sniffer/health", summary="检查代理状态")
async def sniffer_health():
    """检查代理抓包运行状态"""
    sniffer = _get_sniffer()
    return {
        "running": sniffer.is_running,
        "captured_count": sniffer.captured_count,
    }


@router.get("/sniffer/cert", summary="下载 CA 证书")
async def download_ca_cert():
    """下载代理 CA 证书（用于 HTTPS 抓包）"""
    from app.services.proxy.cert import CertManager
    cert_path = CertManager.get_ca_cert_path()
    if not CertManager.ca_cert_exists():
        CertManager.generate_ca_cert()
    if not CertManager.ca_cert_exists():
        raise HTTPException(status_code=404, detail="CA 证书不可用")

    import os
    return Response(
        content=open(cert_path, "rb").read(),
        media_type="application/x-pem-file",
        headers={
            "Content-Disposition": "attachment; filename=ylcraft-ca.pem",
        },
    )
