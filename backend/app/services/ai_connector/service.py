"""
YLCraft — AI 连接器服务层

提供统一的 AI 连接管理，支持多提供商、多模型、成本控制
"""

from __future__ import annotations

import logging
import json
import mimetypes
import os
import time
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from jinja2 import Template
from sqlmodel import select
from sqlalchemy import String, cast

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.ai_connector import (
    AIConnector,
    AIConnectorCreate,
    AIConnectorUpdate,
    AIConnectorResponse,
    AIUsageLog,
    AIProvider,
)

logger = logging.getLogger("ylcraft.ai_connector")


def normalize_size_string(size_str: str) -> str:
    """
    标准化尺寸字符串：
    - 统一使用 'x' 作为分隔符
    - 兼容 'x' 和 '*' 分隔符
    示例: "1024*1024" -> "1024x1024"
    """
    if isinstance(size_str, str):
        return size_str.replace('*', 'x').replace('X', 'x')
    return size_str


def normalize_sizes_value(value) -> str:
    """
    标准化 supported_sizes 字段值：
    - 转换为 JSON 数组格式的字符串
    - 统一使用 'x' 作为尺寸分隔符
    输入: "1024x1024, 1024*1792" 或 ["1024x1024", "1024*1792"] 或 None
    输出: '["1024x1024", "1024x1792"]'
    """
    import json
    
    if value is None:
        return None
    
    # 如果已经是数组
    if isinstance(value, list):
        sizes_list = [normalize_size_string(str(s)) for s in value if s]
        return json.dumps(sizes_list)
    
    # 如果是字符串
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return value
        
        # 如果是逗号分隔的字符串
        if not value.startswith('['):
            sizes_list = [s.strip() for s in value.split(',') if s.strip()]
            # 标准化每个尺寸的分隔符
            sizes_list = [normalize_size_string(s) for s in sizes_list]
            return json.dumps(sizes_list)
        
        # 如果是 JSON 数组字符串
        try:
            sizes_list = json.loads(value)
            if isinstance(sizes_list, list):
                sizes_list = [normalize_size_string(str(s)) for s in sizes_list]
                return json.dumps(sizes_list)
        except json.JSONDecodeError:
            pass
    
    return value


def normalize_provider_type(value: Optional[str]) -> str:
    """Translate legacy connector type names before writing the DB enum."""
    normalized = str(value or "llm").strip().lower()
    return {
        "model3d": "3d",
        "model_3d": "3d",
        "image_to_3d": "3d",
        "image-to-3d": "3d",
    }.get(normalized, normalized)


def _parse_json_object(value) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


IMAGE_CAPABILITY_ORDER = ("text_to_image", "image_to_image")
IMAGE_CAPABILITY_ALIASES = {
    "text_to_image": "text_to_image",
    "text-to-image": "text_to_image",
    "txt2img": "text_to_image",
    "generation": "text_to_image",
    "generate": "text_to_image",
    "image_generation": "text_to_image",
    "image-to-image": "image_to_image",
    "image_to_image": "image_to_image",
    "img2img": "image_to_image",
    "edit": "image_to_image",
    "image_edit": "image_to_image",
}


