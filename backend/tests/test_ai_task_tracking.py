"""AI 操作的任务记录：ai_task 封装 + 持久化白名单规则。

任务中心此前完全依赖端点手写 create_task，地图生图整段漏写导致"查无此任务"。
用 ai_task 后一段上下文就完成建任务/进度/完成或失败；这组用例锁住该契约，
并锁住白名单"不静默丢弃"（丢弃要说明原因）。
"""

import pytest

from app.core.task_queue import InMemoryTaskQueue, TaskStatus
from app.services.ai.tracking import ai_task
from app.services.task_persistence import should_persist


@pytest.fixture
def queue(monkeypatch) -> InMemoryTaskQueue:
    """内存队列 + 拦截落库，避免测试触碰数据库。"""
    persisted: list = []

    async def fake_upsert(task):
        # 保留真实的白名单判断：只替换"写库"这一步。
        if should_persist(str(task.task_type), task.payload or {}):
            persisted.append(task.task_id)

    monkeypatch.setattr("app.services.task_persistence.upsert_task", fake_upsert)
    created = InMemoryTaskQueue()
    created._persisted = persisted  # type: ignore[attr-defined]
    return created


async def test_ai_task_marks_done_with_result(queue):
    async with ai_task(
        "world_map_visual",
        project_id="p1",
        title="地图视觉成图",
        payload={"map_id": "m1"},
        queue=queue,
    ) as task:
        task["result"] = {"map_id": "m1", "images": 2}
        captured = task["task_id"]

    record = queue._tasks[captured]
    assert record.status == TaskStatus.DONE
    assert record.progress == 100
    assert record.error is None
    assert record.payload["project_id"] == "p1"
    assert record.payload["map_id"] == "m1"
    assert record.payload["title"] == "地图视觉成图"
    assert record.result == {"map_id": "m1", "images": 2}
    assert [event.type for event in record.events] == ["start", "done"]
    assert record.completed_at is not None


async def test_ai_task_marks_failed_and_reraises(queue):
    with pytest.raises(RuntimeError):
        async with ai_task("world_map_visual", project_id="p1", queue=queue):
            raise RuntimeError("生图失败")

    record = list(queue._tasks.values())[0]
    assert record.status == TaskStatus.FAILED
    assert "生图失败" in (record.error or "")
    assert any(event.type == "error" for event in record.events)


async def test_ai_task_persists_only_with_project(queue):
    async with ai_task("world_map_visual", project_id="p1", queue=queue):
        pass
    assert queue._persisted  # 带 project_id 且在白名单内 → 走落库

    queue._persisted.clear()
    async with ai_task("world_map_visual", queue=queue):  # 无 project_id
        pass
    assert not queue._persisted


def test_should_persist_rules():
    assert should_persist("world_map_visual", {"project_id": "p1"}) is True
    # 缺项目归属：只存内存，重启即失。
    assert should_persist("world_map_visual", {}) is False
    assert should_persist("world_map_visual", None) is False
    # 未登记的类型：同样不落库（需要时登记进 PERSISTED_TASK_TYPES）。
    assert should_persist("some_new_type", {"project_id": "p1"}) is False
