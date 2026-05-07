"""
YLCraft — Doubao LLM Backend

实现豆包模型调用，符合 LLMBackend Protocol。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.contracts.types import (
    LLMCapability,
    LLMMessage,
    LLMGenerationResult,
    LLMBackend,
)

logger = logging.getLogger("ylcraft.llm.doubao")


@dataclass
class DoubaoConfig:
    """Doubao 模型配置"""
    api_key: str
    api_base: str  # e.g. https://ark.cn-beijing.volces.com/api/v3
    model: str  # e.g. doubao-lite-4k


class DoubaoLLMBackend:
    """
    豆包 LLM 后端实现。
    """

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str = "doubao-lite-4k",
    ):
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        self._capabilities = {
            LLMCapability.TEXT_COMPLETION,
            LLMCapability.STRUCTURED_OUTPUT,
        }

    @property
    def name(self) -> str:
        return "doubao"

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[LLMCapability]:
        return self._capabilities

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMGenerationResult:
        """
        调用豆包 chat completion API。
        """
        # 构建请求
        url = f"{self._api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # 转换消息格式
        oai_messages = []
        for msg in messages:
            oai_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        body = {
            "model": self._model,
            "messages": oai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                content = data["choices"][0]["message"]["content"]
                return LLMGenerationResult(
                    content=content,
                    model=self._model,
                    usage=data.get("usage", {}),
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"[Doubao] HTTP错误: {e.response.status_code} - {e.response.text}")
            return LLMGenerationResult(
                content="",
                model=self._model,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            logger.error(f"[Doubao] 调用失败: {e}")
            return LLMGenerationResult(
                content="",
                model=self._model,
                error=str(e),
            )

    async def structured_output(self, schema: dict, prompt: str) -> dict:
        """
        使用工具调用获取结构化输出。
        简化实现：直接用 chat 返回然后解析 JSON。
        """
        messages = [
            LLMMessage(role="system", content="你是一个JSON生成器。根据用户描述生成合法的JSON。只需返回JSON，不要其他文字。"),
            LLMMessage(role="user", content=f"{prompt}\n\n请按以下JSON schema生成:\n{schema}"),
        ]
        result = await self.chat(messages, temperature=0.1)

        if result.error:
            return {"error": result.error}

        # 尝试解析 JSON
        import json
        import re

        # 提取 JSON 块
        match = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', result.content)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {"error": "无法解析JSON", "raw": result.content}