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
from jsonpath_ng import parse as jsonpath_parse

from app.services.ai.types import (
    LLMBackend,
    LLMCapability,
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
        self.connector = connector
        self.session = session
        self._name = connector.name
        self._model = connector.default_model
        self._capabilities = {
            LLMCapability.TEXT_GENERATION,
            LLMCapability.STRUCTURED_OUTPUT,
        }
        
        self._default_temperature = connector.temperature if connector.temperature is not None else 0.7
        self._default_max_tokens = connector.max_tokens or 4096
        self.response_config = self._parse_json_object(connector.response_config)
        
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

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set:
        return self._capabilities
    
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
            request_body.update(self._parse_json_object(getattr(self.connector, "default_params", None)))
            tools = kwargs.get("tools")
            if tools:
                request_body[self.response_config.get("tools_request_field", "tools")] = tools
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                request_body[self.response_config.get("tool_choice_request_field", "tool_choice")] = tool_choice
            
            logger.info("[GenericLLM] Sending request to %s, model: %s", self._chat_url, model)
            
            response = await self.client.post(self._chat_url, json=request_body)
            response.raise_for_status()
            
            data = response.json()
            content = self._extract_content(data)
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            tool_calls = self._extract_tool_calls(data)
            usage = data.get("usage", {})
            
            return LLMGenerationResult(
                success=True,
                content=content,
                tool_calls=tool_calls,
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

    def _extract_content(self, data: dict) -> str:
        content_path = self.response_config.get("content_path")
        if content_path:
            value = self._extract_jsonpath_value(data, content_path)
            return value if value is not None else ""

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return (
            message.get("content")
            or message.get("reasoning_content")
            or choice.get("text")
            or data.get("output_text")
            or data.get("content")
            or ""
        )

    def _extract_tool_calls(self, data: dict) -> list[dict]:
        finish_reason_path = self.response_config.get("finish_reason_path")
        if finish_reason_path:
            finish_reason = self._extract_jsonpath_value(data, finish_reason_path)
            tool_finish_reasons = self.response_config.get("tool_finish_reasons") or ["tool_calls", "tool_call"]
            if finish_reason not in tool_finish_reasons:
                return []

        tool_calls_path = self.response_config.get("tool_calls_path", "$.choices[0].message.tool_calls[*]")
        raw_calls = self._extract_jsonpath_values(data, tool_calls_path)
        if not raw_calls and not self.response_config.get("tool_calls_path"):
            choice = (data.get("choices") or [{}])[0]
            raw_calls = (choice.get("message") or {}).get("tool_calls") or []

        tool_name_path = self.response_config.get("tool_name_path", "$.function.name")
        tool_arguments_path = self.response_config.get("tool_arguments_path", "$.function.arguments")
        tool_id_path = self.response_config.get("tool_id_path", "$.id")
        tool_type_path = self.response_config.get("tool_type_path", "$.type")

        tool_calls = []
        for index, raw_call in enumerate(raw_calls or []):
            if not isinstance(raw_call, dict):
                continue
            name = self._extract_jsonpath_value(raw_call, tool_name_path)
            arguments = self._extract_jsonpath_value(raw_call, tool_arguments_path)
            call_id = self._extract_jsonpath_value(raw_call, tool_id_path) or f"call_{index + 1}"
            call_type = self._extract_jsonpath_value(raw_call, tool_type_path) or "function"
            if not name:
                continue
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, ensure_ascii=False)
            elif arguments is None:
                arguments = "{}"
            tool_calls.append(
                {
                    "id": str(call_id),
                    "type": str(call_type),
                    "function": {
                        "name": str(name),
                        "arguments": str(arguments),
                    },
                }
            )
        return tool_calls

    @staticmethod
    def _parse_json_object(raw: str | None) -> dict:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("[GenericLLM] JSON 配置解析失败: %s", exc)
            return {}

    @staticmethod
    def _extract_jsonpath_value(data: dict, path: str | None):
        values = GenericLLMBackend._extract_jsonpath_values(data, path)
        return values[0] if values else None

    @staticmethod
    def _extract_jsonpath_values(data: dict, path: str | None) -> list:
        if not path:
            return []
        try:
            return [match.value for match in jsonpath_parse(path).find(data)]
        except Exception as exc:
            logger.warning("[GenericLLM] JSONPath 提取失败: %s, 错误: %s", path, exc)
            return []


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