def _parse_image_capability_values(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            value = parsed
        except Exception:
            value = [item.strip() for item in stripped.split(",")]
    if not isinstance(value, (list, tuple, set)):
        return []

    seen = set()
    for item in value:
        key = str(item or "").strip().lower().replace(" ", "_")
        normalized = IMAGE_CAPABILITY_ALIASES.get(key)
        if normalized:
            seen.add(normalized)
    return [cap for cap in IMAGE_CAPABILITY_ORDER if cap in seen]


def explicit_image_connector_capabilities(connector: AIConnector) -> list[str]:
    """Return user-configured image capabilities from connector default_params."""
    default_params = _parse_json_object(getattr(connector, "default_params", None))
    for key in ("image_capabilities", "capabilities"):
        capabilities = _parse_image_capability_values(default_params.get(key))
        if capabilities:
            return capabilities
    return []


def normalize_reference_image_config_values(
    *,
    provider_type: str = "",
    default_params=None,
    support_reference_image: bool = False,
    support_multiple_reference_images: bool = False,
    reference_image_field: Optional[str] = "image",
    reference_image_array_field: Optional[str] = None,
    support_vision_input: bool = False,
) -> dict:
    """Keep reference-image modes mutually exclusive.

    Supported shapes:
    - JSON array mode: reference_image_array_field is set, reference_image_field is empty.
    - Multipart mode: default_params.request_content_type=multipart, upload field is set.
      Multiple images are sent by repeating the same field, so
      support_multiple_reference_images is kept as declared by the connector.
    - Legacy field mode: reference_image_field is set, array field is empty.
    """
    params = _parse_json_object(default_params)
    field = (reference_image_field or "").strip()
    array_field = (reference_image_array_field or "").strip()
    content_type = str(params.get("request_content_type") or "").strip().lower()

    if not support_reference_image:
        support_multiple_reference_images = False
        field = ""
        array_field = ""
        params.pop("request_content_type", None)
        params.pop("multipart_image_field", None)
    elif content_type == "multipart":
        field = field or str(params.get("multipart_image_field") or "image")
        array_field = ""
        # multipart 通过重复提交同名字段表达多图，网关按提交顺序解释为图 1、图 2……，
        # 因此多图能力以连接器声明为准，不再强制关闭。
        params["request_content_type"] = "multipart"
        params["multipart_image_field"] = field
    elif array_field:
        field = ""
        support_multiple_reference_images = True
        params.pop("request_content_type", None)
        params.pop("multipart_image_field", None)
    else:
        field = field or "image"
        array_field = ""
        params.pop("request_content_type", None)
        params.pop("multipart_image_field", None)

    if provider_type == "image" and support_reference_image:
        support_vision_input = True

    return {
        "support_reference_image": bool(support_reference_image),
        "support_multiple_reference_images": bool(support_multiple_reference_images),
        "reference_image_field": field,
        "reference_image_array_field": array_field or None,
        "support_vision_input": bool(support_vision_input),
        "default_params": json.dumps(params, ensure_ascii=False) if params or default_params else None,
    }


def infer_image_connector_capabilities(connector: AIConnector) -> list[str]:
    """Resolve image connector capabilities.

    Explicit configuration in default_params.image_capabilities wins. Endpoint
    and mode inference only exists as a compatibility fallback for older data.
    """
    default_params = _parse_json_object(getattr(connector, "default_params", None))
    configured = explicit_image_connector_capabilities(connector)
    if configured:
        return configured

    endpoint = str(getattr(connector, "api_endpoint", "") or "").lower()
    mode = str(
        default_params.get("image_mode")
        or default_params.get("mode")
        or default_params.get("operation")
        or ""
    ).lower()
    template = str(getattr(connector, "request_template", "") or "").lower()
    supports_reference = bool(getattr(connector, "support_reference_image", False))

    explicit_edit = mode in {"edit", "image_edit", "image-to-image", "image_to_image", "img2img"}
    explicit_generation = mode in {"generation", "generate", "text-to-image", "text_to_image", "txt2img"}
    edit_endpoint = "/edits" in endpoint or endpoint.endswith("edits")
    generation_endpoint = "/generations" in endpoint or endpoint.endswith("generations")

    if (explicit_edit or edit_endpoint) and not explicit_generation and not generation_endpoint:
        return ["image_to_image"] if supports_reference else []

    capabilities = ["text_to_image"]
    if supports_reference or "reference_image" in template or "image_url" in template:
        capabilities.append("image_to_image")
    return capabilities


class AIConnectorService:
    """AI 连接器服务（异步版本）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # CRUD 操作
    # -------------------------------------------------------------------------

    async def list_all(self) -> list[AIConnector]:
        """列出所有 AI 连接"""
        stmt = select(AIConnector).order_by(AIConnector.priority, AIConnector.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_provider(self, provider: str) -> list[AIConnector]:
        """列出指定提供商的连接"""
        stmt = (
            select(AIConnector)
            .where(AIConnector.provider == provider)
            .order_by(AIConnector.priority, AIConnector.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_type(self, provider_type: str) -> list[AIConnector]:
        """列出指定类型的连接（llm/image/video/tts/stt）"""
        stmt = (
            select(AIConnector)
            .where(cast(AIConnector.provider_type, String) == provider_type)
            .order_by(AIConnector.priority, AIConnector.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_active_by_type(self, provider_type: str) -> list[AIConnector]:
        """列出指定类型的活跃连接"""
        stmt = (
            select(AIConnector)
            .where(
                cast(AIConnector.provider_type, String) == provider_type,
                AIConnector.is_active == True
            )
            .order_by(AIConnector.priority, AIConnector.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_active(self) -> list[AIConnector]:
        """列出所有活跃的连接"""
        stmt = (
            select(AIConnector)
            .where(AIConnector.is_active == True)
            .order_by(AIConnector.priority, AIConnector.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, conn_id: str) -> Optional[AIConnector]:
        """获取单个连接"""
        return await self.session.get(AIConnector, conn_id)

    async def get_default(self) -> Optional[AIConnector]:
        """获取默认连接"""
        stmt = select(AIConnector).where(AIConnector.is_default == True).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_provider(self, provider: str, active_only: bool = True) -> Optional[AIConnector]:
        """获取指定提供商的连接（按优先级）"""
        query = select(AIConnector).where(AIConnector.provider == provider)
        if active_only:
            query = query.where(AIConnector.is_active == True)
        query = query.order_by(AIConnector.priority).limit(1)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def create(self, data: AIConnectorCreate) -> AIConnector:
        """创建新连接"""
        provider_type = normalize_provider_type(data.provider_type)
        logger.info(f"[AIConnector] Creating connector: name={data.name}, provider={data.provider}, type={provider_type}")
        # 标准化 supported_sizes（兼容 x/* 分隔符）
        supported_sizes_value = normalize_sizes_value(data.supported_sizes) if data.supported_sizes else None
        reference_config = normalize_reference_image_config_values(
            provider_type=provider_type,
            default_params=data.default_params,
            support_reference_image=data.support_reference_image,
            support_multiple_reference_images=data.support_multiple_reference_images,
            reference_image_field=data.reference_image_field,
            reference_image_array_field=data.reference_image_array_field,
            support_vision_input=data.support_vision_input,
        )
        
        conn = AIConnector(
            id=str(uuid.uuid4()),
            provider=data.provider,
            name=data.name,
            api_key=data.api_key,
            base_url=data.base_url,
            api_endpoint=data.api_endpoint,
            organization_id=data.organization_id,
            project_id=data.project_id,
            default_model=data.default_model,
            max_tokens=data.max_tokens,
            temperature=data.temperature,
            monthly_budget=data.monthly_budget,
            daily_limit=data.daily_limit,
            price_per_call=data.price_per_call,
            is_active=data.is_active,
            is_default=data.is_default,
            priority=data.priority,
            description=data.description,
            # 扩展字段
            provider_type=provider_type,
            request_template=data.request_template,
            response_config=data.response_config,
            parameter_transforms=data.parameter_transforms,
            supported_sizes=supported_sizes_value,
            default_params=reference_config["default_params"],
            support_reference_image=reference_config["support_reference_image"],
            support_multiple_reference_images=reference_config["support_multiple_reference_images"],
            reference_image_field=reference_config["reference_image_field"],
            reference_image_array_field=reference_config["reference_image_array_field"],
            test_prompt=data.test_prompt,
            timeout=data.timeout,
            test_timeout=data.test_timeout,
            # 嵌入模型配置
            embedding_type=data.embedding_type,
            embedding_dimension=data.embedding_dimension,
            normalize_embeddings=data.normalize_embeddings,
            support_vision_input=reference_config["support_vision_input"],
            # API 格式
            api_format=data.api_format or "custom",
        )
        conn.set_available_models(data.available_models)

        # 如果设为默认，先取消其他默认
        if data.is_default:
            await self._clear_default()

        self.session.add(conn)
        await self.session.commit()
        await self.session.refresh(conn)
        logger.info(f"[AIConnector] Created: {conn.id} for {conn.provider}")
        return conn

    async def update(self, conn_id: str, data: AIConnectorUpdate) -> Optional[AIConnector]:
        """更新连接"""
        conn = await self.get(conn_id)
        if not conn:
            return None

        if data.name is not None:
            conn.name = data.name
        if data.api_key is not None:
            conn.api_key = data.api_key
        if data.base_url is not None:
            conn.base_url = data.base_url
        if data.api_endpoint is not None:
            conn.api_endpoint = data.api_endpoint
        if data.organization_id is not None:
            conn.organization_id = data.organization_id
        if data.project_id is not None:
            conn.project_id = data.project_id
        if data.default_model is not None:
            conn.default_model = data.default_model
        if data.available_models is not None:
            conn.set_available_models(data.available_models)
        if data.max_tokens is not None:
            conn.max_tokens = data.max_tokens
        if data.temperature is not None:
            conn.temperature = data.temperature
        if data.monthly_budget is not None:
            conn.monthly_budget = data.monthly_budget
        if data.daily_limit is not None:
            conn.daily_limit = data.daily_limit
        if data.price_per_call is not None:
            conn.price_per_call = data.price_per_call
        if data.is_active is not None:
            conn.is_active = data.is_active
        if data.is_default is not None:
            if data.is_default:
                await self._clear_default()
            conn.is_default = data.is_default
        if data.priority is not None:
            conn.priority = data.priority
        if data.description is not None:
            conn.description = data.description
        if data.provider is not None:
            conn.provider = data.provider
        # 扩展字段
        if data.provider_type is not None:
            conn.provider_type = normalize_provider_type(data.provider_type)
        if data.request_template is not None:
            conn.request_template = data.request_template
        if data.response_config is not None:
            conn.response_config = data.response_config
        if data.parameter_transforms is not None:
            conn.parameter_transforms = data.parameter_transforms
        if data.supported_sizes is not None:
            # 标准化 supported_sizes（兼容 x/* 分隔符）
            conn.supported_sizes = normalize_sizes_value(data.supported_sizes)
        if data.default_params is not None:
            conn.default_params = data.default_params
        if data.support_reference_image is not None:
            conn.support_reference_image = data.support_reference_image
        if data.support_multiple_reference_images is not None:
            conn.support_multiple_reference_images = data.support_multiple_reference_images
        if data.reference_image_field is not None:
            conn.reference_image_field = data.reference_image_field
        if data.reference_image_array_field is not None:
            conn.reference_image_array_field = data.reference_image_array_field
        if data.test_prompt is not None:
            conn.test_prompt = data.test_prompt
        # 超时配置
        if data.timeout is not None:
            conn.timeout = data.timeout
        if data.test_timeout is not None:
            conn.test_timeout = data.test_timeout
        # 嵌入模型配置
        if data.embedding_type is not None:
            conn.embedding_type = data.embedding_type
        if data.embedding_dimension is not None:
            conn.embedding_dimension = data.embedding_dimension
        if data.normalize_embeddings is not None:
            conn.normalize_embeddings = data.normalize_embeddings
        if data.support_vision_input is not None:
            conn.support_vision_input = data.support_vision_input
        # API 格式
        if data.api_format is not None:
            conn.api_format = data.api_format

        reference_config = normalize_reference_image_config_values(
            provider_type=conn.provider_type,
            default_params=conn.default_params,
            support_reference_image=conn.support_reference_image,
            support_multiple_reference_images=conn.support_multiple_reference_images,
            reference_image_field=conn.reference_image_field,
            reference_image_array_field=conn.reference_image_array_field,
            support_vision_input=conn.support_vision_input,
        )
        conn.default_params = reference_config["default_params"]
        conn.support_reference_image = reference_config["support_reference_image"]
        conn.support_multiple_reference_images = reference_config["support_multiple_reference_images"]
        conn.reference_image_field = reference_config["reference_image_field"]
        conn.reference_image_array_field = reference_config["reference_image_array_field"]
        conn.support_vision_input = reference_config["support_vision_input"]

        conn.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.session.add(conn)
        await self.session.commit()
        await self.session.refresh(conn)
        logger.info(f"[AIConnector] Updated: {conn.id}")
        return conn

    async def delete(self, conn_id: str) -> bool:
        """删除连接"""
        conn = await self.get(conn_id)
        if not conn:
            return False
        await self.session.delete(conn)
        await self.session.commit()
        logger.info(f"[AIConnector] Deleted: {conn_id}")
        return True

    # -------------------------------------------------------------------------
    # 测试与验证
    # -------------------------------------------------------------------------

    async def test_connection(
        self,
        conn_id: str,
        custom_body: Optional[dict] = None,
        test_options: Optional[dict] = None,
    ) -> dict:
        """
        测试连接有效性
        返回 {"success": bool, "message": str}
        """
        conn = await self.get(conn_id)
        if not conn:
            return {"success": False, "message": "连接不存在"}

        if not conn.api_key:
            return {"success": False, "message": "API Key 为空"}

        if conn.base_url:
            request = {"method": "GET", "url": conn.base_url, "json": None}
            headers = {}
            try:
                provider_type = conn.provider_type.value if hasattr(conn.provider_type, "value") else str(conn.provider_type or "llm")
                api_format = getattr(conn, 'api_format', 'custom')
                request = self._build_test_request(
                    conn.base_url,
                    conn.api_endpoint,
                    provider_type,
                    conn.default_model,
                    conn.test_prompt,
                    api_format,
                    conn=conn,
                    test_options=test_options,
                )
                
                # 使用自定义请求体（如果提供了）
                if custom_body:
                    request["json"] = custom_body
                
                headers = {"Authorization": f"Bearer {conn.api_key}"}
                if not request.get("files"):
                    headers["Content-Type"] = "application/json"
                response_config = self._parse_json_object(conn.response_config)
                async_config = response_config.get("async_config") if isinstance(response_config, dict) else None
                if provider_type != "image":
                    async_config = None
                if isinstance(async_config, dict):
                    headers.update(async_config.get("request_headers") or {})

                started_at = time.perf_counter()

                # 自动检测系统代理（支持 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY 环境变量）
                httpx_kwargs = {"timeout": conn.test_timeout}
                proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY") or os.environ.get("http_proxy") or os.environ.get("https_proxy")
                if proxy_url:
                    httpx_kwargs["proxy"] = proxy_url

                async with httpx.AsyncClient(**httpx_kwargs) as client:
                    response = await client.request(
                        method=request["method"],
                        url=request["url"],
                        headers=headers,
                        json=request.get("json"),
                        data=request.get("data"),
                        files=request.get("files"),
                    )
                    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                    debug_info = self._build_debug_info(request, headers, response, latency_ms)

                    if response.status_code in (200, 201, 202) and isinstance(async_config, dict) and async_config:
                        async_test = await self._test_async_image_poll(
                            conn=conn,
                            client=client,
                            create_response=response,
                            async_config=async_config,
                        )
                        debug_info["async_poll"] = async_test.get("debug")
                        if async_test.get("task_id"):
                            debug_info["async_task_id"] = async_test.get("task_id")
                        if not async_test.get("success"):
                            return {
                                "success": False,
                                "message": async_test.get("message") or "异步轮询测试失败",
                                "debug": debug_info,
                            }
                        return {
                            "success": True,
                            "message": async_test.get("message") or "连接正常，异步任务创建并轮询成功",
                            "debug": debug_info,
                        }

                if response.status_code in (200, 201, 202):
                    return {
                        "success": True,
                        "message": "连接正常，可访问 API",
                        "debug": debug_info,
                    }

                error_message = self._extract_error_message(response)
                if error_message:
                    return {
                        "success": False,
                        "message": error_message,
                        "debug": debug_info,
                    }
                return {
                    "success": False,
                    "message": f"API 返回错误: {response.status_code}",
                    "debug": debug_info,
                }
            except Exception as e:
                err_str = str(e)
                # DNS 解析失败 / 网络不可达，给出更具体的提示
                hint = ""
                if "getaddrinfo" in err_str.lower() or "name or service not known" in err_str.lower():
                    hint = "（DNS 解析失败，请检查服务器是否能访问该 API 域名，或是否需要配置代理）"
                elif "connection refused" in err_str.lower() or "connection reset" in err_str.lower():
                    hint = "（服务器拒绝连接，请检查 Base URL 是否正确，或目标服务是否正常运行）"
                elif any(kw in err_str.lower() for kw in ["timeout", "timed out", "connection timed"]):
                    hint = "（连接超时，请检查网络连通性或是否需要配置代理）"

                failed_debug = {
                    "request": {
                        "method": request.get("method"),
                        "url": request.get("url"),
                        "headers": self._mask_headers(headers),
                        "body": request.get("json"),
                    },
                    "response": {
                        "status_code": None,
                        "headers": {},
                        "body": None,
                    },
                    "latency_ms": None,
                    "exception": str(e),
                }
                return {
                    "success": False,
                    "message": f"连接测试失败: {err_str}{hint}",
                    "debug": failed_debug,
                }

        return {"success": True, "message": "API Key 格式正确"}

    async def _test_async_image_poll(
        self,
        conn: AIConnector,
        client: httpx.AsyncClient,
        create_response: httpx.Response,
        async_config: dict,
    ) -> dict:
        """按通用 async_config 对图片异步任务做一次轮询测试。"""
        try:
            create_data = create_response.json()
        except Exception:
            return {"success": False, "message": "异步响应不是有效 JSON"}

        task_id_path = async_config.get("task_id_path")
        if not task_id_path:
            return {"success": False, "message": "未配置 async_config.task_id_path"}

        task_id = self._extract_jsonpath_value(create_data, task_id_path)
        if not task_id:
            return {"success": False, "message": f"未能从创建响应提取 task_id: {task_id_path}"}

        poll_endpoint_template = async_config.get("poll_endpoint")
        if not poll_endpoint_template:
            return {"success": False, "message": "未配置 async_config.poll_endpoint", "task_id": task_id}

        poll_endpoint = str(poll_endpoint_template).replace("{task_id}", str(task_id))
        if poll_endpoint.startswith("http://") or poll_endpoint.startswith("https://"):
            poll_url = poll_endpoint
        else:
            poll_url = f"{(conn.base_url or '').rstrip('/')}/{poll_endpoint.lstrip('/')}"

        poll_headers = {
            "Authorization": f"Bearer {conn.api_key}",
            "Content-Type": "application/json",
            **(async_config.get("poll_headers") or {}),
        }
        poll_method = str(async_config.get("poll_method") or "GET").upper()
        poll_request = {
            "method": poll_method,
            "url": poll_url,
            "json": {} if poll_method == "POST" else None,
        }

        if poll_method not in {"GET", "POST"}:
            return {
                "success": False,
                "message": f"不支持的异步轮询方法: {poll_method}",
                "task_id": task_id,
            }

        status_path = async_config.get("status_path")
        done_value = str(async_config.get("done_value", "SUCCEED")).upper()
        failed_value = str(async_config.get("failed_value", "FAILED")).upper()
        images_path = async_config.get("images_path")
        error_path = async_config.get("error_path")
        poll_interval = max(float(async_config.get("poll_interval", 5) or 5), 0.2)
        max_wait = max(float(async_config.get("max_wait", conn.test_timeout or 20) or 20), 1.0)
        deadline = time.monotonic() + max_wait
        attempts = 0
        last_debug = None
        last_status = None

        while True:
            attempts += 1
            started_at = time.perf_counter()
            if poll_method == "GET":
                poll_response = await client.get(poll_url, headers=poll_headers)
            else:
                poll_response = await client.post(poll_url, headers=poll_headers, json={})

            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            debug = self._build_debug_info(poll_request, poll_headers, poll_response, latency_ms)
            debug["attempt"] = attempts
            debug["max_wait"] = max_wait
            last_debug = debug

            if poll_response.status_code not in (200, 201, 202):
                return {
                    "success": False,
                    "message": f"异步轮询失败: HTTP {poll_response.status_code}",
                    "task_id": task_id,
                    "debug": debug,
                }

            try:
                poll_data = poll_response.json()
            except Exception:
                return {
                    "success": False,
                    "message": "异步轮询响应不是有效 JSON",
                    "task_id": task_id,
                    "debug": debug,
                }

            status = self._extract_jsonpath_value(poll_data, status_path) if status_path else None
            last_status = status
            normalized_status = str(status).upper() if status is not None else ""
            if normalized_status == done_value:
                image_urls = self._extract_jsonpath_values(poll_data, images_path) if images_path else []
                message = f"连接正常，异步图片任务已完成（轮询 {attempts} 次）"
                if not image_urls:
                    message += "，但未按配置提取到图片，请检查 images_path"
                return {
                    "success": True,
                    "message": message,
                    "task_id": task_id,
                    "status": status,
                    "image_urls": image_urls,
                    "debug": debug,
                }

            if normalized_status == failed_value:
                error_message = self._extract_jsonpath_value(poll_data, error_path) if error_path else None
                return {
                    "success": False,
                    "message": error_message or f"异步图片任务失败（状态: {status}）",
                    "task_id": task_id,
                    "status": status,
                    "debug": debug,
                }

            if time.monotonic() + poll_interval > deadline:
                return {
                    "success": True,
                    "message": f"连接正常，异步任务已创建并可轮询，但测试等待超时仍未完成（状态: {last_status or 'unknown'}，轮询 {attempts} 次）。可到生图页正式生成后继续等待结果。",
                    "task_id": task_id,
                    "status": last_status,
                    "debug": last_debug,
                }

            await asyncio.sleep(poll_interval)

    def _build_test_request(
        self,
        base_url: str,
        api_endpoint: Optional[str],
        provider_type: str,
        model: str,
        test_prompt: Optional[str] = None,
        api_format: str = "custom",
        conn: Optional[AIConnector] = None,
        test_options: Optional[dict] = None,
    ) -> dict:
        """
        构造最小测试请求。

        参考 yiliu：支持 base_url + api_endpoint 分离配置。
        优先级：
        1. 如果有 api_endpoint，使用 base_url + api_endpoint
        2. SDK 模式下，base_url 视为根地址，强制追加默认端点
        3. 否则检查 base_url 是否已经包含路径，如果是，直接使用
        4. 否则使用默认路径
        """
        normalized_base = (base_url or "").rstrip("/")
        provider_type = (provider_type or "llm").lower()
        api_format = (api_format or "custom").lower()

        # 检查 base_url 是否已经包含路径（超过域名层级）
        def base_url_has_path() -> bool:
            # 去掉协议部分
            url_without_proto = normalized_base
            if "://" in url_without_proto:
                url_without_proto = url_without_proto.split("://", 1)[1]
            # 检查是否有超过一个 "/"
            return "/" in url_without_proto and url_without_proto.count("/") > 0

        has_path = base_url_has_path()

        def build_url(default_endpoint: str) -> str:
            # 如果有 api_endpoint，优先使用
            if api_endpoint:
                return f"{normalized_base}{api_endpoint}"
            # SDK 模式下，base_url 视为根地址，强制追加默认端点
            if api_format.startswith("openai_sdk"):
                if normalized_base.endswith("/v1"):
                    return f"{normalized_base}{default_endpoint}"
                return f"{normalized_base}/v1{default_endpoint}"
            # 如果 base_url 已经包含路径，直接使用
            if has_path:
                return normalized_base
            # 否则使用默认端点
            if normalized_base.endswith(default_endpoint):
                return normalized_base
            if normalized_base.endswith("/v1"):
                return f"{normalized_base}{default_endpoint}"
            return f"{normalized_base}/{default_endpoint.lstrip('/')}"

        if provider_type == "image":
            return self._build_image_test_request(
                build_url=build_url,
                model=model,
                test_prompt=test_prompt,
                api_format=api_format,
                conn=conn,
                test_options=test_options,
            )

        if provider_type == "llm":
            default_prompt = "Reply with ok."
            return {
                "method": "POST",
                "url": build_url("/chat/completions"),
                "json": {
                    "model": model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": test_prompt or default_prompt},
                    ],
                    "max_tokens": 8,
                    "temperature": 0,
                },
            }

        if provider_type == "embedding":
            return {
                "method": "POST",
                "url": build_url("/embeddings"),
                "json": {
                    "model": model or "text-embedding-3-small",
                    "input": test_prompt or "connection test",
                },
            }

        # video / tts / stt 先做无副作用的可达性探测，避免真的触发生成任务
        return {
            "method": "GET",
            "url": normalized_base,
        }

    def _parse_json_object(self, value) -> dict:
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _build_image_test_request(
        self,
        build_url,
        model: str,
        test_prompt: Optional[str],
        api_format: str,
        conn: Optional[AIConnector],
        test_options: Optional[dict],
    ) -> dict:
        default_prompt = "连接测试图片"
        default_params = self._parse_json_object(getattr(conn, "default_params", None))
        test_options = test_options or {}
        image_input = (
            test_options.get("image_url")
            or test_options.get("image_path")
            or test_options.get("source_image")
            or default_params.get("test_image_url")
            or default_params.get("test_image_path")
            or ""
        )
        endpoint_hint = str(getattr(conn, "api_endpoint", "") or "").lower()
        explicit_mode = str(
            test_options.get("image_mode")
            or default_params.get("image_mode")
            or default_params.get("mode")
            or ""
        ).lower()
        is_edit_request = (
            explicit_mode in {"edit", "image_edit", "image-to-image", "image_to_image"}
            or "edits" in endpoint_hint
            or bool(image_input)
        )
        default_endpoint = "/images/edits" if is_edit_request else "/images/generations"
        params = {
            "model": model or "gpt-image-1",
            "prompt": test_prompt or default_prompt,
            "size": "1024x1024",
            "n": 1,
            **default_params,
        }
        if test_options.get("response_format"):
            params["response_format"] = test_options["response_format"]
        if is_edit_request:
            params.setdefault("response_format", "b64_json")
            if image_input:
                params["image"] = image_input
                params["images"] = [{"image_url": image_input}]

        content_type = str(
            test_options.get("request_content_type")
            or default_params.get("request_content_type")
            or ""
        ).lower()
        is_local_image = self._looks_like_local_file(str(image_input))
        is_remote_image = str(image_input).startswith(("http://", "https://"))
        use_multipart = bool(
            image_input
            and is_local_image
            and (content_type in {"", "multipart"} or not is_remote_image)
        )

        if api_format == "custom" and conn and conn.request_template:
            rendered = self._render_test_template(conn.request_template, params)
            if use_multipart:
                return self._build_multipart_image_test_request(
                    url=build_url(default_endpoint),
                    params={**params, **rendered},
                    image_input=str(image_input),
                    image_field=str(default_params.get("multipart_image_field") or "image"),
                )
            return {"method": "POST", "url": build_url(default_endpoint), "json": rendered}

        if use_multipart:
            return self._build_multipart_image_test_request(
                url=build_url(default_endpoint),
                params=params,
                image_input=str(image_input),
                image_field=str(default_params.get("multipart_image_field") or "image"),
            )

        json_body = {
            key: value
            for key, value in params.items()
            if value is not None
            and key not in {"image", "request_content_type", "image_mode", "mode"}
        }
        if is_edit_request and image_input:
            json_body["images"] = [{"image_url": image_input}]
        return {"method": "POST", "url": build_url(default_endpoint), "json": json_body}

    def _looks_like_local_file(self, value: str) -> bool:
        if not value or value.startswith(("http://", "https://", "data:")):
            return False
        try:
            return Path(value).expanduser().exists()
        except Exception:
            return False

    def _build_multipart_image_test_request(
        self,
        url: str,
        params: dict,
        image_input: str,
        image_field: str = "image",
    ) -> dict:
        image_path = Path(image_input).expanduser()
        if not image_path.exists():
            raise ValueError(f"Multipart 测试图片不存在: {image_input}")
        mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
        data = {
            key: str(value)
            for key, value in params.items()
            if key
            not in {
                "image",
                "images",
                "request_content_type",
                "image_mode",
                "mode",
                "test_image_url",
                "test_image_path",
                "multipart_image_field",
            }
            and value is not None
        }
        return {
            "method": "POST",
            "url": url,
            "data": data,
            "files": {image_field: (image_path.name, image_path.read_bytes(), mime_type)},
        }

    def _render_test_template(self, request_template: str, params: dict) -> dict:
        template_params = dict(params)
        for key, value in params.items():
            template_params[f"{key}_json"] = json.dumps(value, ensure_ascii=False)
            if isinstance(value, str):
                template_params[f"{key}_json_str"] = json.dumps(value or "", ensure_ascii=False)[1:-1]
        rendered = Template(request_template).render(**template_params)
        data = json.loads(rendered)
        if not isinstance(data, dict):
            raise ValueError("Request 模板必须渲染为 JSON 对象")
        return data

    def _extract_jsonpath_value(self, data: dict, path: Optional[str]):
        if not path:
            return None
        try:
            from jsonpath_ng import parse as jsonpath_parse

            matches = jsonpath_parse(path).find(data)
            return matches[0].value if matches else None
        except Exception as e:
            logger.warning("JSONPath 提取失败: %s, 错误: %s", path, e)
            return None

    def _extract_jsonpath_values(self, data: dict, path: Optional[str]) -> list:
        if not path:
            return []
        try:
            from jsonpath_ng import parse as jsonpath_parse

            values = []
            for match in jsonpath_parse(path).find(data):
                value = match.value
                if isinstance(value, list):
                    values.extend(value)
                elif value is not None:
                    values.append(value)
            return values
        except Exception as e:
            logger.warning("JSONPath 列表提取失败: %s, 错误: %s", path, e)
            return []

    def _extract_error_message(self, response) -> Optional[str]:
        """尽量从响应中提取清晰的错误信息。"""
        try:
            data = response.json()
        except Exception:
            text = response.text.strip()
            return text[:200] if text else None

        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                return error.get("message") or error.get("detail")
            if isinstance(error, str):
                return error
            return data.get("message") or data.get("detail")
        return None

    def _build_debug_info(self, request: dict, headers: dict, response: httpx.Response, latency_ms: float) -> dict:
        """构造前端可展示的请求/响应调试信息。"""
        try:
            response_body = response.json()
        except Exception:
            response_body = response.text[:4000] if response.text else None

        return {
            "request": {
                "method": request.get("method"),
                "url": request.get("url"),
                "headers": self._mask_headers(headers),
                "body": request.get("json"),
            },
            "response": {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
            },
            "latency_ms": latency_ms,
        }

    def _mask_headers(self, headers: dict) -> dict:
        """隐藏敏感请求头。"""
        masked = dict(headers or {})
        auth = masked.get("Authorization")
        if isinstance(auth, str) and auth.startswith("Bearer "):
            masked["Authorization"] = "Bearer ***"
        return masked

    # -------------------------------------------------------------------------
    # 使用记录
    # -------------------------------------------------------------------------

    async def log_usage(
        self,
        connector_id: str,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float = 0.0,
        latency_ms: int = 0,
        status: str = "success",
        error_message: Optional[str] = None,
    ):
        """记录使用日志"""
        log = AIUsageLog(
            id=str(uuid.uuid4()),
            connector_id=connector_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost=cost,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
        )
        self.session.add(log)

        # 更新连接统计
        conn = await self.get(connector_id)
        if conn:
            conn.update_usage(prompt_tokens + completion_tokens, cost)

        await self.session.commit()

    async def get_usage_stats(self, connector_id: str, days: int = 30) -> dict:
        """获取使用统计"""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = select(AIUsageLog).where(
            AIUsageLog.connector_id == connector_id,
            AIUsageLog.created_at >= cutoff,
        )
        result = await self.session.execute(stmt)
        logs = result.scalars().all()

        total_tokens = sum(log.total_tokens for log in logs)
        total_cost = sum(log.cost for log in logs)
        total_requests = len(logs)
        avg_latency = sum(log.latency_ms for log in logs) / total_requests if total_requests > 0 else 0

        return {
            "period_days": days,
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 4),
            "avg_latency_ms": round(avg_latency, 2),
        }

    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------

    async def _clear_default(self):
        """清除所有连接的默认标记"""
        stmt = select(AIConnector).where(AIConnector.is_default == True)
        result = await self.session.execute(stmt)
        for conn in result.scalars().all():
            conn.is_default = False
            self.session.add(conn)
        await self.session.commit()
