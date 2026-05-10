"""
YLCraft — 平台 Cookie 管理 API

GET    /api/v1/cookies              — 列出所有已配置的平台
POST   /api/v1/cookies/platform     — 新增/更新平台配置
GET    /api/v1/cookies/{platform}   — 查看指定平台 Cookie 状态
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
    name: str = ""
    configured: bool
    size: int | None = None
    modified: float | None = None
    domains: str | None = None
    test_url: str | None = None
    description: str = ""


class CookieListResponse(BaseModel):
    success: bool = True
    cookies: dict[str, CookieStatus]


class CookieSaveRequest(BaseModel):
    content: str


class CookieSaveResponse(BaseModel):
    success: bool = True
    platform: str
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


class PlatformSaveRequest(BaseModel):
    display_name: str
    domain: str = ""
    test_url: str = ""
    description: str = ""


class PlatformSaveResponse(BaseModel):
    success: bool = True
    platform: str
    message: str


@router.get("", response_model=CookieListResponse, summary="列出所有平台状态")
async def list_cookies():
    mgr = get_cookie_manager()
    platforms = mgr.list_cookies()
    
    result = {}
    for platform, info in platforms.items():
        result[platform] = CookieStatus(
            platform=platform,
            name=info.get("display_name", platform),
            configured=info.get("has_cookie", False),
            size=info.get("size"),
            modified=info.get("modified"),
            domains=info.get("domains", ""),
            test_url=info.get("test_url"),
            description=info.get("description", ""),
        )
    return CookieListResponse(success=True, cookies=result)


@router.post("/platform", response_model=PlatformSaveResponse, summary="新增/更新平台配置")
async def save_platform(platform_id: str, req: PlatformSaveRequest):
    mgr = get_cookie_manager()
    if not platform_id or len(platform_id.strip()) < 2:
        raise HTTPException(status_code=400, detail="平台标识太短")
    
    success = mgr.save_platform(
        platform_id=platform_id.strip().lower(),
        display_name=req.display_name,
        domains=getattr(req, 'domains', req.domain or ""),  # 向后兼容
        test_url=req.test_url,
        description=req.description,
    )
    if success:
        return PlatformSaveResponse(
            success=True,
            platform=platform_id,
            message=f"平台 {req.display_name} 配置已保存，关联域名生效",
        )
    raise HTTPException(status_code=500, detail="保存失败")


@router.get("/{platform}", response_model=CookieStatus, summary="查看单个平台 Cookie 状态")
async def get_cookie_status(platform: str):
    mgr = get_cookie_manager()
    info = mgr.get_platform_info(platform)
    if not info:
        raise HTTPException(status_code=404, detail=f"平台 {platform} 不存在")
    
    return CookieStatus(
        platform=info["id"],
        name=info["display_name"],
        configured=info["has_cookie"],
        domains=info.get("domains", ""),
        test_url=info["test_url"],
        description=info["description"],
    )


class CookieContentResponse(BaseModel):
    platform: str
    content: str = ""
    configured: bool = False
    size: int = 0


@router.get("/{platform}/content", response_model=CookieContentResponse, summary="获取平台 Cookie 原始内容")
async def get_cookie_content(platform: str):
    """返回指定平台保存的 Cookie 原始内容（用于前端展示已配置的值）"""
    from app.db.database import SessionLocal
    from app.db.models import PlatformCookie
    
    session = SessionLocal()
    try:
        plat = session.get(PlatformCookie, platform)
        if plat and plat.cookie_content:
            return CookieContentResponse(
                platform=platform,
                content=plat.cookie_content,
                configured=True,
                size=len(plat.cookie_content),
            )
        return CookieContentResponse(
            platform=platform,
            configured=False,
        )
    finally:
        session.close()


@router.post("/{platform}", response_model=CookieSaveResponse, summary="保存平台 Cookie")
async def save_cookie(platform: str, req: CookieSaveRequest):
    if not platform or len(platform.strip()) < 2:
        raise HTTPException(status_code=400, detail="平台名太短")

    if not req.content or len(req.content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Cookie 内容太短，请检查是否正确")

    try:
        success = get_cookie_manager().save_cookie(platform, req.content)
        return CookieSaveResponse(
            success=True,
            platform=platform,
            message=f"Cookie 已保存到数据库。完全内存模式，无需临时文件。",
        )
    except Exception as e:
        logger.error(f"[CookieAPI] 保存 {platform} Cookie 失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


@router.delete("/{platform}", response_model=CookieDeleteResponse, summary="删除平台 Cookie")
async def delete_cookie(platform: str):
    deleted = get_cookie_manager().delete_cookie(platform)
    if deleted:
        return CookieDeleteResponse(success=True, platform=platform, message="Cookie 已删除")
    else:
        return CookieDeleteResponse(success=True, platform=platform, message="Cookie 文件不存在，无需删除")


@router.post("/{platform}/test", response_model=CookieTestResponse, summary="测试 Cookie 是否有效")
async def test_cookie(platform: str):
    import asyncio
    from app.services.video.parser import parse

    mgr = get_cookie_manager()
    info = mgr.get_platform_info(platform)
    test_url = info.get("test_url") if info else None
    
    if not test_url:
        return CookieTestResponse(
            success=False,
            platform=platform,
            message=f"平台 {platform} 没有配置测试链接，请直接使用真实链接测试"
        )

    try:
        info = await asyncio.wait_for(parse(test_url), timeout=60.0)
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
