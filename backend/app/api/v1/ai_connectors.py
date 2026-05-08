"""
YLCraft — AI 连接器 API

GET    /api/v1/ai/connectors           — 列出所有 AI 连接
GET    /api/v1/ai/connectors/supported  — 获取支持的 AI 提供商
GET    /api/v1/ai/connectors/{id}       — 获取连接详情
POST   /api/v1/ai/connectors            — 创建新连接
PUT    /api/v1/ai/connectors/{id}       — 更新连接
DELETE /api/v1/ai/connectors/{id}       — 删除连接
POST   /api/v1/ai/connectors/{id}/test  — 测试连接
GET    /api/v1/ai/connectors/{id}/usage — 获取使用统计
POST   /api/v1/ai/connectors/{id}/use   — 标记为已使用
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlmodel import Session, SQLModel

from app.db.database import get_session
from app.db.models.ai_connector import (
    AIConnectorCreate,
    AIConnectorUpdate,
    AIConnectorResponse,
    AIProvider,
)
from app.services.ai_connector.service import AIConnectorService

logger = logging.getLogger("ylcraft.api.ai")

router = APIRouter(prefix="/connectors", tags=["AI Connectors"])

# =============================================================================
# 支持的 AI 提供商列表
# =============================================================================

# 简化的 AI Provider 配置（全部使用 OpenAI 兼容 API）
SUPPORTED_AI_PROVIDERS = [
    {
        "value": "openai",
        "label": "OpenAI",
        "color": "#10a37f",
        "icon": "brain",
        "models": [],  # 用户自定义
        "default_model": "gpt-4o",
        "supports_images": True,
        "supports_streaming": True,
    },
    {
        "value": "siliconflow",
        "label": "硅基流动 (SiliconFlow)",
        "color": "#00d4aa",
        "icon": "cloud",
        "models": [],  # 用户自定义
        "default_model": "Qwen/Qwen2.5-VL-32B-Instruct",
        "supports_images": True,
        "supports_streaming": True,
        "base_url": "https://api.siliconflow.cn/v1",
    },
    {
        "value": "gemini",
        "label": "Google Gemini",
        "color": "#4285f4",
        "icon": "globe",
        "models": [],  # 用户自定义
        "default_model": "gemini-1.5-flash",
        "supports_images": True,
        "supports_streaming": True,
    },
    {
        "value": "generic",
        "label": "通用配置 (Generic)",
        "color": "#94a3b8",
        "icon": "settings",
        "models": [],  # 完全自定义
        "default_model": "",
        "supports_images": True,
        "supports_streaming": True,
    },
]


# =============================================================================
# 依赖注入
# =============================================================================

from app.db.database import AsyncSessionLocal

async def get_ai_service():
    """获取 AI 连接服务（异步 session）"""
    async with AsyncSessionLocal() as session:
        yield AIConnectorService(session)


# =============================================================================
# API 端点
# =============================================================================

@router.get("/supported", summary="获取支持的 AI 提供商")
async def get_supported_ai_providers():
    """返回所有支持的 AI 提供商和模型"""
    return {
        "success": True,
        "providers": SUPPORTED_AI_PROVIDERS,
    }


@router.get("", summary="列出所有 AI 连接")
async def list_connectors(
    provider: Optional[str] = Query(None, description="按提供商筛选"),
    provider_type: Optional[str] = Query(None, description="按类型筛选：llm/image/video/tts/stt"),
    active_only: bool = Query(False, description="仅显示活跃"),
    service: AIConnectorService = Depends(get_ai_service),
):
    """列出所有 AI 连接（不返回 API Key）"""
    if provider:
        # provider 现在是字符串，直接使用
        conns = await service.list_by_provider(provider)
    elif provider_type:
        # 按类型筛选
        conns = await service.list_by_type(provider_type)
    elif active_only:
        conns = await service.list_active()
    else:
        conns = await service.list_all()

    return {
        "success": True,
        "connectors": [AIConnectorResponse.from_db(c) for c in conns],
        "total": len(conns),
    }


@router.get("/{conn_id}", summary="获取连接详情")
async def get_connector(
    conn_id: str,
    service: AIConnectorService = Depends(get_ai_service),
):
    """获取单个连接详情（不返回 API Key）"""
    conn = await service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connector": AIConnectorResponse.from_db(conn),
    }


@router.post("", summary="创建 AI 连接")
async def create_connector(
    data: AIConnectorCreate,
    service: AIConnectorService = Depends(get_ai_service),
):
    """创建新的 AI 连接"""
    try:
        conn = await service.create(data)
        return {
            "success": True,
            "connector": AIConnectorResponse.from_db(conn),
            "message": f"AI 连接 {conn.name} 创建成功",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/{conn_id}", summary="更新 AI 连接")
async def update_connector(
    conn_id: str,
    data: AIConnectorUpdate,
    service: AIConnectorService = Depends(get_ai_service),
):
    """更新 AI 连接"""
    conn = await service.update(conn_id, data)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connector": AIConnectorResponse.from_db(conn),
        "message": "更新成功",
    }


@router.delete("/{conn_id}", summary="删除 AI 连接")
async def delete_connector(
    conn_id: str,
    service: AIConnectorService = Depends(get_ai_service),
):
    """删除 AI 连接"""
    ok = await service.delete(conn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "message": "删除成功",
    }


class TestRequest(SQLModel):
    body: Optional[dict] = None


@router.post("/{conn_id}/test", summary="测试连接")
async def test_connector(
    conn_id: str,
    test_request: Optional[TestRequest] = None,
    service: AIConnectorService = Depends(get_ai_service),
):
    """测试 AI 连接有效性"""
    custom_body = test_request.body if test_request else None
    result = await service.test_connection(conn_id, custom_body)
    return {
        "success": result["success"],
        "message": result["message"],
        "connector_id": conn_id,
        "debug": result.get("debug"),
    }


@router.get("/{conn_id}/usage", summary="获取使用统计")
async def get_usage_stats(
    conn_id: str,
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    service: AIConnectorService = Depends(get_ai_service),
):
    """获取 AI 连接的使用统计"""
    conn = await service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    stats = await service.get_usage_stats(conn_id, days)
    return {
        "success": True,
        "connector_id": conn_id,
        "stats": stats,
    }


@router.post("/{conn_id}/use", summary="标记为已使用")
async def mark_used(
    conn_id: str,
    service: AIConnectorService = Depends(get_ai_service),
):
    """标记连接已使用"""
    conn = await service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    conn.last_used = datetime.now(timezone.utc)
    service.session.add(conn)
    await service.session.commit()

    return {
        "success": True,
        "message": "已更新使用时间",
    }


# =============================================================================
# 辅助函数
# =============================================================================

from datetime import datetime, timezone


def get_default_connector(session: Session) -> Optional[AIConnector]:
    """获取默认 AI 连接"""
    service = AIConnectorService(session)
    return service.get_default()


def get_connector_by_provider(session: Session, provider: str) -> Optional[AIConnector]:
    """获取指定提供商的 AI 连接"""
    service = AIConnectorService(session)
    return service.get_by_provider(provider)
