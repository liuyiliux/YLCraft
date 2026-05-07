"""
YLCraft — OpenAI 连接器

参考 MediaCrawler 的模块化架构设计：
- 继承 IAIConnector 抽象基类
- 支持文本对话、图像生成等功能
- 提供使用统计和成本控制
"""

from __future__ import annotations

import logging
import time
import httpx
from typing import Optional, Any, AsyncIterator, Dict

from app.connectors.base import (
    IAIConnector,
    AIModelType,
    TextMessage,
    ChatRequest,
    ChatResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
    TTSRequest,
    TTSResponse,
)
from app.connectors import register_ai_connector

logger = logging.getLogger("ylcraft.connectors.openai")


@register_ai_connector(
    provider_id="openai",
    supported_model_types=[
        AIModelType.TEXT,
        AIModelType.CHAT,
        AIModelType.IMAGE,
    ],
    default_models={
        AIModelType.CHAT: "gpt-4o",
        AIModelType.IMAGE: "dall-e-3",
    },
    description="OpenAI - GPT-4, DALL-E, Whisper 等",
)
class OpenAIConnector(IAIConnector):
    """
    OpenAI 连接器

    功能：
    - GPT-4/3.5 对话
    - DALL-E 图像生成
    - Whisper 语音转文字
    - 流式输出

    使用方式：
        connector = OpenAIConnector("sk-...")
        await connector.initialize()
        response = await connector.chat(request)
    """

    PROVIDER_ID = "openai"
    PROVIDER_NAME = "OpenAI"

    # API 配置
    API_BASE = "https://api.openai.com/v1"
    TIMEOUT = 60.0

    # 模型价格（每 1K token，美元）
    PRICING = {
        "gpt-4o": {"prompt": 0.005, "completion": 0.015},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
        "dall-e-3": {"standard": 0.04, "hd": 0.08},
        "dall-e-2": {"standard": 0.02, "hd": 0.06},
    }

    def __init__(self, api_key: str, config: dict = None):
        super().__init__(api_key, config)
        self._client: Optional[httpx.AsyncClient] = None
        self._organization: Optional[str] = config.get("organization_id") if config else None

    # -------------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------------

    async def initialize(self) -> bool:
        """初始化连接器"""
        try:
            self._client = httpx.AsyncClient(
                base_url=self.API_BASE,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.TIMEOUT,
            )

            if self._organization:
                self._client.headers["OpenAI-Organization"] = self._organization

            # 健康检查
            if not await self.health_check():
                return False

            self._initialized = True
            logger.info("[OpenAI] Initialized successfully")
            return True

        except Exception as e:
            logger.error(f"[OpenAI] Initialization failed: {e}")
            return False

    async def close(self):
        """关闭连接器"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("[OpenAI] Closed")

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            response = await self._client.get("/models")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"[OpenAI] Health check failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # 对话能力
    # -------------------------------------------------------------------------

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        对话生成

        Args:
            request: 对话请求

        Returns:
            对话响应
        """
        if not self._initialized:
            return ChatResponse(success=False, error="Connector not initialized")

        start_time = time.time()

        try:
            # 构建消息
            messages = [{"role": m.role, "content": m.content} for m in request.messages]

            # 构建请求体
            payload = {
                "model": request.model or "gpt-4o",
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "top_p": request.top_p,
                "frequency_penalty": request.frequency_penalty,
                "presence_penalty": request.presence_penalty,
            }

            if request.stop:
                payload["stop"] = request.stop

            # 发送请求
            response = await self._client.post("/chat/completions", json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code != 200:
                error = response.json()
                return ChatResponse(
                    success=False,
                    error=error.get("error", {}).get("message", "Request failed"),
                    latency_ms=latency_ms,
                )

            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})

            # 计算成本
            model = request.model or "gpt-4o"
            cost = self._calculate_text_cost(model, usage)

            # 更新统计
            self._update_usage_stats(usage, cost, latency_ms)

            return ChatResponse(
                success=True,
                content=choice["message"]["content"],
                model=data["model"],
                finish_reason=choice["finish_reason"],
                usage=usage,
                cost=cost,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[OpenAI] Chat failed: {e}")
            return ChatResponse(success=False, error=str(e), latency_ms=latency_ms)

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        流式对话生成

        Args:
            request: 对话请求

        Yields:
            生成的文本片段
        """
        if not self._initialized:
            return

        request.stream = True

        try:
            messages = [{"role": m.role, "content": m.content} for m in request.messages]

            payload = {
                "model": request.model or "gpt-4o",
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": True,
            }

            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        import json
                        chunk = json.loads(data)
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]

        except Exception as e:
            logger.error(f"[OpenAI] Stream failed: {e}")

    # -------------------------------------------------------------------------
    # 图像生成
    # -------------------------------------------------------------------------

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """
        图像生成

        Args:
            request: 图像生成请求

        Returns:
            图像生成响应
        """
        if not self._initialized:
            return ImageGenerationResponse(success=False, error="Connector not initialized")

        start_time = time.time()

        try:
            payload = {
                "model": request.model or "dall-e-3",
                "prompt": request.prompt,
                "n": request.n,
                "size": request.size,
                "quality": request.quality,
                "style": request.style,
                "response_format": request.response_format,
            }

            response = await self._client.post("/images/generations", json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code != 200:
                error = response.json()
                return ImageGenerationResponse(
                    success=False,
                    error=error.get("error", {}).get("message", "Request failed"),
                    latency_ms=latency_ms,
                )

            data = response.json()

            # 计算成本
            model = request.model or "dall-e-3"
            cost = self._calculate_image_cost(model, request.n, request.quality)

            self._usage_stats.total_cost += cost

            return ImageGenerationResponse(
                success=True,
                images=data.get("data", []),
                model=data.get("model", model),
                cost=cost,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[OpenAI] Image generation failed: {e}")
            return ImageGenerationResponse(success=False, error=str(e), latency_ms=latency_ms)

    # -------------------------------------------------------------------------
    # 视频生成（OpenAI 暂不支持，此处预留）
    # -------------------------------------------------------------------------

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """视频生成 - OpenAI 暂不支持"""
        return VideoGenerationResponse(
            success=False,
            error="OpenAI does not support video generation yet",
        )

    # -------------------------------------------------------------------------
    # 语音合成（OpenAI 暂不支持 TTS，暂用 Whisper）
    # -------------------------------------------------------------------------

    async def text_to_speech(self, request: TTSRequest) -> TTSResponse:
        """语音合成 - OpenAI 暂不支持"""
        return TTSResponse(
            success=False,
            error="Use Whisper for speech-to-text instead",
        )

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def get_available_models(self, model_type: AIModelType) -> list[str]:
        """获取可用模型列表"""
        if model_type == AIModelType.CHAT or model_type == AIModelType.TEXT:
            return ["gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]
        elif model_type == AIModelType.IMAGE:
            return ["dall-e-3", "dall-e-2"]
        elif model_type == AIModelType.AUDIO:
            return ["whisper-1"]
        return []

    def _calculate_text_cost(self, model: str, usage: dict) -> float:
        """计算文本生成成本"""
        pricing = self.PRICING.get(model, {"prompt": 0.005, "completion": 0.015})
        prompt_cost = usage.get("prompt_tokens", 0) / 1000 * pricing["prompt"]
        completion_cost = usage.get("completion_tokens", 0) / 1000 * pricing["completion"]
        return round(prompt_cost + completion_cost, 6)

    def _calculate_image_cost(self, model: str, n: int, quality: str) -> float:
        """计算图像生成成本"""
        pricing = self.PRICING.get(model, {"standard": 0.04, "hd": 0.08})
        price_per_image = pricing.get(quality, pricing.get("standard", 0.04))
        return round(price_per_image * n, 4)
