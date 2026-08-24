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
async def test_llm_unavailable_backend_is_recorded_as_failed_event(monkeypatch):
    recorded: list[dict] = []

    async def capture_event(**kwargs):
        recorded.append(kwargs)
        return "log_llm_failure"

    monkeypatch.setattr(llm_api, "get_ai_service", lambda: _UnavailableBackendManager())
    monkeypatch.setattr(llm_api.platform_log, "record_event", capture_event)

    response = await llm_api.chat(
        llm_api.ChatRequest(
            messages=[{"role": "user", "content": "test model configuration"}],
            provider="rohail",
            model="qwen3.8-27b",
        )
    )

    assert response.success is False
    assert "No available LLM Backend" in (response.error or "")
    assert len(recorded) == 1
    event = recorded[0]
    assert event["scene"] == "llm"
    assert event["task_type"] == "llm_chat"
    assert event["level"] == "error"
    assert event["status"] == "failed"
    assert event["provider"] == "rohail"
    assert event["model"] == "qwen3.8-27b"
    assert event["message"] == "文本生成失败"
    assert "No available LLM Backend" in event["error"]
    assert event["request"]["messages"] == [{"role": "user", "content": "test model configuration"}]
    assert event["retry_payload"] == event["request"]
