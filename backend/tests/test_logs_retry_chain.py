"""Tests for the failed-event retry chain (OpenSpec `platform-event-logging` task 28).

A retry must reject non-retryable events, replay the sanitized payload through the
matching scene, record a new event carrying `retry_of`, and stamp `retried_by`
back onto the original.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import logs as logs_api


class _StubManager:
    """Records replayed calls and returns a configurable result."""

    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.calls: list[dict] = []

    def is_loaded(self) -> bool:
        return True

    async def generate_image(self, request):
        self.calls.append({"scene": "image", "request": request})
        return SimpleNamespace(
            success=self.success,
            task_id="task_retry_1",
            provider="openai",
            model="gpt-image-1",
            latency_ms=42,
            error=None if self.success else "upstream 503",
        )


def _install(monkeypatch, *, event, manager):
    async def _get_event(_id):
        return event

    monkeypatch.setattr(logs_api.platform_log, "get_event", _get_event)
    monkeypatch.setattr(logs_api, "get_ai_service", lambda: manager)

    recorded: list[dict] = []
    linked: list[tuple[str, str]] = []

    async def _record(**kwargs):
        recorded.append(kwargs)
        return "log_retry_new"

    async def _link(original_id: str, new_id: str) -> None:
        linked.append((original_id, new_id))

    monkeypatch.setattr(logs_api.platform_log, "record_event", _record)
    monkeypatch.setattr(logs_api.platform_log, "link_retried_by", _link)
    return recorded, linked


@pytest.mark.asyncio
async def test_retry_creates_new_event_and_links_chain(monkeypatch):
    event = {
        "id": "log_original",
        "scene": "image",
        "task_type": "image_generation",
        "status": "failed",
        "provider": "openai",
        "model": "gpt-image-1",
        "retry_payload": {"prompt": "a cat", "project_id": "proj_1"},
    }
    manager = _StubManager(success=True)
    recorded, linked = _install(monkeypatch, event=event, manager=manager)

    response = await logs_api.retry_log("log_original")

    assert response.success is True
    assert response.event_id == "log_retry_new"
    assert response.task_id == "task_retry_1"
    # The replay actually reached the provider with the persisted payload.
    assert len(manager.calls) == 1
    # New event must point back at the original failure.
    assert recorded[0]["retry_of"] == "log_original"
    assert recorded[0]["status"] == "success"
    # Original must point forward at the replay.
    assert linked == [("log_original", "log_retry_new")]


@pytest.mark.asyncio
async def test_retry_rejects_successful_event(monkeypatch):
    event = {"id": "log_ok", "scene": "image", "status": "success", "retry_payload": {"prompt": "x"}}
    manager = _StubManager()
    _install(monkeypatch, event=event, manager=manager)

    with pytest.raises(HTTPException) as exc:
        await logs_api.retry_log("log_ok")

    assert exc.value.status_code == 409
    assert manager.calls == []


@pytest.mark.asyncio
async def test_retry_rejects_event_without_replay_payload(monkeypatch):
    event = {"id": "log_bare", "scene": "image", "status": "failed", "retry_payload": {}}
    manager = _StubManager()
    _install(monkeypatch, event=event, manager=manager)

    with pytest.raises(HTTPException) as exc:
        await logs_api.retry_log("log_bare")

    assert exc.value.status_code == 400
    assert manager.calls == []


@pytest.mark.asyncio
async def test_retry_rejects_unknown_event(monkeypatch):
    manager = _StubManager()
    _install(monkeypatch, event=None, manager=manager)

    with pytest.raises(HTTPException) as exc:
        await logs_api.retry_log("log_missing")

    assert exc.value.status_code == 404
    assert manager.calls == []


@pytest.mark.asyncio
async def test_failed_retry_records_failure_and_still_links_chain(monkeypatch):
    event = {
        "id": "log_original",
        "scene": "image",
        "task_type": "image_generation",
        "status": "failed",
        "provider": "openai",
        "model": "gpt-image-1",
        "retry_payload": {"prompt": "a cat"},
    }
    manager = _StubManager(success=False)
    recorded, linked = _install(monkeypatch, event=event, manager=manager)

    response = await logs_api.retry_log("log_original")

    assert response.success is False
    assert response.error == "upstream 503"
    # A replay that fails again is still recorded with the retry link, so the
    # audit trail shows the full attempt history instead of going silent.
    assert recorded[0]["retry_of"] == "log_original"
    assert recorded[0]["status"] == "failed"
    assert linked == [("log_original", "log_retry_new")]
