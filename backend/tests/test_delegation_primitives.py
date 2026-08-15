"""Fake-backed tests for the fork and continuable subagent primitives.

These verify the observable contracts of ``ForkExecutor`` (read-only parent
reference injection) and ``send_message`` (resume an existing thread) without a
database or live LLM.
"""

from __future__ import annotations

import json

from app.services.agent.runtime.delegation import (
    DelegatedTask,
    ForkExecutor,
    SubagentExecutionResult,
    SubagentExecutor,
    SubagentOrchestrator,
)


class _FakeSession:
    async def commit(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeService:
    def __init__(self, captured: list):
        self.captured = captured

    async def chat(self, **kwargs):
        self.captured.append(kwargs)
        return {
            "done": True,
            "status": "completed",
            "run_id": "run-1",
            "thread_id": "thread-1",
            "reply": "ok",
            "linked_objects": [],
        }


def _make_executor(captured: list) -> SubagentExecutor:
    return SubagentExecutor(
        lambda: _FakeSession(),
        service_factory=lambda session, user_id: _FakeService(captured),
    )


async def test_fork_executor_injects_readonly_parent_reference():
    captured: list = []
    executor = ForkExecutor(
        lambda: _FakeSession(),
        service_factory=lambda session, user_id: _FakeService(captured),
    )
    task = DelegatedTask(task_key="k", profile_id="p", objective="o", spawn_mode="fork")
    result = await executor.execute(
        task,
        user_id="u",
        root_run_id="root",
        parent_run_id="parent",
        delegation_depth=1,
        context={"project_id": "p1"},
    )
    assert result.status == "completed"
    assert captured[0]["context"]["_fork"] == {
        "parent_run_id": "parent",
        "root_run_id": "root",
        "read_only": True,
    }


async def test_executor_send_message_resumes_existing_thread():
    captured: list = []
    executor = _make_executor(captured)
    result = await executor.send_message(
        thread_id="thread-1",
        user_message="继续写",
        user_id="u",
        profile_id="p",
    )
    assert result.status == "completed"
    assert captured[0]["session_id"] == "thread-1"
    assert captured[0]["force_new_thread"] is False


class _FakeDelegation:
    def __init__(self):
        self.child_run_id = "child-1"
        self.user_id = "u"
        self.target_profile_id = "p"
        self.result_json = json.dumps({"thread_id": "thread-1"})
        self.context_json = "{}"
        self.continuation_of = None
        self.updated_at = None


class _OrchSession:
    async def get(self, model, ident):
        return _FakeDelegation()

    async def commit(self):
        pass


class _FakeRunner:
    def __init__(self):
        self.calls: list = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return SubagentExecutionResult(
            task_key="continuation",
            profile_id="p",
            status="completed",
            child_run_id="child-2",
            reply="ok",
        )


async def test_orchestrator_send_message_records_continuation():
    session = _OrchSession()
    runner = _FakeRunner()
    orchestrator = SubagentOrchestrator(session, runner)
    result = await orchestrator.send_message("d1", "继续", "u")
    assert result["success"] is True
    assert result["child_run_id"] == "child-2"
    assert result["continuation_of"] == "child-1"
    assert runner.calls[0]["thread_id"] == "thread-1"
    assert runner.calls[0]["user_message"] == "继续"
