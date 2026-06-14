"""
YLCraft — AI 能力中心

提供业务页统一选择模型/Provider 的轻量接口。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.db.database import SessionLocal
from app.db.models.ai_connector import AIConnector, AIProvider, AIProviderType

router = APIRouter()


CapabilityType = Literal["llm", "image", "video", "tts", "stt", "embedding"]


class AICapability(BaseModel):
    id: str
    name: str
    provider: str
    provider_label: str
    type: str
    model: str
    available_models: list[str] = []
    base_url: str | None = None
    api_endpoint: str | None = None
    api_format: str = "custom"
    has_api_key: bool = False
    is_default: bool = False
    priority: int = 0
    status: str = "available"
    status_message: str = "可用"
    capabilities: list[str] = []
    supported_sizes: list[str] = []
    support_reference_image: bool = False
    support_multiple_reference_images: bool = False
    support_vision_input: bool = False


class AICapabilitiesResponse(BaseModel):
    success: bool = True
    type: str | None = None
    capabilities: list[AICapability] = []


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except Exception:
        return []
    return []


def _image_capabilities(conn: AIConnector) -> list[str]:
    caps = ["text_to_image"]
    if conn.support_reference_image:
        caps.append("image_to_image")
    if conn.support_multiple_reference_images or conn.reference_image_array_field:
        caps.append("multi_reference_image")
    return caps


def _connector_status(conn: AIConnector) -> tuple[str, str]:
    if not conn.is_active:
        return "disabled", "已禁用"
    if not conn.api_key:
        return "missing_key", "未配置 API Key"
    if not conn.default_model:
        return "missing_model", "未配置默认模型"
    return "available", "可用"


def _to_capability(conn: AIConnector) -> AICapability:
    available_models = conn.get_available_models()
    if not available_models and conn.default_model:
        available_models = [conn.default_model]

    provider_type = conn.provider_type.value if hasattr(conn.provider_type, "value") else str(conn.provider_type)
    capabilities: list[str] = []
    if provider_type == "llm":
        capabilities = ["chat"]
        if conn.support_vision_input:
            capabilities.append("vision")
    elif provider_type == "image":
        capabilities = _image_capabilities(conn)
    elif provider_type == "video":
        capabilities = ["text_to_video", "image_to_video"]
    elif provider_type == "embedding":
        capabilities = [conn.embedding_type or "text"]
    elif provider_type == "tts":
        capabilities = ["text_to_speech"]
    elif provider_type == "stt":
        capabilities = ["speech_to_text"]

    status, status_message = _connector_status(conn)

    return AICapability(
        id=conn.id,
        name=conn.name,
        provider=conn.provider,
        provider_label=AIProvider.label(conn.provider),
        type=provider_type,
        model=conn.default_model or "",
        available_models=available_models,
        base_url=conn.base_url,
        api_endpoint=conn.api_endpoint,
        api_format=conn.api_format or "custom",
        has_api_key=bool(conn.api_key),
        is_default=bool(conn.is_default),
        priority=conn.priority or 0,
        status=status,
        status_message=status_message,
        capabilities=capabilities,
        supported_sizes=_json_list(conn.supported_sizes),
        support_reference_image=bool(conn.support_reference_image),
        support_multiple_reference_images=bool(conn.support_multiple_reference_images),
        support_vision_input=bool(conn.support_vision_input),
    )


@router.get("/capabilities", response_model=AICapabilitiesResponse, summary="获取 AI 能力列表")
async def list_ai_capabilities(
    type: CapabilityType | None = Query(default=None, description="能力类型：llm/image/video/tts/stt/embedding"),
    available_only: bool = Query(default=False, description="只返回已启用、已配置 Key、已配置模型的能力"),
):
    with SessionLocal() as session:
        query = session.query(AIConnector)
        if type:
            query = query.filter(AIConnector.provider_type == AIProviderType(type))
        connectors = query.order_by(AIConnector.priority.asc(), AIConnector.created_at.desc()).all()

    capabilities = [_to_capability(conn) for conn in connectors]
    if available_only:
        capabilities = [item for item in capabilities if item.status == "available"]

    return AICapabilitiesResponse(success=True, type=type, capabilities=capabilities)
