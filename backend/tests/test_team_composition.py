"""Focused tests for declarative agent team composition.

Covers team template loading/validation, task resolution, deterministic tool
ordering, compression provenance, cost metering and delegation spawn_mode.
No database or live LLM is required.
"""

from __future__ import annotations

import json

import pytest

from app.services.agent.context_compressor import ContextCompressor
from app.services.agent.cost_meter import CostMeter
from app.services.agent.registry import Tool, ToolRegistry
from app.services.agent.scope import AgentScope
from app.services.agent.runtime.delegation import DelegatedTask, DelegationValidationError
from app.services.agent.team_composer import TeamComposer
from app.services.agent.team_template import (
    TeamTemplate,
    TeamTemplateError,
    TeamTemplateLoader,
    TeamTemplateValidator,
    capability_diff,
)


# ---------------------------------------------------------------------------
# Team template loading / validation
# ---------------------------------------------------------------------------


def test_loader_loads_shipped_templates():
    loader = TeamTemplateLoader()
    validator = TeamTemplateValidator()
    for template_id in ("writer-room-team", "scene-sim"):
        template = loader.load(template_id)
        validator.validate(template)  # should not raise
        assert template.name == template_id
        assert template.roles


def test_loader_unknown_template_raises():
    with pytest.raises(TeamTemplateError):
        TeamTemplateLoader().load("does-not-exist")


def _template(roles, join_strategy="all"):
    return TeamTemplate.from_dict({"team": {"name": "t", "roles": roles, "join_strategy": join_strategy}})


def test_validator_rejects_cycle():
    roles = [
        {"id": "a", "profile": "p", "depends_on": ["b"], "join": True},
        {"id": "b", "profile": "p", "depends_on": ["a"]},
    ]
    with pytest.raises(TeamTemplateError):
        TeamTemplateValidator().validate(_template(roles))


def test_validator_rejects_missing_join():
    roles = [{"id": "a", "profile": "p"}, {"id": "b", "profile": "p"}]
    with pytest.raises(TeamTemplateError):
        TeamTemplateValidator().validate(_template(roles))


def test_validator_rejects_invalid_spawn():
    roles = [{"id": "a", "profile": "p", "spawn": "weird", "join": True}]
    with pytest.raises(TeamTemplateError):
        TeamTemplateValidator().validate(_template(roles))


# ---------------------------------------------------------------------------
# TeamComposer task resolution
# ---------------------------------------------------------------------------


def test_build_tasks_writer_room_resolution():
    loader = TeamTemplateLoader()
    template = loader.load("writer-room-team")
    composer = TeamComposer(orchestrator=None)
    tasks = composer.build_tasks(
        template,
        {"project_id": "p1", "scene_context": "雨夜对峙", "characters": ["沈清", "陆沉"]},
    )
    by_key = {t.task_key: t for t in tasks}

    assert set(by_key) == {"director", "role-actor-沈清", "role-actor-陆沉", "editor"}
    assert by_key["director"].spawn_mode == "fork"
    assert by_key["role-actor-沈清"].spawn_mode == "spawn"
    assert by_key["editor"].spawn_mode == "fork"
    # editor joins both role actors, and actors depend on director
    assert set(by_key["editor"].depends_on) == {"role-actor-沈清", "role-actor-陆沉"}
    assert set(by_key["role-actor-沈清"].depends_on) == {"director"}
    # resolved_item flows into actor context for character resolution
    assert by_key["role-actor-沈清"].context["resolved_item"] == "沈清"


def test_build_tasks_scene_sim_has_join_writer():
    loader = TeamTemplateLoader()
    template = loader.load("scene-sim")
    composer = TeamComposer(orchestrator=None)
    tasks = composer.build_tasks(template, {"project_id": "p1", "characters": ["甲"]})
    keys = [t.task_key for t in tasks]
    assert "writer" in keys  # creative-director join role
    assert "editor" in keys
    assert "role-actor-甲" in keys


# ---------------------------------------------------------------------------
# Capability diff
# ---------------------------------------------------------------------------


