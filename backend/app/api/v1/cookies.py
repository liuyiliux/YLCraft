"""
YLCraft — 平台 Cookie 管理 API

GET    /api/v1/cookies              — 列出所有已配置的 Cookie 平台
GET    /api/v1/cookies/{platform}   — 查看指定平台 Cookie 状态（不含内容）
POST   /api/v1/cookies/{platform}   — 上传/保存 Cookie
DELETE /api/v1/cookies/{platform}   — 删除 Cookie
POST   /api/v1/cookies/{platform}/test — 测试 Cookie 是否有效
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.video.parser import get_cookie_manager

logger = logging.getLogger("ylcraft.cookies")

router = APIRouter(prefix="", tags=["Cookies"])


class CookieStatus(BaseModel):
    platform: str
    configured: bool
    path: str | None = None
    size: int | None = None
    modified: float | None = None
    platforms_supported: list[str] = [
        "douyin", "tiktok", "kuaishou", "bilibili",
        "xiaohongshu", "weibo", "youtube",
    ]


class CookieListResponse(BaseModel):
    success: bool = True
    cookies: dict[str, CookieStatus]


class CookieSaveRequest(BaseModel):
    content: str


class CookieSaveResponse(BaseModel):
    success: bool = True
    platform: str
    path: str
    message: str


class CookieDeleteResponse(BaseModel):
    success: bool = True
    platform: str
    message: str


class CookieTestResponse(BaseModel):
    success: bool
    platform: str
    message: str
    parse_method: str = ""


@router.get("", response_model=CookieListResponse, summary="列出所有 Cookie 状态")
async def list_cookies():
    mgr = get_cookie_manager()
    all_platforms = [
        "douyin", "tiktok", "kuaishou", "bilibili",
        "xiaohongshu", "weibo", "youtube",
    ]
    existing = mgr.list_cookies()
    result = {}
    for platform in all_platforms:
        info = existing.get(platform)
        result[platform] = CookieStatus(
            platform=platform,
            configured=platform in existing,
            path=info["path"] if info else None,
            size=info["size"] if info else None,
            modified=info["modified"] if info else None,
        )
    return CookieListResponse(success=True, cookies=result)


@router.get("/{platform}", response_model=CookieStatus, summary="查看单个平台 Cookie 状态")
async def get_cookie_status(platform: str):
    platforms = ["douyin", "tiktok", "kuaishou", "bilibili", "xiaohongshu", "weibo", "youtube"]
    if platform not in platforms:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {platform}")

    mgr = get_cookie_manager()
    existing = mgr.list_cookies()
    info = existing.get(platform)
    return CookieStatus(
        platform=platform,
        configured=platform in existing,
        path=info["path"] if info else None,
        size=info["size"] if info else None,
        modified=info["modified"] if info else None,
    )


@router.post("/{platform}", response_model=CookieSaveResponse, summary="保存平台 Cookie")
async def save_cookie(platform: str, req: CookieSaveRequest):
    platforms = ["douyin", "tiktok", "kuaishou", "bilibili", "xiaohongshu", "weibo", "youtube"]
    if platform not in platforms:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {platform}")

    if not req.content or len(req.content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Cookie 内容太短，请检查是否正确")

    try:
        path = get_cookie_manager().save_cookie(platform, req.content)
        return CookieSaveResponse(
            success=True,
            platform=platform,
            path=str(path),
            message=f"Cookie 已保存。下次解析 {platform} 时自动注入。",
        )
    except Exception as e:
        logger.error(f"[CookieAPI] 保存 {platform} Cookie 失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


@router.delete("/{platform}", response_model=CookieDeleteResponse, summary="删除平台 Cookie")
async def delete_cookie(platform: str):
    platforms = ["douyin", "tiktok", "kuaishou", "bilibili", "xiaohongshu", "weibo", "youtube"]
    if platform not in platforms:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {platform}")

    deleted = get_cookie_manager().delete_cookie(platform)
    if deleted:
        return CookieDeleteResponse(success=True, platform=platform, message="Cookie 已删除")
    else:
        return CookieDeleteResponse(success=True, platform=platform, message="Cookie 文件不存在，无需删除")


@router.post("/{platform}/test", response_model=CookieTestResponse, summary="测试 Cookie 是否有效")
async def test_cookie(platform: str):
    import asyncio
    from app.services.video.parser import parse

    platforms = ["douyin", "tiktok", "kuaishou", "bilibili", "xiaohongshu", "weibo", "youtube"]
    if platform not in platforms:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {platform}")

    test_urls = {
        "douyin": "https://www.douyin.com/video/7322548203919920387",
        "tiktok": "https://www.tiktok.com/@tiktok/video/7043492019477857454",
        "kuaishou": "https://www.kuaishou.com/short-video/3xpdvbqr5y5g",
        "bilibili": "https://www.bilibili.com/video/BV1xx411c7XD",
        "xiaohongshu": "https://www.xiaohongshu.com/explore/6543a0cb000000003d0170f6",
        "weibo": "https://weibo.com/7741392674/status/5028368969279244",
        "youtube": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }

    url = test_urls.get(platform)
    if not url:
        raise HTTPException(status_code=400, detail="该平台暂无测试链接")

    try:
        info = await asyncio.wait_for(parse(url), timeout=60.0)
        if info.is_valid():
            return CookieTestResponse(
                success=True,
                platform=platform,
                message=f"解析成功！标题: {info.title[:50] if info.title else '(无)'}",
                parse_method=info.parse_method,
            )
        else:
            return CookieTestResponse(
                success=False,
                platform=platform,
                message=f"解析失败，parse_method: {info.parse_method}。Cookie 可能已失效。",
                parse_method=info.parse_method,
            )
    except asyncio.TimeoutError:
        return CookieTestResponse(
            success=False,
            platform=platform,
            message="解析超时，Cookie 可能无效或网络问题。",
        )
    except Exception as e:
        return CookieTestResponse(
            success=False,
            platform=platform,
            message=f"测试异常: {str(e)}",
        )
