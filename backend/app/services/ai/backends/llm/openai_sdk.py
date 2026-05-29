"""
YLCraft - OpenAI SDK LLM Backend

使用 OpenAI Python SDK 调用标准 OpenAI 兼容 API。
支持两种 SDK 模式：
- openai_sdk：Chat Completions（兼容所有 OpenAI 兼容平台）
- openai_sdk_responses：Responses API（仅 OpenAI 本家，2025 新接口）
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

import openai

from app.services.ai.types import (
    LLMCapability,
    LLMMessage,
    LLMGenerationResult,
)
from app.db.models.ai_connector import AIConnector

logger = logging.getLogger("ylcraft.openai_sdk_llm")


def _extract_text_content(content) -> str:
    """从多模态 content 中提取纯文本部分。"""
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    text_parts.append("[图片]")
                    logger.warning(
                        f"[OpenAISDK-LLM/Responses] 检测到图片内容，"
                        f"Responses API 对多模态支持有限，建议使用 Chat Completions 模式"
                    )
        return "\n".join(text_parts)
    
    return str(content)


class OpenAISDKLLMBackend:
    """
    基于 OpenAI Python SDK 的 LLM 后端。

    根据 api_format 自动选择：
    - openai_sdk → Chat Completions（兼容 DeepSeek、Groq 等）
    - openai_sdk_responses → Responses API（OpenAI 2025 新接口）
    """

    def __init__(self, connector: AIConnector):
        self.connector = connector
        self._name = connector.name
        self._model = connector.default_model
        self._api_format = getattr(connector, 'api_format', 'openai_sdk')
        self._provider = getattr(connector, 'provider', '')
        
        self._default_temperature = connector.temperature if connector.temperature is not None else 0.7
        self._default_max_tokens = connector.max_tokens or 4096

        self._client = openai.AsyncOpenAI(
            api_key=connector.api_key,
            base_url=connector.base_url or None,
            max_retries=2,
        )

        self._capabilities = {
            LLMCapability.TEXT_GENERATION,
            LLMCapability.STRUCTURED_OUTPUT,
        }

        logger.info(
            f"[OpenAISDK-LLM] 初始化: name={connector.name}, "
            f"model={connector.default_model}, "
            f"mode={'Responses' if self._api_format == 'openai_sdk_responses' else 'Chat Completions'}"
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set:
        return self._capabilities

    async def chat(self, messages: list[LLMMessage], **kwargs) -> LLMGenerationResult:
        """根据 api_format 自动选择 Chat Completions 或 Responses API。"""
        if self._api_format == 'openai_sdk_responses':
            return await self._chat_via_responses(messages, **kwargs)
        return await self._chat_via_completions(messages, **kwargs)

    async def _chat_via_completions(self, messages: list[LLMMessage], **kwargs) -> LLMGenerationResult:
        """Chat Completions 模式"""
        model = kwargs.get("model", self._model)
        temperature = kwargs.get("temperature", self._default_temperature)
        max_tokens = kwargs.get("max_tokens", self._default_max_tokens)

        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            choice = response.choices[0]
            usage = response.usage

            return LLMGenerationResult(
                success=True,
                content=choice.message.content or "",
                model=model,
                provider=self._provider,
                usage={
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
            )

        except openai.APIError as e:
            logger.error(f"[OpenAISDK-LLM/Completions] API错误: {e}")
            return LLMGenerationResult(success=False, error=f"OpenAI API 错误: {e}")
        except Exception as e:
            logger.error(f"[OpenAISDK-LLM/Completions] 未知错误: {e}")
            return LLMGenerationResult(success=False, error=str(e))

    async def _chat_via_responses(self, messages: list[LLMMessage], **kwargs) -> LLMGenerationResult:
        """Responses API 模式"""
        model = kwargs.get("model", self._model)

        try:
            user_input_parts = []
            instructions = ""

            for m in messages:
                content = m.content
                if m.role == "system":
                    instructions = _extract_text_content(content)
                else:
                    text = _extract_text_content(content)
                    if text:
                        user_input_parts.append(text)

            user_input = "\n".join(user_input_parts)

            params = {"model": model, "input": user_input.strip()}
            if instructions:
                params["instructions"] = instructions

            response = self._client.responses.create(**params)

            output_text = getattr(response, 'output_text', '')
            if not output_text:
                for item in getattr(response, 'output', []):
                    for content_item in getattr(item, 'content', []):
                        if hasattr(content_item, 'text'):
                            output_text += content_item.text

            usage = getattr(response, 'usage', None)

            return LLMGenerationResult(
                success=True,
                content=output_text or '',
                model=model,
                provider=self._provider,
                usage={
                    "prompt_tokens": usage.input_tokens if usage else 0,
                    "completion_tokens": usage.output_tokens if usage else 0,
                    "total_tokens": (usage.input_tokens + usage.output_tokens) if usage else 0,
                },
            )

        except openai.APIError as e:
            logger.error(f"[OpenAISDK-LLM/Responses] API错误: {e}")
            return LLMGenerationResult(success=False, error=f"OpenAI Responses API 错误: {e}")
        except Exception as e:
            logger.error(f"[OpenAISDK-LLM/Responses] 未知错误: {e}")
            return LLMGenerationResult(success=False, error=str(e))

    async def structured_output(self, schema: dict, prompt: str) -> dict:
        """结构化输出。"""
        if self._api_format == 'openai_sdk_responses':
            return await self._structured_via_responses(schema, prompt)
        return await self._structured_via_completions(schema, prompt)

    async def _structured_via_completions(self, schema: dict, prompt: str) -> dict:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是一个精确的 JSON 生成器。严格按照 JSON Schema 输出。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "structured_response", "schema": schema, "strict": True},
                },
                temperature=0.1,
            )
            content = response.choices[0].message.content
            return json.loads(content) if content else {}
        except json.JSONDecodeError as e:
            return {"error": f"JSON解析失败: {e}"}
        except openai.APIError as e:
            return {"error": str(e)}

    async def _structured_via_responses(self, schema: dict, prompt: str) -> dict:
        try:
            response = self._client.responses.create(
                model=self._model,
                instructions="你是一个精确的 JSON 生成器。只输出 JSON，不要其他内容。",
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "structured_response",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )
            output_text = getattr(response, 'output_text', '')
            return json.loads(output_text) if output_text else {}
        except json.JSONDecodeError:
            return {"error": "JSON解析失败"}
        except Exception as e:
            return {"error": str(e)}

    def get_available_models(self) -> List[str]:
        available = self.connector.get_available_models()
        if available:
            return available
        return [self._model] if self._model else []

    async def close(self):
        await self._client.close()
