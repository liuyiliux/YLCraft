"""
YLCraft - Generic LLM Backend

配置驱动的 LLM 后端，支持所有 OpenAI 兼容 API。
通过数据库中的配置驱动，无需为每个 Provider 写代码。
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Dict, List

import httpx
from jinja2 import Template

from app.core.contracts.types import (
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
        # 先调用父类初始化，传入 name 和 model
        super().__init__(name=connector.name, model=connector.default_model)
        
        self.connector = connector
        self.session = session
        # 不要直接设置 self.model，已经在 super().__init__() 中设置了
        
        # 创建 HTTP 客户端
        headers = {}
        if connector.api_key:
            headers["Authorization"] = f"Bearer {connector.api_key}"
        headers["Content-Type"] = "application/json"
        
        self.client = httpx.AsyncClient(
            base_url=connector.base_url or "",
            headers=headers,
            timeout=120.0,
        )
        
        logger.info(f"[GenericLLM] 初始化 Backend: {connector.name}")
    
    async def generate(self, messages: List[LLMMessage], **kwargs) -> LLMGenerationResult:
        """
        生成 LLM 响应
        
        Args:
            messages: 对话历史
            **kwargs: 额外参数
                - model: 动态指定模型（覆盖默认模型，控制花费）
                - temperature: 温度参数
                - max_tokens: 最大 token 数
            
        Returns:
            LLMGenerationResult
        """
        try:
            # 优先使用传入的 model 参数，否则使用默认 model（支持动态模型切换控制花费）
            model = kwargs.get("model", self.model)
            
            # 构建请求体
            request_body = {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": kwargs.get("temperature", 0.7),
                "max_tokens": kwargs.get("max_tokens", 4096),
            }
            
            # 发送请求
            response = await self.client.post("/chat/completions", json=request_body)
            response.raise_for_status()
            data = response.json()
            
            # 解析响应
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            
            return LLMGenerationResult(
                content=content,
                model=model,  # 返回实际使用的模型
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            )
            
        except Exception as e:
            logger.error(f"[GenericLLM] 生成失败: {e}")
            raise
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        # 优先从 connector.available_models 读取，否则使用默认 model
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
