from types import SimpleNamespace

import pytest

from app.services.agent.multi_agent_coordinator import (
    MultiAgentCoordinator,
    SimulationConfig,
)


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
async def test_multi_agent_team_stores_non_approved_candidate():
    session = _FakeAsyncSession()
    coordinator = MultiAgentCoordinator(SimpleNamespace(session=session))
    config = SimulationConfig(
        project_id="project-1",
        scene_context="废弃剪辑室里的第一次对峙",
        store_as_candidate=True,
    )
    team_result = {
        "team_template_id": "scene-sim",
        "joined_observation": "苏棠没有后退。",
        "delegations": [],
    }

    candidate_id = await coordinator._store_team_candidate(config, team_result)

    assert candidate_id
    assert session.committed is True
    candidate = session.added[0]
    assert candidate_id == candidate.id
    assert candidate.content_type == "scene_simulation_candidate"
    assert candidate.is_locked is False
    assert '"candidate": true' in candidate.data_json
    assert '"approved": false' in candidate.data_json
    assert candidate.text_content == "苏棠没有后退。"


@pytest.mark.asyncio
async def test_multi_agent_team_skips_candidate_when_disabled():
    session = _FakeAsyncSession()
    coordinator = MultiAgentCoordinator(SimpleNamespace(session=session))
    config = SimulationConfig(
        project_id="project-1",
        scene_context="废弃剪辑室里的第一次对峙",
        store_as_candidate=False,
    )

    candidate_id = await coordinator._store_team_candidate(
        config, {"team_template_id": "scene-sim", "joined_observation": "x"}
    )

    assert candidate_id is None
    assert session.added == []
