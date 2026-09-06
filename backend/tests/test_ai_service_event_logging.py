"""AIService 统一事件收口：任何 AI 调用都要落平台事件日志。

背景：事件日志此前只在端点手写，未手写的路径（世界地图生图、批量生图、
agent 工具等）完全不可观测。这里把记录下沉到 AIService 三个入口后，
用这组用例锁住契约：成功/失败/异常/无可用后端都要落账，且可注入业务身份。
"""

import asyncio

import pytest

from app.services.ai.service import AIService, ai_call_context
from app.services.ai.types import (
    ImageGenerationRequest,
    ImageGenerationResult,
    LLMGenerationResult,
    LLMMessage,
    VideoGenerationRequest,
    VideoGenerationResult,
)


class _StubBackend:
    """返回预定结果的 LLM backend。"""

    name = "stub-llm"

    def __init__(self, result=None, raises: Exception | None = None):
        self._result = result
        self._raises = raises

    async def chat(self, messages, model=None, **kwargs):
        if self._raises:
            raise self._raises
        return self._result or LLMGenerationResult(
            success=True, content="你好", model=model or "m1", provider="stub-llm"
        )


class _StubRouter:
    """只实现 AIService 用到的三个 resolve 方法。"""

    def __init__(self, backend=None, image_result=None, video_result=None):
        self._backend = backend
        self._image_result = image_result
        self._video_result = video_result

    def resolve_llm(self, backend_name=None, model=None):
        return self._backend, model or "m1"

    async def resolve_image(self, req):
        return self._image_result or ImageGenerationResult(
            success=True, url="http://img/1.png", provider="stub-img", model="sd"
        )

    async def resolve_video(self, req):
        return self._video_result or VideoGenerationResult(
            success=True, task_id="v1", provider="stub-video", model="kling"
        )


@pytest.fixture
def recorded(monkeypatch):
    """截获平台事件日志写入（避免测试依赖数据库）。"""
    calls: list[dict] = []

    async def fake_record_event(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        "app.services.platform_log.service.record_event", fake_record_event
    )
    return calls


def test_chat_success_emits_event_with_context(recorded):
    service = AIService(registry=None, router=_StubRouter(backend=_StubBackend()))
    with ai_call_context(project_id="p1", ref_id="r1"):
        result = asyncio.run(service.chat([LLMMessage(role="user", content="写一句问候")]))

    assert result.success is True
    assert len(recorded) == 1
    event = recorded[0]
    assert event["scene"] == "llm"
    assert event["task_type"] == "llm_chat"
    assert event["status"] == "success"
    assert event["provider"] == "stub-llm"
    assert event["project_id"] == "p1" and event["ref_id"] == "r1"
    assert event["duration_ms"] >= 0
    assert "写一句问候" in (event["request"] or {}).get("prompt", "")


def test_chat_failure_emits_failed_event(recorded):
    failing = LLMGenerationResult(success=False, error="上游 500", model="m1", provider="stub-llm")
    service = AIService(registry=None, router=_StubRouter(backend=_StubBackend(result=failing)))

    asyncio.run(service.chat([LLMMessage(role="user", content="hi")]))

    assert len(recorded) == 1
    assert recorded[0]["status"] == "failed"
    assert recorded[0]["error"] == "上游 500"
    assert recorded[0]["level"] == "error"


def test_chat_exception_emits_event_and_reraises(recorded):
    boom = RuntimeError("连接被重置")
    service = AIService(
        registry=None, router=_StubRouter(backend=_StubBackend(raises=boom))
    )

    with pytest.raises(RuntimeError):
        asyncio.run(service.chat([LLMMessage(role="user", content="hi")]))

    assert len(recorded) == 1
    assert recorded[0]["status"] == "failed"
    assert "连接被重置" in (recorded[0]["error"] or "")


def test_chat_without_backend_emits_failed_event(recorded):
    class NoBackendRouter(_StubRouter):
        def resolve_llm(self, backend_name=None, model=None):
            return None, model

    service = AIService(registry=None, router=NoBackendRouter())

    result = asyncio.run(service.chat([LLMMessage(role="user", content="hi")], backend_name="nope"))

    assert result.success is False
    assert len(recorded) == 1
    assert recorded[0]["status"] == "failed"
    assert "No available LLM Backend" in (recorded[0]["error"] or "")


def test_generate_image_and_video_emit_events(recorded):
    service = AIService(registry=None, router=_StubRouter())

    asyncio.run(service.generate_image(ImageGenerationRequest(prompt="山水画", model="sd")))
    asyncio.run(service.generate_video(VideoGenerationRequest(prompt="海边日出")))

    assert [(item["scene"], item["task_type"]) for item in recorded] == [
        ("image", "image_generation"),
        ("video", "video_generation"),
    ]
    assert "山水画" in (recorded[0]["request"] or {}).get("prompt", "")


def test_context_can_override_scene_and_suppress(recorded):
    service = AIService(registry=None, router=_StubRouter(backend=_StubBackend()))

    with ai_call_context(scene="world_map", task_type="map_visual", label="地图成图"):
        asyncio.run(service.chat([LLMMessage(role="user", content="hi")]))
    assert recorded[0]["scene"] == "world_map"
    assert recorded[0]["task_type"] == "map_visual"
    assert recorded[0]["message"] == "地图成图"

    # 端点自己写业务事件时抑制自动记账，避免重复。
    with ai_call_context(suppress_auto_event=True):
        asyncio.run(service.chat([LLMMessage(role="user", content="hi")]))
    assert len(recorded) == 1
