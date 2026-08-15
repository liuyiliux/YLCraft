import pytest

from app.api.v1 import tasks as tasks_api
from app.core.task_queue import InMemoryTaskQueue, MAX_TASK_EVENTS, get_task_queue, init_task_queue


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
