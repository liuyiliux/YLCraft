from datetime import datetime, timezone

import pytest

from app.api.v1 import tasks as tasks_api
from app.core.task_queue import InMemoryTaskQueue, MAX_TASK_EVENTS, get_task_queue, init_task_queue
from app.services.task_persistence import should_persist


def test_project_writing_tasks_are_persisted():
    assert should_persist("creative_writing", {"project_id": "project-1"}) is True
    assert should_persist("creative_writing", {}) is False


def test_media_task_diagnostics_preserves_provider_payload_and_adds_task_center_fields():
    diagnostics = tasks_api._media_task_diagnostics(
        payload={
            "planning_summary": {
                "provider": "Agnes Video V2.0 Text to Video",
                "model": "agnes-video-v2.0",
            },
        },
        result={
            "provider_task_id": "video_95471d0af2c04b1495a47916b7aeef60",
            "diagnostics": {
                "operation": "submit",
                "method": "POST",
                "endpoint": "https://api.agnes-ai.cn/v1/videos",
                "http_status": 200,
                "response_excerpt": '{"status":"queued"}',
            },
        },
        status="pending",
    )

    assert diagnostics is not None
    # Provider-specific diagnostics stay intact for deep debugging.
    assert diagnostics["operation"] == "submit"
    assert diagnostics["http_status"] == 200
    # Task-center display fields are normalized without duplicating storage.
    assert diagnostics["external_task_id"] == "video_95471d0af2c04b1495a47916b7aeef60"
    assert diagnostics["provider"] == "Agnes Video V2.0 Text to Video"
    assert diagnostics["model"] == "agnes-video-v2.0"
    assert diagnostics["last_remote_status"] == "pending"
    assert diagnostics["last_response_excerpt"] == '{"status":"queued"}'


def test_media_task_diagnostics_prefers_explicit_normalized_fields():
    diagnostics = tasks_api._media_task_diagnostics(
        payload={"external_task_id": "payload-id"},
        result={
            "provider_task_id": "result-id",
            "diagnostics": {
                "external_task_id": "diagnostics-id",
                "response_excerpt": "provider response",
                "last_response_excerpt": "already normalized",
            },
        },
    )

    assert diagnostics == {
        "external_task_id": "diagnostics-id",
        "response_excerpt": "provider response",
        "last_response_excerpt": "already normalized",
    }


def test_terminal_task_without_end_timestamp_has_unknown_duration():
    """A failed row without completed_at must not report a duration that grows daily."""
    duration = tasks_api._duration_seconds({
        "status": "error",
        "created_at": 1_700_000_000.0,
        "completed_at": None,
    })

    assert duration is None


def test_active_task_without_end_timestamp_uses_current_time():
    duration = tasks_api._duration_seconds({
        "status": "running",
        "created_at": 1_700_000_000.0,
        "completed_at": None,
    })

    assert duration is not None
    assert duration > 0


def test_task_timestamps_serialize_with_explicit_offset():
    """Every storage shape must carry an offset so browsers cannot guess local time.

    ``asset_nodes`` uses naive UTC while the media ledgers store epoch floats.
    A bare naive ISO string made the browser read 09:06 UTC as 09:06 Beijing.
    """
    epoch = 1_790_152_374.0  # 2026-09-23T16:32:54+08:00
    naive_utc = datetime(2026, 9, 23, 8, 32, 54)
    aware_utc = datetime(2026, 9, 23, 8, 32, 54, tzinfo=timezone.utc)

    serialized = [
        tasks_api._format_timestamp(epoch),
        tasks_api._format_timestamp(naive_utc),
        tasks_api._format_timestamp(aware_utc),
    ]

    for value in serialized:
        assert value is not None
        parsed = datetime.fromisoformat(value)
        assert parsed.tzinfo is not None, f"{value!r} must carry a UTC offset"

    # All three shapes describe the same instant and must round-trip equal.
    parsed = [tasks_api._parse_timestamp(value) for value in serialized]
    assert parsed[0] == parsed[1] == parsed[2]


def test_task_timestamp_ordering_uses_parsed_instants():
    """Fractional and whole-second strings must not be compared as raw text."""
    earlier = {"created_at": 1_790_152_374.0}                    # ...:54
    later = {"created_at": 1_790_152_374.987654}                 # ...:54.987654
    infos = [
        tasks_api._download_task_info(
            "later", {"status": "done", "created_at": later["created_at"]}
        ),
        tasks_api._download_task_info(
            "earlier", {"status": "done", "created_at": earlier["created_at"]}
        ),
    ]

    ordered = sorted(
        infos,
        key=lambda item: tasks_api._parse_timestamp(item.created_at),
        reverse=True,
    )

    assert [item.task_id for item in ordered] == ["later", "earlier"]


@pytest.mark.asyncio
async def test_task_queue_appends_events_and_sanitizes_sensitive_data():
    queue = InMemoryTaskQueue()
    task = await queue.create_task("image_generation", {"prompt": "demo"})

    event = await queue.append_event(
        task.task_id,
        "submitted_remote",
        "submitted",
        data={
            "Authorization": "Bearer secret-token",
            "nested": {"api_key": "secret-key"},
            "response": "x" * 1200,
        },
    )

    assert event is not None
    stored = await queue.get_task(task.task_id)
    assert stored is not None
    assert len(stored.events) == 1
    assert stored.events[0].data["Authorization"] == "***"
    assert stored.events[0].data["nested"]["api_key"] == "***"
    assert stored.events[0].data["response"].endswith("...(truncated)")