def test_capability_diff_detects_tool_change():
    before = _template([
        {"id": "a", "profile": "p", "tools": ["x", "y"], "join": True},
    ])
    after = _template([
        {"id": "a", "profile": "p", "tools": ["y", "z"], "join": True},
    ])
    diff = capability_diff(before, after)
    assert "a" in diff["changed"]
    assert diff["changed"]["a"]["before"]["tools"] == ["x", "y"]
    assert diff["changed"]["a"]["after"]["tools"] == ["y", "z"]


def test_capability_diff_detects_added_and_removed_roles():
    before = _template([{"id": "a", "profile": "p", "join": True}])
    after = _template([{"id": "a", "profile": "p", "join": True}, {"id": "b", "profile": "q"}])
    diff = capability_diff(before, after)
    assert "b" in diff["added"]
    assert diff["removed"] == []


# ---------------------------------------------------------------------------
# Host/agent plane isolation
# ---------------------------------------------------------------------------


def test_agent_scope_child_isolates_agent_state():
    shared = object()
    with AgentScope.enter(host={"tools": shared}, agent={"persona": "parent"}) as parent:
        child = parent.child(role_id="role-actor", persona="child")
        # host singletons are shared across scopes
        assert child.get_host("tools") is shared
        # agent-plane state is isolated per scope
        assert child.get_agent("persona") == "child"
        assert parent.get_agent("persona") == "parent"
        assert child.get_agent("role_id") == "role-actor"
        assert AgentScope.current() is parent


# ---------------------------------------------------------------------------
# Delegation spawn_mode parsing
# ---------------------------------------------------------------------------


def test_delegated_task_parses_spawn_mode():
    task = DelegatedTask.from_value({"task_key": "k", "profile_id": "p", "objective": "o", "spawn_mode": "fork"})
    assert task.spawn_mode == "fork"


def test_delegated_task_rejects_invalid_spawn_mode():
    with pytest.raises(DelegationValidationError):
        DelegatedTask.from_value({"task_key": "k", "profile_id": "p", "objective": "o", "spawn_mode": "bad"})


# ---------------------------------------------------------------------------
# Cache-stable tool catalog
# ---------------------------------------------------------------------------


def test_tool_registry_deterministic_ordering():
    probe = ["__probe_zeta", "__probe_alpha", "__probe_mid"]
    try:
        for name in probe:
            ToolRegistry.register(
                Tool(
                    name=name,
                    description="probe",
                    parameters={"type": "object", "properties": {}},
                    handler=lambda **kwargs: None,
                    category="__probe",
                )
            )
        first = ToolRegistry.get_openai_tools_spec(allowed_tools=["*"])
        second = ToolRegistry.get_openai_tools_spec(allowed_tools=["*"])
        names = [item["function"]["name"] for item in first]
        assert names == sorted(names)
        assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(
            second, sort_keys=True, ensure_ascii=False
        )
    finally:
        for name in probe:
            ToolRegistry._tools.pop(name, None)
        ToolRegistry._categories.pop("__probe", None)


# ---------------------------------------------------------------------------
# Compression provenance
# ---------------------------------------------------------------------------


async def test_context_compressor_records_provenance():
    compressor = ContextCompressor(token_threshold=100, keep_last=2, response_budget=0)
    messages = [{"role": "user", "content": "长消息" * 500} for _ in range(20)]
    await compressor.ensure_fits(messages, system_prompt="", memory_context="")
    assert compressor.last_provenance is not None
    assert compressor.last_provenance["expansion_path"] == "compressed_summary"
    assert compressor.last_provenance["summary_version"] >= 1
    assert compressor.last_provenance["source_span"]["compressed_message_count"] > 0


# ---------------------------------------------------------------------------
# CostMeter cache hit rate
# ---------------------------------------------------------------------------


def test_cost_meter_reads_nested_cached_tokens():
    usage = {"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 40}}
    assert CostMeter.cached_prompt_tokens(usage) == 40
    assert CostMeter.cache_hit_rate(usage) == 0.4


def test_cost_meter_reads_flat_cached_tokens():
    usage = {"prompt_tokens": 100, "cached_tokens": 100}
    assert CostMeter.cache_hit_rate(usage) == 1.0


def test_cost_meter_unknown_when_no_total():
    assert CostMeter.cache_hit_rate({}) is None
    assert CostMeter.cache_hit_rate(None) is None
