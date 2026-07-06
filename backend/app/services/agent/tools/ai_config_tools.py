"""Agent tools for inspecting and configuring AI connector/model settings.

Conversational workflow for the Agent:
  1. User describes a provider spec  → Agent calls upsert_provider_metadata
  2. User describes model config    → Agent calls create_ai_connector
  3. User wants to modify a config  → Agent calls update_ai_connector
  4. User wants to verify config    → Agent calls test_ai_connector
  5. User wants to discover models  → Agent calls discover_connector_models

Read tools:  list_ai_connectors, get_ai_connector, list_provider_metadata, get_provider_metadata
Write tools: upsert_provider_metadata, create_ai_connector, update_ai_connector
Verify:      test_ai_connector, discover_connector_models
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlmodel import select

from app.db.database import AsyncSessionLocal, SessionLocal
from app.db.models.ai_connector import (
    AIConnector,
    AIConnectorCreate,
    AIProviderMetadata,
    AIProviderMetadataCreate,
    AIProviderMetadataUpdate,
    AIProviderType,
)
from app.services.agent.registry import register_tool
from app.services.ai_connector.service import AIConnectorService, normalize_sizes_value

logger = logging.getLogger("ylcraft.agent.ai_config_tools")

# =============================================================================
# 内部辅助函数
# =============================================================================

VALID_PROVIDER_TYPES = {e.value for e in AIProviderType}
JSON_FIELDS_PROVIDER = [
    "supported_types", "default_models", "available_models", "default_params",
    "request_templates", "response_configs", "supported_sizes",
    "reference_image_configs", "parameter_transforms",
]


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _parse_json_argument(raw: str | None, field_name: str, expected: type) -> tuple[Any, str | None]:
    if raw is None or str(raw).strip() == "":
        return expected(), None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"{field_name} 不是有效 JSON: {e.msg}"
    if not isinstance(parsed, expected):
        expected_name = "array" if expected is list else "object"
        return None, f"{field_name} 必须是 JSON {expected_name}"
    return parsed, None


def _to_json_str(value: Any) -> str:
    """序列化为 JSON 字符串（用于数据库字段）。"""
    if isinstance(value, str):
        try:
            json.loads(value)  # 已经是合法 JSON 字符串
            return value
        except Exception:
            return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def _normalize_provider_type(pt: str) -> str:
    """标准化 provider_type，无效时回退 llm。"""
    if pt in VALID_PROVIDER_TYPES:
        return pt
    return "llm"


def _connector_summary(connector: AIConnector) -> dict[str, Any]:
    provider_type = getattr(connector.provider_type, "value", connector.provider_type)
    return {
        "id": connector.id,
        "name": connector.name,
        "provider": connector.provider,
        "provider_type": provider_type,
        "api_format": connector.api_format,
        "default_model": connector.default_model,
        "available_models": connector.get_available_models(),
        "is_active": connector.is_active,
        "is_default": connector.is_default,
        "priority": connector.priority,
        "base_url": connector.base_url,
        "api_endpoint": connector.api_endpoint,
        "support_vision_input": connector.support_vision_input,
        "support_reference_image": connector.support_reference_image,
        "support_multiple_reference_images": connector.support_multiple_reference_images,
        "supported_sizes": _loads(connector.supported_sizes, []),
        "has_api_key": bool(connector.api_key),
        "usage_count": connector.usage_count,
        "total_cost": connector.total_cost,
        "last_used": connector.last_used.isoformat() if connector.last_used else None,
    }


def _connector_detail(connector: AIConnector) -> dict[str, Any]:
    payload = _connector_summary(connector)
    payload.update(
        {
            "description": connector.description or "",
            "max_tokens": connector.max_tokens,
            "temperature": connector.temperature,
            "timeout": connector.timeout,
            "test_timeout": connector.test_timeout,
            "monthly_budget": connector.monthly_budget,
            "daily_limit": connector.daily_limit,
            "price_per_call": connector.price_per_call,
            "default_params": _loads(connector.default_params, {}),
            "response_config": _loads(connector.response_config, {}),
            "parameter_transforms": _loads(connector.parameter_transforms, {}),
            "request_template": connector.request_template or "",
            "reference_image_field": connector.reference_image_field,
            "reference_image_array_field": connector.reference_image_array_field,
            "embedding_type": connector.embedding_type,
            "embedding_dimension": connector.embedding_dimension,
            "normalize_embeddings": connector.normalize_embeddings,
            "test_prompt": connector.test_prompt or "",
        }
    )
    return payload


def _find_connector(session, connector_id: str = "", name: str = "") -> AIConnector | None:
    if connector_id:
        return session.get(AIConnector, connector_id)
    if name:
        return session.exec(select(AIConnector).where(AIConnector.name == name)).first()
    return None


def _provider_summary(provider: AIProviderMetadata) -> dict[str, Any]:
    return {
        "provider_id": provider.provider_id,
        "name": provider.name,
        "icon": provider.icon,
        "color": provider.color,
        "description": provider.description or "",
        "base_url": provider.base_url,
        "api_format": provider.api_format,
        "supported_types": provider.get_supported_types(),
        "default_models": provider.get_default_models(),
        "available_models": provider.get_available_models(),
        "is_active": provider.is_active,
        "is_editable": provider.is_editable,
    }


def _provider_detail(provider: AIProviderMetadata) -> dict[str, Any]:
    payload = _provider_summary(provider)
    payload.update({
        "default_params": provider.get_default_params(),
        "request_templates": provider.get_request_templates(),
        "response_configs": provider.get_response_configs(),
        "supported_sizes": provider.get_supported_sizes(),
        "reference_image_configs": provider.get_reference_image_configs(),
        "parameter_transforms": provider.get_parameter_transforms(),
        "has_api_key": bool(provider.api_key),
        "created_at": provider.created_at.isoformat() if provider.created_at else None,
        "updated_at": provider.updated_at.isoformat() if provider.updated_at else None,
    })
    return payload


# =============================================================================
# 只读工具
# =============================================================================

@register_tool(
    name="list_ai_connectors",
    description="列出当前配置的 AI 连接器和默认模型，供智能体选择文本、生图、视频、语音或嵌入模型。",
    category="ai_config",
    examples=["列出可用文本模型", "看看有哪些生图模型支持参考图", "当前默认模型是什么"],
    input_schema_note="provider_type 可选 llm/image/video/tts/stt/embedding/all；active_only 默认 true；keyword 可按名称、提供商、模型模糊过滤；limit 最大 100。",
    output_schema_note="返回 success、total、connectors；不会返回 API Key，只返回 has_api_key、默认模型、可用模型、能力和使用统计摘要。",
    risk_level="read",
    output_type="ai_connector_list",
)
async def list_ai_connectors(
    provider_type: str = "all",
    active_only: bool = True,
    keyword: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    with SessionLocal() as session:
        stmt = select(AIConnector)
        if active_only:
            stmt = stmt.where(AIConnector.is_active == True)
        if provider_type and provider_type not in {"all", "*"}:
            stmt = stmt.where(AIConnector.provider_type == provider_type)
        stmt = stmt.order_by(AIConnector.provider_type, AIConnector.priority, AIConnector.name).limit(max(1, min(int(limit or 50), 100)))
        connectors = session.exec(stmt).all()

        needle = (keyword or "").strip().lower()
        if needle:
            connectors = [
                item
                for item in connectors
                if needle in (item.name or "").lower()
                or needle in (item.provider or "").lower()
                or needle in (item.default_model or "").lower()
            ]
        return {
            "success": True,
            "total": len(connectors),
            "connectors": [_connector_summary(item) for item in connectors],
        }


@register_tool(
    name="get_ai_connector",
    description="读取单个 AI 连接器的非敏感详情，帮助智能体判断请求路径、SDK/HTTP 模式、尺寸、参考图能力和响应解析配置。",
    category="ai_config",
    examples=["查看魔塔生图连接器详情", "检查这个模型为什么是 HTTP 模式", "看 gpt-image 连接器支持什么尺寸"],
    input_schema_note="connector_id 和 name 二选一；name 为连接器显示名称。",
    output_schema_note="返回 success、connector；connector 包含 request_template/response_config/default_params，但不会返回 api_key。",
    risk_level="read",
    output_type="ai_connector_detail",
)
async def get_ai_connector(connector_id: str = "", name: str = "") -> dict[str, Any]:
    with SessionLocal() as session:
        connector = _find_connector(session, connector_id=connector_id, name=name)
        if not connector:
            return {"success": False, "message": "AI 连接器不存在", "connector_id": connector_id, "name": name}
        return {"success": True, "connector": _connector_detail(connector)}


@register_tool(
    name="list_provider_metadata",
    description="列出所有已注册的 AI 供应商规范（Provider Metadata），包含各类型的默认模型、请求模板、响应解析配置。",
    category="ai_config",
    examples=["列出所有供应商", "看看有哪些已注册的供应商规范"],
    input_schema_note="active_only 默认 false，设为 true 仅返回启用的供应商。",
    output_schema_note="返回 success、total、providers 列表（摘要信息）。",
    risk_level="read",
    output_type="provider_metadata_list",
)
async def list_provider_metadata(active_only: bool = False) -> dict[str, Any]:
    with SessionLocal() as session:
        stmt = select(AIProviderMetadata)
        if active_only:
            stmt = stmt.where(AIProviderMetadata.is_active == True)
        stmt = stmt.order_by(AIProviderMetadata.name)
        providers = session.exec(stmt).all()
        return {
            "success": True,
            "total": len(providers),
            "providers": [_provider_summary(p) for p in providers],
        }


@register_tool(
    name="get_provider_metadata",
    description="读取单个供应商规范的完整详情，包含各类型的 request_template、response_config、default_params 等。",
    category="ai_config",
    examples=["查看 OpenAI 供应商规范", "看硅基流动的图片生成请求模板"],
    input_schema_note="provider_id 必填，如 openai、siliconflow、gemini、qwen、generic。",
    output_schema_note="返回 success、provider 完整详情。",
    risk_level="read",
    output_type="provider_metadata_detail",
)
async def get_provider_metadata(provider_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        provider = session.get(AIProviderMetadata, provider_id)
        if not provider:
            return {"success": False, "message": f"供应商 '{provider_id}' 不存在"}
        return {"success": True, "provider": _provider_detail(provider)}


# =============================================================================
# 写入工具 — 供应商规范管理
# =============================================================================

@register_tool(
    name="upsert_provider_metadata",
    description=(
        "创建或更新 AI 供应商规范（Provider Metadata）。"
        "当用户描述一个供应商的 API 规范时调用此工具，将规范持久化到数据库。"
        "创建的规范可供后续 create_ai_connector 使用。"
    ),
    category="ai_config",
    examples=[
        "帮我注册 Novita AI，OpenAI 兼容格式，base_url 是 https://api.novita.ai/v3/openai，支持 llm 和 image",
        "更新硅基流动的供应商规范，加入新的默认模型",
    ],
    input_schema_note=(
        "provider_id 必填（英文标识，如 novita、together）；name 必填；"
        "base_url、api_format（openai-compatible/custom/gemini）、"
        "supported_types（如 ['llm', 'image']）；"
        "request_templates、response_configs、default_models、available_models、"
        "default_params 均为按 provider_type 分组的字典；"
        "provider_id 已存在时更新，否则新建。"
    ),
    output_schema_note="返回 success、provider、action（created/updated）。",
    risk_level="write",
    output_type="provider_metadata_result",
)
async def upsert_provider_metadata(
    provider_id: str,
    name: str,
    base_url: str = "",
    api_format: str = "custom",
    supported_types: str = "[]",           # JSON 数组字符串，如 '["llm","image"]'
    description: str = "",
    api_key: str = "",
    request_templates: str = "{}",          # JSON 对象字符串，按类型分组
    response_configs: str = "{}",           # JSON 对象字符串
    default_models: str = "{}",             # JSON 对象字符串
    available_models: str = "{}",           # JSON 对象字符串
    default_params: str = "{}",             # JSON 对象字符串
    supported_sizes: str = "{}",            # JSON 对象字符串
    reference_image_configs: str = "{}",    # JSON 对象字符串
    parameter_transforms: str = "{}",       # JSON 对象字符串
    is_active: bool = True,
    is_editable: bool = True,
) -> dict[str, Any]:
    """创建或更新供应商元数据。"""
    # 解析所有 JSON 参数字段
    parsed_supported_types, error = _parse_json_argument(supported_types, "supported_types", list)
    if error:
        return {"success": False, "message": error, "field": "supported_types"}
    parsed_request_templates, error = _parse_json_argument(request_templates, "request_templates", dict)
    if error:
        return {"success": False, "message": error, "field": "request_templates"}
    parsed_response_configs, error = _parse_json_argument(response_configs, "response_configs", dict)
    if error:
        return {"success": False, "message": error, "field": "response_configs"}
    parsed_default_models, error = _parse_json_argument(default_models, "default_models", dict)
    if error:
        return {"success": False, "message": error, "field": "default_models"}
    parsed_available_models, error = _parse_json_argument(available_models, "available_models", dict)
    if error:
        return {"success": False, "message": error, "field": "available_models"}
    parsed_default_params, error = _parse_json_argument(default_params, "default_params", dict)
    if error:
        return {"success": False, "message": error, "field": "default_params"}
    parsed_supported_sizes, error = _parse_json_argument(supported_sizes, "supported_sizes", dict)
    if error:
        return {"success": False, "message": error, "field": "supported_sizes"}
    parsed_ref_configs, error = _parse_json_argument(reference_image_configs, "reference_image_configs", dict)
    if error:
        return {"success": False, "message": error, "field": "reference_image_configs"}
    parsed_param_transforms, error = _parse_json_argument(parameter_transforms, "parameter_transforms", dict)
    if error:
        return {"success": False, "message": error, "field": "parameter_transforms"}

    with SessionLocal() as session:
        existing = session.get(AIProviderMetadata, provider_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        action = "updated" if existing else "created"

        if existing:
            existing.name = name
            existing.icon = "brain"
            existing.color = "#94a3b8"
            existing.description = description or ""
            existing.base_url = base_url or None
            existing.api_format = api_format
            existing.supported_types = _to_json_str(parsed_supported_types)
            existing.default_models = _to_json_str(parsed_default_models)
            existing.available_models = _to_json_str(parsed_available_models)
            existing.default_params = _to_json_str(parsed_default_params)
            existing.request_templates = _to_json_str(parsed_request_templates)
            existing.response_configs = _to_json_str(parsed_response_configs)
            existing.supported_sizes = _to_json_str(parsed_supported_sizes)
            existing.reference_image_configs = _to_json_str(parsed_ref_configs)
            existing.parameter_transforms = _to_json_str(parsed_param_transforms)
            existing.is_active = is_active
            existing.is_editable = is_editable
            if api_key:
                existing.api_key = api_key
            existing.updated_at = now
            provider = existing
        else:
            provider = AIProviderMetadata(
                provider_id=provider_id,
                name=name,
                icon="brain",
                color="#94a3b8",
                description=description or "",
                base_url=base_url or None,
                api_key=api_key or None,
                api_format=api_format,
                supported_types=_to_json_str(parsed_supported_types),
                default_models=_to_json_str(parsed_default_models),
                available_models=_to_json_str(parsed_available_models),
                default_params=_to_json_str(parsed_default_params),
                request_templates=_to_json_str(parsed_request_templates),
                response_configs=_to_json_str(parsed_response_configs),
                supported_sizes=_to_json_str(parsed_supported_sizes),
                reference_image_configs=_to_json_str(parsed_ref_configs),
                parameter_transforms=_to_json_str(parsed_param_transforms),
                is_active=is_active,
                is_editable=is_editable,
                created_at=now,
                updated_at=now,
            )
            session.add(provider)

        session.commit()
        session.refresh(provider)
        return {
            "success": True,
            "action": action,
            "provider": _provider_summary(provider),
            "message": f"供应商 '{name}' ({provider_id}) { '更新' if action == 'updated' else '创建' }成功",
        }


# =============================================================================
# 写入工具 — 连接器配置管理
# =============================================================================

@register_tool(
    name="create_ai_connector",
    description=(
        "创建新的 AI 连接器配置。当你了解了用户的供应商规范和模型规范后，"
        "调用此工具生成完整的连接器配置持久化到数据库。"
        "支持配置 request_template（Jinja2 格式请求体模板）、"
        "response_config（响应 JSONPath 解析）、"
        "parameter_transforms（参数转换规则）等高级字段。"
    ),
    category="ai_config",
    examples=[
        "为 novita 创建一个 image 类型的连接器，默认模型 dreamshaper_8",
        "创建一个支持视觉输入的 llm 连接器，用 qwen-vl 模型",
    ],
    input_schema_note=(
        "name、provider、provider_type(llm/image/video/tts/stt/embedding)、"
        "default_model、api_key 为必填核心字段。"
        "base_url、request_template、response_config 等为可选高级配置。"
        "request_template 使用 Jinja2 语法，可用变量：{{ model }}, {{ prompt }}, {{ negative_prompt }}, {{ size }} 等。"
        "response_config 为 JSON，包含 images_path（JSONPath）、error_path、response_format 等。"
        "supported_sizes 为 JSON 数组字符串如 '[\"1024x1024\"]'。"
    ),
    output_schema_note="返回 success、connector（包含 id 和摘要）。",
    risk_level="write",
    output_type="ai_connector_created",
)
async def create_ai_connector(
    name: str,
    provider: str,
    provider_type: str = "llm",
    default_model: str = "",
    api_key: str = "",
    base_url: str = "",
    api_endpoint: str = "",
    api_format: str = "custom",
    description: str = "",
    is_active: bool = True,
    is_default: bool = False,
    priority: int = 0,
    # 模型配置
    available_models: str = "[]",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    # 请求/响应高级配置
    request_template: str = "",
    response_config: str = "",
    parameter_transforms: str = "",
    supported_sizes: str = "[]",
    default_params: str = "{}",
    # 参考图配置
    support_reference_image: bool = False,
    support_multiple_reference_images: bool = False,
    reference_image_field: str = "image",
    reference_image_array_field: str = "",
    # 视觉支持
    support_vision_input: bool = False,
    # 嵌入配置
    embedding_type: str = "",
    embedding_dimension: int = 0,
    normalize_embeddings: bool = True,
    # 超时
    timeout: int = 300,
    test_timeout: int = 20,
    test_prompt: str = "",
    # 成本
    monthly_budget: float = 0,
    daily_limit: int = 0,
    price_per_call: float = 0,
) -> dict[str, Any]:
    """创建新的 AI 连接器。"""
    pt = _normalize_provider_type(provider_type)

    # 解析 available_models
    models_list = _loads(available_models, [])
    if isinstance(models_list, str):
        models_list = [m.strip() for m in models_list.split(",") if m.strip()]
    if not isinstance(models_list, list):
        models_list = []

    conn_id = str(uuid.uuid4())

    with SessionLocal() as session:
        if is_default:
            # 取消其他默认连接
            default_conns = session.exec(
                select(AIConnector).where(AIConnector.is_default == True)
            ).all()
            for dc in default_conns:
                dc.is_default = False
                session.add(dc)

        # 处理 supported_sizes 标准化
        sizes_raw = _loads(supported_sizes, [])
        if isinstance(sizes_raw, list):
            sizes_raw = json.dumps([s.replace("*", "x") for s in sizes_raw if s])
        elif isinstance(sizes_raw, str) and sizes_raw:
            sizes_raw = normalize_sizes_value(sizes_raw)
        else:
            sizes_raw = None

        conn = AIConnector(
            id=conn_id,
            name=name,
            provider=provider,
            api_key=api_key,
            provider_type=pt,
            base_url=base_url or None,
            api_endpoint=api_endpoint or None,
            default_model=default_model,
            max_tokens=max_tokens,
            temperature=temperature,
            is_active=is_active,
            is_default=is_default,
            priority=priority,
            description=description or "",
            request_template=request_template or None,
            response_config=response_config or None,
            parameter_transforms=parameter_transforms or None,
            supported_sizes=sizes_raw,
            default_params=default_params or None,
            support_reference_image=support_reference_image,
            support_multiple_reference_images=support_multiple_reference_images,
            reference_image_field=reference_image_field,
            reference_image_array_field=reference_image_array_field or None,
            support_vision_input=support_vision_input,
            embedding_type=embedding_type or None,
            embedding_dimension=embedding_dimension or None,
            normalize_embeddings=normalize_embeddings,
            timeout=timeout,
            test_timeout=test_timeout,
            test_prompt=test_prompt or None,
            monthly_budget=monthly_budget if monthly_budget > 0 else None,
            daily_limit=daily_limit if daily_limit > 0 else None,
            price_per_call=price_per_call if price_per_call > 0 else None,
            api_format=api_format,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        conn.set_available_models(models_list)
        session.add(conn)
        session.commit()
        session.refresh(conn)

        return {
            "success": True,
            "connector": _connector_summary(conn),
            "message": f"连接器 '{name}' 创建成功，ID: {conn_id}",
        }


@register_tool(
    name="update_ai_connector",
    description="更新已有的 AI 连接器配置。可修改模型、API Key、请求模板、响应解析配置等任意字段。",
    category="ai_config",
    examples=["把 OpenAI 连接器的默认模型改成 gpt-4o", "更新生图连接器的 request_template"],
    input_schema_note=(
        "connector_id 必填（可通过 list_ai_connectors 获取）。"
        "只传需要修改的字段，未传字段保持不变。"
        "provider_type 可选 llm/image/video/tts/stt/embedding。"
    ),
    output_schema_note="返回 success、connector 更新后的摘要。",
    risk_level="write",
    output_type="ai_connector_updated",
)
async def update_ai_connector(
    connector_id: str,
    name: str = "",
    provider: str = "",
    provider_type: str = "",
    default_model: str = "",
    api_key: str = "",
    base_url: str = "",
    api_endpoint: str = "",
    api_format: str = "",
    description: str = "",
    is_active: str = "",  # 用字符串区分"未传"和"传了 False"
    is_default: str = "",
    priority: str = "",
    available_models: str = "",
    max_tokens: str = "",
    temperature: str = "",
    request_template: str = "",
    response_config: str = "",
    parameter_transforms: str = "",
    supported_sizes: str = "",
    default_params: str = "",
    support_reference_image: str = "",
    support_multiple_reference_images: str = "",
    reference_image_field: str = "",
    reference_image_array_field: str = "",
    support_vision_input: str = "",
    embedding_type: str = "",
    embedding_dimension: str = "",
    normalize_embeddings: str = "",
    timeout: str = "",
    test_timeout: str = "",
    test_prompt: str = "",
    monthly_budget: str = "",
    daily_limit: str = "",
    price_per_call: str = "",
) -> dict[str, Any]:
    """更新已有连接器，只修改传入的字段。"""
    with SessionLocal() as session:
        connector = session.get(AIConnector, connector_id)
        if not connector:
            return {"success": False, "message": f"连接器 '{connector_id}' 不存在"}

        updated_fields = []

        def _apply(field_name: str, value: str, setter_fn=None):
            nonlocal updated_fields
            if value == "" or value is None:
                return
            if setter_fn:
                setter_fn(value)
            else:
                setattr(connector, field_name, value)
            updated_fields.append(field_name)

        _apply("name", name)
        _apply("provider", provider)
        if provider_type:
            _apply("provider_type", _normalize_provider_type(provider_type), lambda v: setattr(connector, "provider_type", v))
        _apply("default_model", default_model)
        if api_key:
            _apply("api_key", api_key)
        if base_url:
            _apply("base_url", base_url or None)
        if api_endpoint:
            _apply("api_endpoint", api_endpoint or None)
        if api_format:
            _apply("api_format", api_format)
        _apply("description", description)
        if is_active == "true":
            _apply("is_active", True)
        elif is_active == "false":
            _apply("is_active", False)
        if is_default == "true":
            # 先取消其他默认
            default_conns = session.exec(
                select(AIConnector).where(AIConnector.is_default == True)
            ).all()
            for dc in default_conns:
                dc.is_default = False
                session.add(dc)
            _apply("is_default", True)
        elif is_default == "false":
            _apply("is_default", False)
        if priority:
            _apply("priority", int(priority))

        if available_models:
            models = _loads(available_models, [])
            if isinstance(models, str):
                models = [m.strip() for m in models.split(",") if m.strip()]
            if isinstance(models, list):
                connector.set_available_models(models)
                updated_fields.append("available_models")

        if max_tokens:
            _apply("max_tokens", int(max_tokens))
        if temperature:
            _apply("temperature", float(temperature))
        if request_template:
            _apply("request_template", request_template or None)
        if response_config:
            _apply("response_config", response_config or None)
        if parameter_transforms:
            _apply("parameter_transforms", parameter_transforms or None)
        if supported_sizes:
            sizes = _loads(supported_sizes, [])
            if isinstance(sizes, list):
                sizes = json.dumps([s.replace("*", "x") for s in sizes if s])
                _apply("supported_sizes", sizes)
            else:
                _apply("supported_sizes", normalize_sizes_value(supported_sizes))
        if default_params:
            _apply("default_params", default_params)

        if support_reference_image == "true":
            _apply("support_reference_image", True)
        elif support_reference_image == "false":
            _apply("support_reference_image", False)
        if support_multiple_reference_images == "true":
            _apply("support_multiple_reference_images", True)
        elif support_multiple_reference_images == "false":
            _apply("support_multiple_reference_images", False)
        if reference_image_field:
            _apply("reference_image_field", reference_image_field)
        if reference_image_array_field:
            _apply("reference_image_array_field", reference_image_array_field or None)

        if support_vision_input == "true":
            _apply("support_vision_input", True)
        elif support_vision_input == "false":
            _apply("support_vision_input", False)

        if embedding_type:
            _apply("embedding_type", embedding_type or None)
        if embedding_dimension:
            _apply("embedding_dimension", int(embedding_dimension) if int(embedding_dimension) > 0 else None)
        if normalize_embeddings == "true":
            _apply("normalize_embeddings", True)
        elif normalize_embeddings == "false":
            _apply("normalize_embeddings", False)

        if timeout:
            _apply("timeout", int(timeout))
        if test_timeout:
            _apply("test_timeout", int(test_timeout))
        if test_prompt:
            _apply("test_prompt", test_prompt or None)

        if monthly_budget:
            _apply("monthly_budget", float(monthly_budget) if float(monthly_budget) > 0 else None)
        if daily_limit:
            _apply("daily_limit", int(daily_limit) if int(daily_limit) > 0 else None)
        if price_per_call:
            _apply("price_per_call", float(price_per_call) if float(price_per_call) > 0 else None)

        if not updated_fields:
            return {"success": False, "message": "没有需要更新的字段"}

        connector.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.add(connector)
        session.commit()
        session.refresh(connector)

        return {
            "success": True,
            "message": f"连接器 '{connector.name}' 更新成功，变更字段: {', '.join(updated_fields)}",
            "connector": _connector_summary(connector),
            "updated_fields": updated_fields,
        }


# =============================================================================
# 验证工具
# =============================================================================

@register_tool(
    name="test_ai_connector",
    description="测试 AI 连接器的连通性和配置有效性。发送测试请求到供应商 API，返回成功/失败及诊断信息。",
    category="ai_config",
    examples=["测试一下刚创建的连接器能不能用", "验证 OpenAI 的 API Key 是否有效"],
    input_schema_note="connector_id 必填。",
    output_schema_note="返回 success、message 及 debug 诊断信息。",
    risk_level="read",
    output_type="test_result",
)
async def test_ai_connector(
    connector_id: str,
    image_url: str = "",
    image_path: str = "",
    image_mode: str = "",
    request_content_type: str = "",
    response_format: str = "",
) -> dict[str, Any]:
    """测试连接器连通性（异步方式调用 AIConnectorService）。"""
    try:
        async with AsyncSessionLocal() as session:
            service = AIConnectorService(session)
            conn = await service.get(connector_id)
            if not conn:
                return {"success": False, "message": f"连接器 '{connector_id}' 不存在"}

            test_options = {
                key: value
                for key, value in {
                    "image_url": image_url,
                    "image_path": image_path,
                    "image_mode": image_mode,
                    "request_content_type": request_content_type,
                    "response_format": response_format,
                }.items()
                if value
            }
            result = await service.test_connection(connector_id, test_options=test_options or None)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "debug": result.get("debug"),
            }
    except Exception as e:
        logger.error(f"[ai_config_tools] test_ai_connector 异常: {e}")
        return {"success": False, "message": f"测试异常: {str(e)}"}


# =============================================================================
# 发现工具
# =============================================================================

@register_tool(
    name="discover_connector_models",
    description=(
        "从 AI 供应商 API 自动发现可用模型列表。"
        "创建连接器后，可调用此工具自动获取该供应商支持的所有模型，"
        "方便用户选择默认模型。"
    ),
    category="ai_config",
    examples=["发现 Novita 支持哪些模型", "拉取 OpenAI 的模型列表"],
    input_schema_note=(
        "connector_id 必填（必须先 create_ai_connector）。"
    ),
    output_schema_note="返回 success、models 列表、total 数量。",
    risk_level="read",
    output_type="model_discovery",
)
async def discover_connector_models(connector_id: str) -> dict[str, Any]:
    """从连接器对应的供应商 API 发现可用模型。"""
    with SessionLocal() as session:
        connector = session.get(AIConnector, connector_id)
        if not connector:
            return {"success": False, "message": f"连接器 '{connector_id}' 不存在"}

        base_url = (connector.base_url or "").rstrip("/")
        api_key = connector.api_key

        if not base_url:
            return {"success": False, "message": "未配置 base_url，无法发现模型"}
        if not api_key:
            return {"success": False, "message": "未配置 api_key，无法发现模型"}

        models_url = f"{base_url}/models"

        try:
            async def _do_discover():
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        models_url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # OpenAI 兼容格式返回 {"data": [{"id": "model-name", ...}, ...]}
                        models_raw = data.get("data", [])
                        if isinstance(models_raw, list):
                            models = [
                                m.get("id", str(m))
                                if isinstance(m, dict)
                                else str(m)
                                for m in models_raw
                            ]
                            return {"success": True, "models": models, "total": len(models)}
                        return {"success": False, "message": f"无法解析模型列表格式: {str(data)[:200]}"}
                    elif resp.status_code == 404:
                        # 有些提供商不提供 /models 端点，试试 /v1/models
                        alt_url = f"{base_url}/v1/models"
                        resp2 = await client.get(
                            alt_url,
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                        )
                        if resp2.status_code == 200:
                            data2 = resp2.json()
                            models_raw2 = data2.get("data", [])
                            if isinstance(models_raw2, list):
                                models2 = [
                                    m.get("id", str(m))
                                    if isinstance(m, dict)
                                    else str(m)
                                    for m in models_raw2
                                ]
                                return {"success": True, "models": models2, "total": len(models2)}
                        return {"success": False, "message": f"模型发现端点不可用 (404): {resp.text[:200]}"}
                    else:
                        return {
                            "success": False,
                            "message": f"API 返回 {resp.status_code}: {resp.text[:200]}",
                        }

            return await _do_discover()

        except httpx.ConnectError as e:
            return {"success": False, "message": f"无法连接到 {base_url}: {str(e)}"}
        except Exception as e:
            logger.error(f"[ai_config_tools] discover_connector_models 异常: {e}")
            return {"success": False, "message": f"模型发现异常: {str(e)}"}