@pytest.mark.asyncio
async def test_task_queue_limits_events():
    queue = InMemoryTaskQueue()
    task = await queue.create_task("image_generation", {})

    for idx in range(MAX_TASK_EVENTS + 5):
        await queue.append_event(task.task_id, f"event_{idx}", f"event {idx}")

    stored = await queue.get_task(task.task_id)
    assert stored is not None
    assert len(stored.events) == MAX_TASK_EVENTS
    assert stored.events[0].type == "event_5"
    assert stored.events[-1].type == f"event_{MAX_TASK_EVENTS + 4}"


@pytest.mark.asyncio
async def test_task_queue_updates_diagnostics():
    queue = InMemoryTaskQueue()
    task = await queue.create_task("image_generation", {})

    diagnostics = await queue.update_diagnostics(
        task.task_id,
        external_task_id="remote-1",
        poll_count=2,
        api_key="secret",
    )

    assert diagnostics == {
        "external_task_id": "remote-1",
        "poll_count": 2,
        "api_key": "***",
    }
    stored = await queue.get_task(task.task_id)
    assert stored is not None
    assert stored.payload["diagnostics"]["external_task_id"] == "remote-1"


@pytest.mark.asyncio
async def test_task_detail_api_returns_diagnostics_and_events_while_list_stays_lightweight():
    init_task_queue()
    queue = get_task_queue()
    task = await queue.create_task("image_generation", {"prompt": "demo"})
    await queue.update_diagnostics(task.task_id, external_task_id="remote-1", poll_count=1)
    await queue.append_event(task.task_id, "submitted_remote", "submitted", data={"status": "PENDING"})

    detail = await tasks_api.get_task_detail(task.task_id)

    assert detail.success is True
    assert detail.task is not None
    assert detail.task.diagnostics == {"external_task_id": "remote-1", "poll_count": 1}
    assert detail.task.events is not None
    assert detail.task.events[0]["type"] == "submitted_remote"

    lightweight = tasks_api._task_info(task, include_detail=False)
    assert lightweight.payload is None
    assert lightweight.result is None
    assert lightweight.diagnostics is None
    assert lightweight.events is None


@pytest.mark.asyncio
async def test_task_list_can_filter_project_and_opt_into_payload_details():
    init_task_queue()
    queue = get_task_queue()
    matching = await queue.create_task(
        "image_generation",
        {"project_id": "project-1", "prompt": "scene"},
    )
    await queue.create_task(
        "image_generation",
        {"project_id": "project-2", "prompt": "other"},
    )
    await queue.create_task("download", {"project_id": "project-1"})

    filtered = await tasks_api.list_tasks(
        project_id="project-1",
        task_type="image_generation",
        active_only=True,
        include_detail=True,
    )

    assert filtered.success is True
    assert [task.task_id for task in filtered.tasks] == [matching.task_id]
    assert filtered.tasks[0].payload == {"project_id": "project-1", "prompt": "scene"}


def test_task_center_merges_durable_media_workspaces_without_queue_duplicates(monkeypatch):
    init_task_queue()
    video = tasks_api.TaskInfo(
        task_id="video-1", task_type="video_generation", status="running", progress=30,
        progress_message="generating", created_at="2026-08-14T10:00:00",
    )
    model3d = tasks_api.TaskInfo(
        task_id="model3d-1", task_type="model3d_generation", status="done", progress=100,
        progress_message="ready", created_at="2026-08-14T11:00:00",
    )

    merged = tasks_api._all_task_infos(video_infos=[video], model3d_infos=[model3d])

    assert [task.task_id for task in merged[:2]] == ["model3d-1", "video-1"]
    assert {task.task_type for task in merged} >= {"video_generation", "model3d_generation"}


@pytest.mark.asyncio
async def test_queue_hydrates_persisted_project_task(monkeypatch):
    async def fake_get_task(task_id):
        assert task_id == "persisted-task"
        return {
            "task_id": task_id,
            "task_type": "image_generation",
            "status": "running",
            "payload": {"project_id": "project-1", "external_task_id": "remote-1"},
            "result": {},
            "progress": 35,
            "progress_message": "generating",
            "created_at": 100.0,
            "started_at": 101.0,
            "events": [],
        }

    monkeypatch.setattr("app.services.task_persistence.get_task", fake_get_task)
    init_task_queue()
    task = await get_task_queue().get_task("persisted-task")

    assert task is not None
    assert task.status.value == "running"
    assert task.payload["external_task_id"] == "remote-1"
    assert task.progress == 35


@pytest.mark.asyncio
async def test_task_center_reports_terminal_durable_task_cannot_cancel(monkeypatch):
    init_task_queue()
    completed = tasks_api.TaskInfo(
        task_id="video-complete", task_type="video_generation", status="done", progress=100,
        progress_message="ready",
    )

    async def no_persistent_cancel(task_id):
        assert task_id == "video-complete"
        return None

    async def video_infos(include_detail=False):
        return [completed]

    async def model_infos(include_detail=False):
        return []

    monkeypatch.setattr(tasks_api, "_cancel_persistent_media_task", no_persistent_cancel)
    monkeypatch.setattr(tasks_api, "_video_task_infos", video_infos)
    monkeypatch.setattr(tasks_api, "_model3d_task_infos", model_infos)

    response = await tasks_api.cancel_task("video-complete")

    assert response.success is False
    assert "done" in response.message
