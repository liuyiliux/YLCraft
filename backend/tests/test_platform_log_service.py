"""Unit tests for the platform event log service.

Covers `record_event` persistence, sensitive-field redaction and summary
truncation (OpenSpec `platform-event-logging` task 24), plus the
`retry_of` / `retried_by` retry chain (task 28).
"""

from __future__ import annotations

import pytest

from app.services.platform_log import service as platform_log


class _RecordingSession:
    """Minimal async-session stand-in that captures committed rows."""

    def __init__(self) -> None:
        self.added: list[object] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        return None

    async def rollback(self):
        return None


@pytest.fixture
def captured(monkeypatch):
    """Route `record_event` writes into an in-memory recorder."""
    session = _RecordingSession()

    def _session_factory():
        return session

    monkeypatch.setattr(platform_log, "get_async_session", _session_factory)
    return session


@pytest.mark.asyncio
async def test_record_event_persists_core_fields(captured):
    event_id = await platform_log.record_event(
        scene="image",
        task_type="image_generation",
        level="error",
        status="failed",
        provider="openai",
        model="gpt-image-1",
        message="图片生成失败",
        error="socket timeout",
        duration_ms=1500,
        project_id="proj_1",
    )

    assert event_id is not None
    assert len(captured.added) == 1

    row = captured.added[0]
    assert row.id == event_id
    assert row.scene == "image"
    assert row.status == "failed"
    assert row.level == "error"
    assert row.provider == "openai"
    assert row.error == "socket timeout"
    assert row.duration_ms == 1500
    assert row.project_id == "proj_1"


@pytest.mark.asyncio
async def test_record_event_redacts_credentials_in_retry_payload(captured):
    await platform_log.record_event(
        scene="image",
        status="failed",
        retry_payload={
            "prompt": "a cat",
            "api_key": "sk-should-not-persist",
            "headers": {"Authorization": "Bearer secret-token"},
        },
    )

    stored = captured.added[0].retry_payload_json
    assert "sk-should-not-persist" not in stored
    assert "secret-token" not in stored
    # Business fields required for a faithful replay must survive redaction.
    assert "a cat" in stored


@pytest.mark.asyncio
async def test_record_event_truncates_long_summaries(captured):
    await platform_log.record_event(
        scene="llm",
        status="failed",
        error="E" * 5000,
        response={"blob": "x" * 5000},
    )

    row = captured.added[0]
    assert len(row.error) <= platform_log.MAX_SUMMARY_LENGTH + len("...(truncated)")
    assert row.error.endswith("...(truncated)")
    assert len(row.response_summary) <= platform_log.MAX_SUMMARY_LENGTH + len("...(truncated)")
    assert row.response_summary.endswith("...(truncated)")


@pytest.mark.asyncio
async def test_record_event_keeps_short_summaries_intact(captured):
    await platform_log.record_event(scene="llm", status="success", error="minor warning")

    assert captured.added[0].error == "minor warning"
    assert captured.added[0].error.endswith("...(truncated)") is False


@pytest.mark.asyncio
async def test_record_event_returns_none_when_persistence_fails(monkeypatch):
    def _broken_session_factory():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(platform_log, "get_async_session", _broken_session_factory)

    # Logging is best-effort: a storage failure must not raise into callers.
    assert await platform_log.record_event(scene="image", status="failed") is None


@pytest.mark.asyncio
async def test_link_retried_by_builds_retry_chain(monkeypatch):
    from app.db.models.platform_log import PlatformEventLog

    original = PlatformEventLog(id="log_original", scene="image", status="failed")
    store = {"log_original": original}

    class _Session(_RecordingSession):
        async def get(self, model, key):
            return store.get(key)

        async def __aenter__(self):
            return self

    session = _Session()
    monkeypatch.setattr(platform_log, "get_async_session", lambda: session)

    await platform_log.link_retried_by("log_original", "log_retry")

    assert original.retried_by == "log_retry"


@pytest.mark.asyncio
async def test_link_retried_by_ignores_missing_event(monkeypatch):
    class _EmptySession(_RecordingSession):
        async def get(self, model, key):
            return None

        async def __aenter__(self):
            return self

    monkeypatch.setattr(platform_log, "get_async_session", _EmptySession)

    # A missing original must not raise; the chain is best-effort metadata.
    await platform_log.link_retried_by("log_missing", "log_retry")
