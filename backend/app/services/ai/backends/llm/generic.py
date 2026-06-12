"""
YLCraft - Generic LLM Backend

配置驱动的 LLM 后端，支持所有 OpenAI 兼容 API。
通过数据库中的配置驱动，无需为每个 Provider 写代码。
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Dict, List
from urllib.parse import urlparse

import httpx
from jinja2 import Template

from app.services.ai.types import (
    LLMBackend,
    LLMMessage,
    LLMGenerationResult,
)
from app.db.models.ai_connector import AIConnector

logger = logging.getLogger("ylcraft.generic_llm_backend")


class GenericLLMBackend(LLMBackend):
    """
    通用 LLM 后端
    
    通过数据库配置驱动，支持任意 OpenAI 兼容的 LLM API
    无需为每个 Provider 写代码，只需在数据库中配置
    """
    
    def __init__(self, connector: AIConnector, session):
        """
        初始化通用 LLM 后端
        
        Args:
            connector: AIConnector 数据库记录
            session: SQLAlchemy session
        """
        super().__init__(name=connector.name, model=connector.default_model)
        
        self.connector = connector
        self.session = session
        
        self._default_temperature = connector.temperature if connector.temperature is not None else 0.7
        self._default_max_tokens = connector.max_tokens or 4096
        
        headers = {}
        if connector.api_key:
            headers["Authorization"] = f"Bearer {connector.api_key}"
        headers["Content-Type"] = "application/json"
        self._chat_url = _build_chat_url(connector.base_url or "", connector.api_endpoint)
        
        self.client = httpx.AsyncClient(
            headers=headers,
            timeout=120.0,
        )
        
        logger.info(f"[GenericLLM] 初始化 Backend: {connector.name}")
    
    async def chat(self, messages: List[LLMMessage], **kwargs) -> LLMGenerationResult:
        """生成 LLM 响应"""
        try:
            model = kwargs.get("model", self.model)
            
            request_body = {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": kwargs.get("temperature", self._default_temperature),
                "max_tokens": kwargs.get("max_tokens", self._default_max_tokens),
            }
            
            logger.info("[GenericLLM] Sending request to %s, model: %s", self._chat_url, model)
            
            response = await self.client.post(self._chat_url, json=request_body)
            response.raise_for_status()
            
            data = response.json()
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = (
                message.get("content")
                or message.get("reasoning_content")
                or choice.get("text")
                or data.get("output_text")
                or data.get("content")
                or ""
            )
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            usage = data.get("usage", {})
            
            return LLMGenerationResult(
                success=True,
                content=content,
                model=model,
                provider=self.connector.provider,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            )
            
        except Exception as e:
            logger.error(f"[GenericLLM] 生成失败: {e}", exc_info=True)
            return LLMGenerationResult(
                success=False,
                error=str(e),
                content="",
            )

    async def structured_output(self, schema: dict, prompt: str) -> dict:
        """结构化输出"""
        messages = [LLMMessage(role="user", content=prompt)]
        result = await self.chat(messages)
        if not result.success:
            raise ValueError(result.error)
        try:
            return result.content
        except Exception:
            return {"raw": result.content}
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        available = self.connector.get_available_models()
        if available:
            return available
        return [self.model] if self.model else []
    
    def estimate_cost(self, messages: List[LLMMessage], **kwargs) -> float:
        """估算成本（子类可重写）"""
        return 0.0
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()


def _build_chat_url(base_url: str, api_endpoint: Optional[str] = None) -> str:
    """Build an OpenAI-compatible chat URL without duplicating endpoint paths."""
    base = (base_url or "").strip().rstrip("/")
    endpoint = (api_endpoint or "/chat/completions").strip() or "/chat/completions"
    endpoint_path = "/" + endpoint.lstrip("/")
    if not base:
        return endpoint_path

    base_path = urlparse(base).path.rstrip("/")
    normalized_endpoint = endpoint_path.rstrip("/")
    if normalized_endpoint and base_path.lower().endswith(normalized_endpoint.lower()):
        return base
    if base_path and normalized_endpoint.lower().startswith((base_path + "/").lower()):
        normalized_endpoint = normalized_endpoint[len(base_path):]
    return base + normalized_endpoint
