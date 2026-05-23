"""
YLCraft — 平台连接器 API（统一凭证架构）

GET    /api/v1/platforms                           — 列出所有平台连接
GET    /api/v1/platforms/supported                  — 获取支持的平台列表
GET    /api/v1/platforms/{id}                       — 获取单个连接详情
POST   /api/v1/platforms                           — 创建新连接
PUT    /api/v1/platforms/{id}                       — 更新连接
DELETE /api/v1/platforms/{id}                      — 删除连接
POST   /api/v1/platforms/{id}/test                 — 测试连接有效性
POST   /api/v1/platforms/{id}/use                  — 标记为已使用
GET    /api/v1/platforms/{id}/cookie-content       — 获取 Netscape 格式 Cookie
POST   /api/v1/platforms/{id}/cookie-content       — 保存 Netscape 格式 Cookie
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db.database import get_session
from app.db.models.platform_connection import (
    PlatformConnectionCreate,
    PlatformConnectionUpdate,
    PlatformConnectionResponse,
    PlatformType,
    AuthType,
    ConnectionStatus,
    AcquisitionMethod,
)
from app.services.platform_connection.service import PlatformConnectionService

logger = logging.getLogger("ylcraft.api.platforms")

router = APIRouter(prefix="", tags=["Platform Connections"])

# =============================================================================
# 支持的平台列表
# =============================================================================

SUPPORTED_PLATFORMS = [
    {"value": "xhs",        "label": "小红书",   "icon": "book",        "color": "#fe2c55",  "auth_types": ["cookie"]},
    {"value": "douyin",     "label": "抖音",     "icon": "video",       "color": "#000000",  "auth_types": ["cookie"]},
    {"value": "kuaishou",   "label": "快手",     "icon": "play-circle", "color": "#ff5000",  "auth_types": ["cookie"]},
    {"value": "bilibili",   "label": "B站",      "icon": "tv",          "color": "#00aeec",  "auth_types": ["cookie"]},
    {"value": "weibo",      "label": "微博",     "icon": "message",     "color": "#ff8200",  "auth_types": ["cookie"]},
    {"value": "zhihu",      "label": "知乎",     "icon": "question",    "color": "#0066ff",  "auth_types": ["cookie"]},
    {"value": "youtube",    "label": "YouTube",   "icon": "youtube",     "color": "#ff0000",  "auth_types": ["cookie"]},
    {"value": "tiktok",     "label": "TikTok",    "icon": "tiktok",      "color": "#000000",  "auth_types": ["cookie"]},
    {"value": "twitter",    "label": "Twitter/X", "icon": "twitter",    "color": "#1da1f2",  "auth_types": ["cookie"]},
    {"value": "telegram",   "label": "Telegram",  "icon": "send",        "color": "#0088cc",  "auth_types": ["cookie"]},
    {"value": "openai",     "label": "OpenAI",    "icon": "api",         "color": "#10a37f",  "auth_types": ["api_key"]},
    {"value": "anthropic",  "label": "Anthropic", "icon": "api",         "color": "#d4a0e7",  "auth_types": ["api_key"]},
    {"value": "minimax",    "label": "MiniMax",   "icon": "api",         "color": "#00d4ff",  "auth_types": ["api_key"]},
]

AUTH_TYPES = [
    {"value": "cookie",   "label": "Cookie 认证"},
    {"value": "api_key",  "label": "API Key"},
    {"value": "oauth2",   "label": "OAuth2.0"},
    {"value": "password", "label": "账号密码"},
    {"value": "none",     "label": "无需认证"},
]

ACQUISITION_METHODS = [
    {"value": "manual",     "label": "手动粘贴"},
    {"value": "playwright", "label": "浏览器自动化"},
    {"value": "qrcode",    "label": "扫码登录"},
]


# =============================================================================
# 依赖注入
# =============================================================================

def get_platform_service(session: Session = Depends(get_session)) -> PlatformConnectionService:
    return PlatformConnectionService(session)


# =============================================================================
# API 端点
# =============================================================================

@router.get("/supported", summary="获取支持的平台列表")
async def get_supported_platforms():
    """返回所有支持的平台、认证类型、获取方式"""
    # 检查 Playwright 是否可用
    playwright_available = False
    try:
        from app.services.cookies.patchright_manager import get_patchright_manager
        playwright_available = get_patchright_manager().is_available()
    except Exception:
        pass

    return {
        "platforms": SUPPORTED_PLATFORMS,
        "auth_types": AUTH_TYPES,
        "acquisition_methods": ACQUISITION_METHODS,
        "playwright_available": playwright_available,
        "statuses": [
            {"value": "active",  "label": "有效"},
            {"value": "expired", "label": "已过期"},
            {"value": "failed",  "label": "连接失败"},
            {"value": "unknown", "label": "未测试"},
        ],
    }


@router.get("", summary="列出所有平台连接")
async def list_connections(
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """列出所有平台连接（不返回凭证内容）"""
    conns = service.list_all()
    return {
        "success": True,
        "connections": [PlatformConnectionResponse.from_db(c) for c in conns],
        "total": len(conns),
    }


@router.get("/{conn_id}", summary="获取连接详情")
async def get_connection(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """获取单个连接详情（不返回凭证内容）"""
    conn = service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connection": PlatformConnectionResponse.from_db(conn),
    }


@router.post("", summary="创建平台连接")
async def create_connection(
    data: PlatformConnectionCreate,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """创建新的平台连接"""
    try:
        conn = service.create(data)
        return {
            "success": True,
            "connection": PlatformConnectionResponse.from_db(conn),
            "message": f"平台连接 {conn.name} 创建成功",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/{conn_id}", summary="更新平台连接")
async def update_connection(
    conn_id: str,
    data: PlatformConnectionUpdate,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """更新平台连接"""
    conn = service.update(conn_id, data)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connection": PlatformConnectionResponse.from_db(conn),
        "message": "更新成功",
    }


@router.delete("/{conn_id}", summary="删除平台连接")
async def delete_connection(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """删除平台连接"""
    ok = service.delete(conn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "message": "删除成功",
    }


@router.post("/{conn_id}/test", summary="测试连接有效性")
async def test_connection(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """测试连接是否有效"""
    result = service.test_connection(conn_id)
    return {
        "success": result["success"],
        "message": result["message"],
        "connection_id": conn_id,
    }


@router.post("/{conn_id}/use", summary="标记为已使用")
async def mark_used(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """标记连接已使用（更新 last_used）"""
    service.mark_used(conn_id)
    return {
        "success": True,
        "message": "已更新使用时间",
    }


# =============================================================================
# Cookie Content 端点
# =============================================================================

class CookieContentResponse(BaseModel):
    """Cookie 内容响应"""
    connection_id: str
    platform: str
    content: str = ""
    configured: bool = False
    size: int = 0


class CookieContentSaveRequest(BaseModel):
    """Cookie 内容保存请求"""
    content: str


@router.get("/{conn_id}/cookie-content", summary="获取 Netscape 格式 Cookie")
async def get_cookie_content(
    conn_id: str,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """获取连接的 Netscape 格式 Cookie 内容（视频解析用）"""
    conn = service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    cookie_content = service.get_cookie_content(conn_id)
    if cookie_content:
        return CookieContentResponse(
            connection_id=conn_id,
            platform=conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform),
            content=cookie_content,
            configured=True,
            size=len(cookie_content),
        )
    return CookieContentResponse(
        connection_id=conn_id,
        platform=conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform),
        configured=False,
    )


@router.post("/{conn_id}/cookie-content", summary="保存 Netscape 格式 Cookie")
async def save_cookie_content(
    conn_id: str,
    req: CookieContentSaveRequest,
    service: PlatformConnectionService = Depends(get_platform_service),
):
    """保存 Netscape 格式 Cookie 到连接（替代原 /cookies/{platform}）"""
    if not req.content or len(req.content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Cookie 内容太短，请检查是否正确")

    # 使用 CookieManager 的公共方法进行格式转换
    try:
        from app.services.video.parser import get_cookie_manager
        mgr = get_cookie_manager()
        conn = service.get(conn_id)
        if not conn:
            raise HTTPException(status_code=404, detail="连接不存在")

        platform = conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform)
        # 使用公共方法 normalize_cookie 转换为 Netscape 格式
        netscape_content = mgr.normalize_cookie(platform, req.content)
        
        ok = service.save_cookie_content(conn_id, netscape_content)
        if ok:
            return {
                "success": True,
                "message": "Cookie 已保存",
                "connection_id": conn_id,
            }
        raise HTTPException(status_code=500, detail="保存失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PlatformsAPI] save_cookie_content failed: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


# =============================================================================
# 辅助函数（供其他模块调用）
# =============================================================================

def get_active_connection(session: Session, platform: str) -> Optional[dict]:
    """
    获取指定平台的活跃连接凭证
    供搜索/下载/发布等功能调用
    """
    service = PlatformConnectionService(session)
    conn = service.get_active(platform)
    if not conn:
        return None
    return {
        "id": conn.id,
        "platform": conn.platform,
        "name": conn.name,
        "auth_type": conn.auth_type,
        "credentials": conn.get_credentials(),
        "cookie_content": conn.cookie_content,
        "status": conn.status,
    }
