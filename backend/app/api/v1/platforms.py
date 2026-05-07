"""
YLCraft — 平台连接器 API

GET    /api/v1/platforms              — 列出所有平台连接
GET    /api/v1/platforms/supported    — 获取支持的平台列表
GET    /api/v1/platforms/{id}         — 获取单个连接详情
POST   /api/v1/platforms              — 创建新连接
PUT    /api/v1/platforms/{id}         — 更新连接
DELETE /api/v1/platforms/{id}         — 删除连接
POST   /api/v1/platforms/{id}/test     — 测试连接有效性
POST   /api/v1/platforms/{id}/use      — 标记为已使用
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session

from app.db.database import get_session
from app.db.models.platform_connection import (
    PlatformConnectionCreate,
    PlatformConnectionUpdate,
    PlatformConnectionResponse,
    PlatformType,
    AuthType,
    ConnectionStatus,
)
from app.services.platform_connection.service import PlatformConnectionService

logger = logging.getLogger("ylcraft.api.platforms")

router = APIRouter(prefix="", tags=["Platform Connections"])

# =============================================================================
# 支持的平台列表
# =============================================================================

SUPPORTED_PLATFORMS = [
    {"value": "xhs",        "label": "小红书",   "icon": "book",        "color": "#fe2c55"},
    {"value": "douyin",    "label": "抖音",     "icon": "video",       "color": "#000000"},
    {"value": "kuaishou",  "label": "快手",     "icon": "play-circle", "color": "#ff5000"},
    {"value": "bilibili",  "label": "B站",      "icon": "tv",          "color": "#00aeec"},
    {"value": "weibo",     "label": "微博",     "icon": "message",     "color": "#ff8200"},
    {"value": "zhihu",     "label": "知乎",     "icon": "question",    "color": "#0066ff"},
    {"value": "youtube",   "label": "YouTube",   "icon": "youtube",     "color": "#ff0000"},
    {"value": "tiktok",    "label": "TikTok",    "icon": "tiktok",      "color": "#000000"},
    {"value": "openai",    "label": "OpenAI",    "icon": "api",         "color": "#10a37f"},
    {"value": "anthropic","label": "Anthropic", "icon": "api",         "color": "#d4a0e7"},
    {"value": "minimax",   "label": "MiniMax",   "icon": "api",         "color": "#00d4ff"},
]

AUTH_TYPES = [
    {"value": "cookie",   "label": "Cookie 认证"},
    {"value": "api_key",  "label": "API Key"},
    {"value": "oauth2",   "label": "OAuth2.0"},
    {"value": "password", "label": "账号密码"},
    {"value": "none",     "label": "无需认证"},
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
    """返回所有支持的平台和认证类型"""
    return {
        "platforms": SUPPORTED_PLATFORMS,
        "auth_types": AUTH_TYPES,
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
        "status": conn.status,
    }
