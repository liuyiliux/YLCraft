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
