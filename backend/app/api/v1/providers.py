"""
YLCraft — Provider 管理 API

GET  /api/v1/providers              — 列出所有已注册的 Provider
POST /api/v1/providers/{key}/test   — 测试单个 Provider 连接
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm.manager import get_manager

router = APIRouter()
logger = logging.getLogger("ylcraft.providers")


class ProviderListResponse(BaseModel):
    success: bool = True
    data: list[dict]


class ProviderTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: float | None = None


@router.get("", response_model=ProviderListResponse, summary="Provider 列表")
async def list_providers():
    """
    返回所有已注册的 LLM / Media Provider。
    数据来源：providers.yaml 配置 + 内置 Provider 注册表。
    """
    manager = get_manager()
    providers = []

    # 从 BackendManager 读取已加载的 provider 信息
    # 实际返回格式取决于 manager 的实现
    try:
        if manager.is_loaded():
            for backend in manager._backends.values():
                providers.append({
                    "key": backend.name,
                    "name": backend.name,
                    "media_type": "llm",  # 默认
                    "enabled": True,
                })
    except Exception as e:
        logger.warning(f"Could not enumerate providers: {e}")

    return ProviderListResponse(success=True, data=providers)


@router.post("/{provider_key}/test", response_model=ProviderTestResponse, summary="测试 Provider 连接")
async def test_provider(provider_key: str):
    """
    向指定 Provider 发送一个简单的 chat 请求来验证连通性。
    """
    import time

    manager = get_manager()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="BackendManager 未初始化，请检查 providers.yaml")

    try:
        from app.core.contracts.types import LLMMessage

        start = time.time()
        result = await manager.chat(
            messages=[LLMMessage(role="user", content="Hello, reply with 'ok'")],
            provider=provider_key,
        )
        latency_ms = (time.time() - start) * 1000

        if result.success:
            return ProviderTestResponse(success=True, message="连接成功", latency_ms=latency_ms)
        else:
            return ProviderTestResponse(success=False, message=result.error or "未知错误", latency_ms=latency_ms)
    except Exception as e:
        logger.error(f"Provider test failed for {provider_key}: {e}")
        return ProviderTestResponse(success=False, message=str(e))
