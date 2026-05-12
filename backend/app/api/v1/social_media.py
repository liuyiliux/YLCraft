"""
YLCraft — 社交媒体连接器 API

GET    /api/v1/social/connectors              — 列出所有社交媒体连接
GET    /api/v1/social/connectors/supported    — 获取支持的平台列表
GET    /api/v1/social/connectors/{id}          — 获取连接详情
POST   /api/v1/social/connectors              — 创建新连接
PUT    /api/v1/social/connectors/{id}          — 更新连接
DELETE /api/v1/social/connectors/{id}         — 删除连接
POST   /api/v1/social/connectors/{id}/test    — 测试连接
POST   /api/v1/social/connectors/{id}/use     — 标记使用情况
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlmodel import Session

from app.db.database import get_session
from app.db.models.social_media_connector import (
    SocialMediaConnectorCreate,
    SocialMediaConnectorUpdate,
    SocialMediaConnectorResponse,
    SocialMediaPlatform,
    SocialAuthType,
    SocialConnectionStatus,
)
from app.services.social_media_connector.service import SocialMediaConnectorService

logger = logging.getLogger("ylcraft.api.social")

router = APIRouter(tags=["Social Media Connectors"])

# =============================================================================
# 支持的平台列表
# =============================================================================

SUPPORTED_SOCIAL_PLATFORMS = [
    {
        "value": "xhs",
        "label": "小红书",
        "icon": "book",
        "color": "#fe2c55",
        "auth_types": ["cookie"],
        "supports_publishing": True,
        "supports_stories": False,
    },
    {
        "value": "douyin",
        "label": "抖音",
        "icon": "video",
        "color": "#000000",
        "auth_types": ["cookie", "oauth2"],
        "supports_publishing": True,
        "supports_stories": True,
    },
    {
        "value": "kuaishou",
        "label": "快手",
        "icon": "play-circle",
        "color": "#ff5000",
        "auth_types": ["cookie"],
        "supports_publishing": True,
        "supports_stories": False,
    },
    {
        "value": "bilibili",
        "label": "B站",
        "icon": "tv",
        "color": "#00aeec",
        "auth_types": ["cookie"],
        "supports_publishing": True,
        "supports_stories": False,
    },
    {
        "value": "weibo",
        "label": "微博",
        "icon": "message",
        "color": "#ff8200",
        "auth_types": ["cookie", "oauth2"],
        "supports_publishing": True,
        "supports_stories": True,
    },
    {
        "value": "zhihu",
        "label": "知乎",
        "icon": "question",
        "color": "#0066ff",
        "auth_types": ["cookie"],
        "supports_publishing": True,
        "supports_stories": False,
    },
    {
        "value": "youtube",
        "label": "YouTube",
        "icon": "youtube",
        "color": "#ff0000",
        "auth_types": ["oauth2"],
        "supports_publishing": True,
        "supports_stories": True,
    },
    {
        "value": "tiktok",
        "label": "TikTok",
        "icon": "tiktok",
        "color": "#000000",
        "auth_types": ["cookie", "oauth2"],
        "supports_publishing": True,
        "supports_stories": True,
    },
    {
        "value": "twitter",
        "label": "Twitter/X",
        "icon": "twitter",
        "color": "#1da1f2",
        "auth_types": ["oauth2"],
        "supports_publishing": True,
        "supports_stories": False,
    },
    {
        "value": "reddit",
        "label": "Reddit",
        "icon": "globe",
        "color": "#ff4500",
        "auth_types": ["oauth2"],
        "supports_publishing": True,
        "supports_stories": False,
    },
    {
        "value": "instagram",
        "label": "Instagram",
        "icon": "image",
        "color": "#e4405f",
        "auth_types": ["oauth2"],
        "supports_publishing": True,
        "supports_stories": True,
    },
    {
        "value": "facebook",
        "label": "Facebook",
        "icon": "facebook",
        "color": "#1877f2",
        "auth_types": ["oauth2"],
        "supports_publishing": True,
        "supports_stories": True,
    },
]

AUTH_TYPES = [
    {"value": "cookie", "label": "Cookie 认证", "description": "使用浏览器 Cookie 登录"},
    {"value": "oauth2", "label": "OAuth2.0", "description": "授权第三方应用访问"},
    {"value": "password", "label": "账号密码", "description": "直接使用账号密码登录"},
    {"value": "qr_code", "label": "二维码扫码", "description": "扫码授权登录"},
]


# =============================================================================
# 依赖注入
# =============================================================================

def get_social_service(session: Session = Depends(get_session)) -> SocialMediaConnectorService:
    return SocialMediaConnectorService(session)


# =============================================================================
# API 端点
# =============================================================================

@router.get("/connectors/supported", summary="获取支持的社交平台")
async def get_supported_platforms():
    """返回所有支持的社交媒体平台和认证类型"""
    return {
        "success": True,
        "platforms": SUPPORTED_SOCIAL_PLATFORMS,
        "auth_types": AUTH_TYPES,
        "statuses": [
            {"value": "active", "label": "有效", "color": "#10a37f"},
            {"value": "expired", "label": "已过期", "color": "#ff9800"},
            {"value": "failed", "label": "连接失败", "color": "#f44336"},
            {"value": "pending", "label": "待验证", "color": "#9e9e9e"},
            {"value": "unknown", "label": "未测试", "color": "#607d8b"},
        ],
    }


@router.get("/connectors", summary="列出所有社交媒体连接")
async def list_connections(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    service: SocialMediaConnectorService = Depends(get_social_service),
):
    """列出所有社交媒体连接（不返回凭证内容）"""
    if platform:
        try:
            platform_enum = SocialMediaPlatform(platform)
            conns = service.list_by_platform(platform_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"未知平台: {platform}")
    else:
        conns = service.list_all()

    return {
        "success": True,
        "connections": [SocialMediaConnectorResponse.from_db(c) for c in conns],
        "total": len(conns),
    }


@router.get("/connectors/{conn_id}", summary="获取连接详情")
async def get_connection(
    conn_id: str,
    service: SocialMediaConnectorService = Depends(get_social_service),
):
    """获取单个连接详情"""
    conn = service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connection": SocialMediaConnectorResponse.from_db(conn),
    }


@router.post("/connectors", summary="创建社交媒体连接")
async def create_connection(
    data: SocialMediaConnectorCreate,
    service: SocialMediaConnectorService = Depends(get_social_service),
):
    """创建新的社交媒体连接"""
    try:
        conn = service.create(data)
        return {
            "success": True,
            "connection": SocialMediaConnectorResponse.from_db(conn),
            "message": f"社交媒体连接 {conn.name} 创建成功",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/connectors/{conn_id}", summary="更新社交媒体连接")
async def update_connection(
    conn_id: str,
    data: SocialMediaConnectorUpdate,
    service: SocialMediaConnectorService = Depends(get_social_service),
):
    """更新社交媒体连接"""
    conn = service.update(conn_id, data)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connection": SocialMediaConnectorResponse.from_db(conn),
        "message": "更新成功",
    }


@router.delete("/connectors/{conn_id}", summary="删除社交媒体连接")
async def delete_connection(
    conn_id: str,
    service: SocialMediaConnectorService = Depends(get_social_service),
):
    """删除社交媒体连接"""
    ok = service.delete(conn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "message": "删除成功",
    }


@router.post("/connectors/{conn_id}/test", summary="测试连接")
async def test_connection(
    conn_id: str,
    service: SocialMediaConnectorService = Depends(get_social_service),
):
    """测试连接有效性"""
    result = service.test_connection(conn_id)
    return {
        "success": result["success"],
        "message": result["message"],
        "connection_id": conn_id,
    }


@router.post("/connectors/{conn_id}/use", summary="标记使用情况")
async def mark_used(
    conn_id: str,
    success: bool = Query(True, description="是否成功"),
    error: str = Query("", description="错误信息"),
    service: SocialMediaConnectorService = Depends(get_social_service),
):
    """标记连接使用情况"""
    service.mark_used(conn_id, success, error)
    return {
        "success": True,
        "message": "已更新使用记录",
    }


@router.post("/connectors/{conn_id}/publish", summary="发布内容到平台")
async def publish_content(
    conn_id: str,
    content: dict,
    service: SocialMediaConnectorService = Depends(get_social_service),
):
    """
    使用指定连接发布内容到平台

    content 格式：
    {
        "title": "标题",
        "body": "正文内容",
        "content_type": "video|image|text|article",
        "tags": ["标签1", "标签2"],
        "media": [
            {"file_path": "/path/to/file.mp4", "media_type": "mp4"}
        ]
    }
    """
    result = service.publish(conn_id, content)
    return result


# =============================================================================
# 辅助函数
# =============================================================================

def get_active_connection(session: Session, platform: str) -> Optional[dict]:
    """
    获取指定平台的活跃连接凭证
    供搜索/下载/发布等功能调用
    """
    try:
        platform_enum = SocialMediaPlatform(platform)
        service = SocialMediaConnectorService(session)
        conn = service.get_active(platform_enum)
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
    except ValueError:
        return None
