"""
YLCraft — AI 连接器服务层

提供统一的 AI 连接管理，支持多提供商、多模型、成本控制
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlmodel import select

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
            .where(AIConnector.provider_type == provider_type)
            .order_by(AIConnector.priority, AIConnector.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_active_by_type(self, provider_type: str) -> list[AIConnector]:
        """列出指定类型的活跃连接"""
        stmt = (
            select(AIConnector)
            .where(
                AIConnector.provider_type == provider_type,
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
        logger.info(f"[AIConnector] Creating connector: name={data.name}, provider={data.provider}, type={data.provider_type}")
        # 标准化 supported_sizes（兼容 x/* 分隔符）
        supported_sizes_value = normalize_sizes_value(data.supported_sizes) if data.supported_sizes else None
        
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
            provider_type=data.provider_type,
            request_template=data.request_template,
            response_config=data.response_config,
            parameter_transforms=data.parameter_transforms,
            supported_sizes=supported_sizes_value,
            default_params=data.default_params,
            support_reference_image=data.support_reference_image,
            support_multiple_reference_images=data.support_multiple_reference_images,
            reference_image_field=data.reference_image_field,
            reference_image_array_field=data.reference_image_array_field,
            test_prompt=data.test_prompt,
            # 嵌入模型配置
            embedding_type=data.embedding_type,
            embedding_dimension=data.embedding_dimension,
            normalize_embeddings=data.normalize_embeddings,
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
        # 扩展字段
        if data.provider_type is not None:
            conn.provider_type = data.provider_type
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
        # 嵌入模型配置
        if data.embedding_type is not None:
            conn.embedding_type = data.embedding_type
        if data.embedding_dimension is not None:
            conn.embedding_dimension = data.embedding_dimension
        if data.normalize_embeddings is not None:
            conn.normalize_embeddings = data.normalize_embeddings
        # API 格式
        if data.api_format is not None:
            conn.api_format = data.api_format

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

    async def test_connection(self, conn_id: str, custom_body: Optional[dict] = None) -> dict:
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
            try:
                provider_type = conn.provider_type.value if hasattr(conn.provider_type, "value") else str(conn.provider_type or "llm")
                api_format = getattr(conn, 'api_format', 'custom')
                request = self._build_test_request(conn.base_url, conn.api_endpoint, provider_type, conn.default_model, conn.test_prompt, api_format)
                
                # 使用自定义请求体（如果提供了）
                if custom_body:
                    request["json"] = custom_body
                
                headers = {
                    "Authorization": f"Bearer {conn.api_key}",
                    "Content-Type": "application/json",
                }
                started_at = time.perf_counter()

                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.request(
                        method=request["method"],
                        url=request["url"],
                        headers=headers,
                        json=request.get("json"),
                    )
                latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                debug_info = self._build_debug_info(request, headers, response, latency_ms)

                if response.status_code == 200:
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
                    "message": f"连接测试失败: {str(e)}",
                    "debug": failed_debug,
                }

        return {"success": True, "message": "API Key 格式正确"}

    def _build_test_request(self, base_url: str, api_endpoint: Optional[str], provider_type: str, model: str, test_prompt: Optional[str] = None, api_format: str = "custom") -> dict:
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
            default_prompt = "连接测试图片"
            return {
                "method": "POST",
                "url": build_url("/images/generations"),
                "json": {
                    "model": model or "gpt-image-1",
                    "prompt": test_prompt or default_prompt,
                    "size": "1024x1024",
                    "n": 1,
                },
            }

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
            token = auth[len("Bearer "):]
            if len(token) > 12:
                token = f"{token[:6]}...{token[-4:]}"
            else:
                token = "***"
            masked["Authorization"] = f"Bearer {token}"
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
