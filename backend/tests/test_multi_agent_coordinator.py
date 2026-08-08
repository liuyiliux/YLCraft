from types import SimpleNamespace

import pytest

from app.services.agent.multi_agent_coordinator import (
    AgentSlot,
    MultiAgentCoordinator,
    SimulationConfig,
)


class _ScalarResult:
    def __init__(self, value=0):
        self.value = value


class _FakeAsyncSession:
    def __init__(self):
        self.added = []
        self.committed = False

    async def scalar(self, _query):
        return 0

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True

    async def refresh(self, value):
        if not value.id:
            value.id = "candidate-1"


@pytest.mark.asyncio
async def test_multi_agent_scene_simulation_stores_non_approved_candidate():
    session = _FakeAsyncSession()
    coordinator = MultiAgentCoordinator(SimpleNamespace(session=session))
    config = SimulationConfig(
        project_id="project-1",
        scene_context="废弃剪辑室里的第一次对峙",
        store_as_candidate=True,
    )
    slots = [
        AgentSlot("director", "天意总导演", "context", output="冲突升级"),
        AgentSlot("writer", "创作导演", "context", output="苏棠没有后退。"),
    ]

    candidate_id = await coordinator._store_candidate(config, slots)

    assert candidate_id
    assert session.committed is True
    candidate = session.added[0]
    assert candidate.content_type == "scene_simulation_candidate"
    assert candidate.is_locked is False
    assert '"candidate": true' in candidate.data_json
    assert '"approved": false' in candidate.data_json
    assert candidate.text_content == "苏棠没有后退。"
