"""LLM 端点的事件记录契约。

事件日志已下沉到 AIService 三个入口统一记录（见
test_ai_service_event_logging.py），端点层不再手写"调用成功/失败"事件——
否则同一件事会双写两遍。这里锁住的是：端点只负责返回业务结果，不重复记账。
"""

from __future__ import annotations

import pytest

from app.api.v1 import llm as llm_api


class _UnavailableBackendManager:
    def is_loaded(self) -> bool:
        return True

    async def chat(self, **kwargs):
        raise ValueError(
            "No available LLM Backend. Backend: rohail, Model: qwen3.8-27b"
        )


@pytest.mark.asyncio
async def test_llm_unavailable_backend_still_returns_failure(monkeypatch):
    """后端不可用时端点照常返回失败结果（事件由 AIService 收口记录）。"""
    monkeypatch.setattr(llm_api, "get_ai_service", lambda: _UnavailableBackendManager())

    response = await llm_api.chat(
        llm_api.ChatRequest(
            messages=[{"role": "user", "content": "test model configuration"}],
            provider="rohail",
            model="qwen3.8-27b",
        )
    )

    assert response.success is False
    assert "No available LLM Backend" in (response.error or "")


@pytest.mark.asyncio
async def test_llm_endpoint_does_not_write_platform_event_itself(monkeypatch):
    """端点不再直接写平台事件：调用类事件统一由 AIService 收口，避免双写。"""
    recorded: list[dict] = []

    async def capture_event(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(llm_api, "get_ai_service", lambda: _UnavailableBackendManager())
    monkeypatch.setattr(
        "app.services.platform_log.service.record_event", capture_event
    )

    await llm_api.chat(
        llm_api.ChatRequest(messages=[{"role": "user", "content": "hi"}])
    )

    assert recorded == []
