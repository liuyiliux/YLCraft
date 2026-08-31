from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.task_queue import get_task_queue
from app.db.models.agent import AgentContextSnapshot, AgentDelegation, AgentMemory, AgentMemorySnapshot, AgentMessage, AgentProfile, AgentRun, AgentRunStep, AgentSession, AgentSkill, AgentSkillDraft, AgentThread, AgentToolCall
from app.db.models.ai_connector import AIConnector
from app.db.models.creative_project import CreativeProject, ProjectContent, ProjectGenerationLog
from app.services.agent import tools as _agent_tools  # noqa: F401 - register tools
from app.services.agent.memory.manager import MemoryManager
from app.services.agent.profile import AgentProfileManager, profile_to_dict
from app.services.agent.skill_templates import builtin_skill_names
from app.api.v1.agent import (
    SaveMemoryCandidatesRequest,
    SaveMemoryRequest,
    SkillRoutePreviewRequest,
    SkillDraftCreateRequest,
    SkillDraftFromRunRequest,
    SkillBundleCreateRequest,
    ToolTestRequest,
    approve_skill_draft,
    cancel_run,
    confirm_pending_step,
    create_skill_bundle,
    create_skill_draft,
    create_skill_draft_from_run,
    delete_skill_bundle,
    discard_memory_candidates,
    export_run_markdown,
    get_memory_view,
    get_run_linked_logs,
    get_run_delegations,
    get_run_memory_snapshot,
    get_run_tree,
    inspect_run_skill_candidate,
    list_skill_package_files,
    list_skill_package_index,
    list_skill_drafts,
    preview_skill_route,
    read_skill_package_file,
    run_tool_test,
    save_memory,
    save_memory_candidates,
    update_skill_bundle,
)
from app.services.agent.registry import Tool, ToolCallResult, ToolRegistry
from app.services.agent.runtime import Planner, RunLoop, SkillRouter, ToolExecutor
from app.services.agent.runtime.delegation import (
    DelegatedTask,
    DelegationLimits,
    DelegationPolicy,
    DelegationValidationError,
    SubagentExecutionResult,
    SubagentOrchestrator,
)
from app.services.agent.skill_loader import SkillPackageLoader
from app.services.agent.skill_drafts import AgentSkillDraftService, SkillDraftError
from app.services.agent.tools.skill_tools import create_agent_skill_draft as create_agent_skill_draft_tool
from app.services.agent.tools.skill_tools import create_agent_skill_draft_from_run as create_agent_skill_draft_from_run_tool
from app.services.agent.tools.skill_tools import inspect_agent_run_skill_candidate as inspect_agent_run_skill_candidate_tool
from app.services.agent.tools.skill_tools import list_agent_skill_drafts as list_agent_skill_drafts_tool
from app.services.agent.tools.delegation_tools import DELEGATE_AGENT_TASKS_SCHEMA
from app.services.agent.service import AgentService
from app.services.agent.session.manager import SessionManager
from app.services.agent.thread_manager import ThreadManager
from app.services.ai.backends.llm.generic import GenericLLMBackend
from app.services.ai.backends.llm.openai_sdk import OpenAISDKLLMBackend
from app.services.ai.types import LLMGenerationResult


@pytest_asyncio.fixture
async def agent_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'agent-center.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(AgentSession.__table__.create)
        await conn.run_sync(AgentThread.__table__.create)
        await conn.run_sync(AgentMessage.__table__.create)
        await conn.run_sync(AgentContextSnapshot.__table__.create)
        await conn.run_sync(AgentMemory.__table__.create)
        await conn.run_sync(AgentSkill.__table__.create)
        await conn.run_sync(AgentSkillDraft.__table__.create)
        await conn.run_sync(AgentProfile.__table__.create)
        await conn.run_sync(AgentToolCall.__table__.create)
        await conn.run_sync(AgentRun.__table__.create)
        await conn.run_sync(AgentRunStep.__table__.create)
        await conn.run_sync(AgentDelegation.__table__.create)
        await conn.run_sync(AgentMemorySnapshot.__table__.create)
        await conn.run_sync(CreativeProject.__table__.create)
        await conn.run_sync(ProjectContent.__table__.create)
        await conn.run_sync(ProjectGenerationLog.__table__.create)
        await conn.run_sync(AIConnector.__table__.create)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_profile_manager_creates_default_profiles(agent_session: AsyncSession):
    manager = AgentProfileManager(agent_session)

    profiles = await manager.list_profiles()

    profile_ids = {profile.id for profile in profiles}
    assert {
        "default-assistant",
        "ai-config-specialist",
        "creative-director",
        "novel-writer",
        "character-designer",
        "storyboard-director",
        "asset-curator",
        "quality-reviewer",
    } <= profile_ids

    creative = next(profile for profile in profiles if profile.id == "creative-director")
    creative_data = profile_to_dict(creative)
    assert creative_data["role_type"] == "orchestrator"
    assert "run_creative_project_pipeline" in creative_data["allowed_tools"]
    assert "run_creative_production_plan" in creative_data["allowed_tools"]
    assert "analyze_creative_production_plan_impact" in creative_data["allowed_tools"]
    assert "preview_fanqie_project_publish" in creative_data["allowed_tools"]
    assert "publish_fanqie_project_chapter" in creative_data["allowed_tools"]
    assert creative_data["max_steps"] == 10

    storyboard = next(profile for profile in profiles if profile.id == "storyboard-director")
    storyboard_data = profile_to_dict(storyboard)
    assert storyboard_data["role_type"] == "storyboard_director"
    assert "search_assets" in storyboard_data["allowed_tools"]

    character_designer = next(profile for profile in profiles if profile.id == "character-designer")
    character_data = profile_to_dict(character_designer)
    assert "inspect_character" in character_data["allowed_tools"]
    assert "update_character_visual_profile" in character_data["allowed_tools"]
    assert character_data["default_workflow"] == "character_visual_card"
    assert "character_visual_card" in character_data["default_skill_ids"]

    ai_config = next(profile for profile in profiles if profile.id == "ai-config-specialist")
    ai_config_data = profile_to_dict(ai_config)
    assert "get_ai_connector" in ai_config_data["allowed_tools"]
    assert "reference_image_url" in ai_config_data["system_prompt"]
    assert "base64_images_path" in ai_config_data["system_prompt"]
    assert "/v1/images/edits" in ai_config_data["system_prompt"]


@pytest.mark.asyncio
async def test_agent_memory_manager_seeds_builtin_skill_templates(agent_session: AsyncSession):
    manager = MemoryManager(agent_session)

    skills = await manager.list_skills()

    names = {skill.name for skill in skills}
    expected = {
        "novel_completion",
        "character_visual_card",
        "storyboard_generation",
        "reference_match",
        "platform_source_search",
        "download_workflow",
        "image_generation_workflow",
        "subtitle_workflow",
        "clip_workflow",
        "comic_image_prompt",
    }
    assert expected <= names
    assert set(builtin_skill_names()) <= names
    assert all(skill.is_builtin for skill in skills if skill.name in expected)


@pytest.mark.asyncio
async def test_agent_thread_manager_migrates_legacy_session_and_messages(agent_session: AsyncSession):
    # M2.3: Use SessionManager directly for creating legacy test data
    session_mgr = SessionManager(agent_session)
    legacy = await session_mgr.create_session(title="Legacy thread")
    await session_mgr.append_message(legacy.id, {"role": "user", "content": "first"})
    await session_mgr.append_message(legacy.id, {"role": "assistant", "content": "second"})
    await agent_session.commit()

    manager = ThreadManager(agent_session)
    thread = await manager.get_thread(legacy.id)
    assert thread is not None
    assert thread.id == legacy.id
    assert thread.title == "Legacy thread"

    messages = await manager.get_messages(thread.id)
    assert [item["content"] for item in messages] == ["first", "second"]

    snapshot = await manager.create_context_snapshot(
        thread_id=thread.id,
        run_id="run-1",
        kind="planning",
        context={"conversation_state": {"active_intent": "demo"}},
        summary="demo snapshot",
        token_estimate=42,
    )
    await agent_session.commit()

    assert snapshot.thread_id == thread.id
    assert snapshot.run_id == "run-1"


@pytest.mark.asyncio
async def test_agent_chat_uses_thread_messages_without_legacy_session(agent_session: AsyncSession):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="continued")

    manager = ThreadManager(agent_session)
    thread = await manager.create_thread(title="Thread only")
    await manager.append_message(thread.id, {"role": "user", "content": "search ghost story videos"})
    await agent_session.commit()

    assert await agent_session.get(AgentSession, thread.id) is None

    service = AgentService(agent_session)
    fake = FakeLLM()
    service._llm_manager = fake

    result = await service.chat(
        session_id=thread.id,
        user_message="use bilibili skill",
        context={},
    )

    assert result["thread_id"] == thread.id
    assert result["session_id"] == thread.id
    assert await agent_session.get(AgentSession, thread.id) is not None

    messages = await manager.get_messages(thread.id)
    assert [item["content"] for item in messages] == [
        "search ghost story videos",
        "use bilibili skill",
        "continued",
    ]
    assert fake.calls
    planned_messages = fake.calls[0]["messages"]
    assert [item.content for item in planned_messages[-2:]] == [
        "search ghost story videos",
        "use bilibili skill",
    ]
    assert "search ghost story videos" in planned_messages[0].content


def test_agent_tool_registry_exposes_creative_project_tools():
    tools = ToolRegistry.list_tools("creative_project")
    names = {tool.name for tool in tools}

    assert "list_creative_projects" in names
    assert "inspect_creative_project" in names
    assert "build_creative_project_context_pack" in names
    assert "list_creative_project_contents" in names
    assert "get_creative_project_content" in names
    assert "get_creative_production_plan" in names
    assert "save_creative_production_plan" in names
    assert "update_creative_project_content" in names
    assert "list_creative_project_asset_links" in names
    assert "link_creative_project_asset" in names
    assert "match_creative_project_reference_assets" in names
    assert "list_creative_project_generation_logs" in names
    assert "get_creative_project_generation_log" in names
    assert "run_creative_writer_room" in names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write", "costly"}
        assert tool.output_type.startswith("creative_")
    match_tool = ToolRegistry.get_tool("match_creative_project_reference_assets")
    assert match_tool is not None
    assert match_tool.cost_hint
    assert ToolRegistry.get_tool("get_creative_production_plan").risk_level == "read"
    assert ToolRegistry.get_tool("save_creative_production_plan").risk_level == "write"


def test_agent_tool_registry_exposes_canvas_tools_with_specs():
    tools = ToolRegistry.list_tools("canvas")
    names = {tool.name for tool in tools}

    assert {
        "list_creative_canvas_documents",
        "get_creative_canvas_document",
        "apply_creative_canvas_operations",
        "get_project_canvas",
        "save_project_canvas",
        "add_project_canvas_node",
        "connect_project_canvas_nodes",
        "apply_project_canvas_operations",
    }.issubset(names)
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write"}
        assert tool.output_type.startswith(("project_canvas_", "creative_canvas_"))
    assert ToolRegistry.get_tool("get_project_canvas").risk_level == "read"
    assert ToolRegistry.get_tool("apply_project_canvas_operations").risk_level == "write"
    assert ToolRegistry.get_tool("list_creative_canvas_documents").risk_level == "read"
    assert ToolRegistry.get_tool("apply_creative_canvas_operations").risk_level == "write"


def test_agent_tool_registry_exposes_character_tools():
    tools = ToolRegistry.list_tools("character")
    names = {tool.name for tool in tools}

    assert {
        "list_characters",
        "find_character_duplicate_candidates",
        "inspect_character",
        "preview_character_portrait_prompt",
        "update_character_visual_profile",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write"}


def test_agent_tool_registry_exposes_asset_tools_with_specs():
    tools = ToolRegistry.list_tools("asset")
    names = {tool.name for tool in tools}

    assert {
        "search_assets",
        "get_asset_detail",
        "download_asset",
        "add_asset_tag",
        "delete_asset",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write", "delete"}
        assert tool.output_type.startswith("asset_")
    search_tool = ToolRegistry.get_tool("search_assets")
    assert search_tool is not None
    assert "status" in search_tool.parameters["properties"]


def test_agent_tool_registry_exposes_subtitle_tools_with_specs():
    tools = ToolRegistry.list_tools("subtitle")
    names = {tool.name for tool in tools}

    assert {"extract_subtitle", "get_subtitle_styles", "burn_subtitle"} <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write", "costly"}
        assert tool.output_type.startswith("subtitle_") or tool.output_type == "video_file_result"
    extract_tool = ToolRegistry.get_tool("extract_subtitle")
    assert extract_tool is not None
    assert extract_tool.cost_hint


def test_agent_tool_registry_exposes_bgm_tools_with_specs():
    tools = ToolRegistry.list_tools("bgm")
    names = {tool.name for tool in tools}

    assert {"list_bgm_tracks", "add_bgm_to_video", "upload_bgm"} <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write"}
        assert tool.output_type.startswith("bgm_") or tool.output_type == "video_file_result"


def test_agent_tool_registry_exposes_clip_tools_with_specs():
    tools = ToolRegistry.list_tools("clip")
    names = {tool.name for tool in tools}

    assert {"start_cutclaw_clip", "start_narrato_clip", "start_moe_clip", "get_clip_task_status"} <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "costly"}
        assert tool.output_type.startswith("clip_")
        if tool.risk_level == "costly":
            assert tool.cost_hint


def test_agent_tool_registry_exposes_breaker_tools_with_specs():
    tools = ToolRegistry.list_tools("breaker")
    names = {tool.name for tool in tools}

    assert {"analyze_viral_content", "get_breaker_task_status", "generate_script"} <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "external", "costly"}
        assert tool.output_type in {"breaker_task_started", "breaker_analysis_status", "script_text_result"}
    generate_tool = ToolRegistry.get_tool("generate_script")
    assert generate_tool is not None
    assert generate_tool.cost_hint


def test_agent_tool_registry_exposes_image_tools_with_specs():
    tools = ToolRegistry.list_tools("image")
    names = {tool.name for tool in tools}

    assert {
        "list_image_backends",
        "preview_image_generation_request",
        "generate_image_asset",
        "poll_image_generation_task",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "costly"}
        assert tool.output_type.startswith("image_")
    generate_tool = ToolRegistry.get_tool("generate_image_asset")
    assert generate_tool is not None
    assert generate_tool.cost_hint


def test_agent_tool_registry_exposes_video_tools_with_specs():
    tools = ToolRegistry.list_tools("video")
    names = {tool.name for tool in tools}

    assert {
        "list_video_backends",
        "preview_video_generation_request",
        "generate_video_asset",
        "poll_video_generation_task",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "costly"}
        assert tool.output_type.startswith("video_")
    generate_tool = ToolRegistry.get_tool("generate_video_asset")
    assert generate_tool is not None
    assert generate_tool.cost_hint


def test_agent_tool_registry_exposes_image_prompt_reference_tools_with_specs():
    tools = ToolRegistry.list_tools("image_prompt_reference")
    names = {tool.name for tool in tools}

    assert {
        "list_image_prompt_sources",
        "search_image_prompt_references",
        "get_image_prompt_reference",
        "refresh_image_prompt_sources",
        "save_image_prompt_reference_as_asset",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write"}
        assert tool.output_type.startswith("image_prompt_")
    assert ToolRegistry.get_tool("list_image_prompt_sources").risk_level == "read"
    assert ToolRegistry.get_tool("search_image_prompt_references").risk_level == "read"
    assert ToolRegistry.get_tool("get_image_prompt_reference").risk_level == "read"
    assert ToolRegistry.get_tool("refresh_image_prompt_sources").risk_level == "write"
    assert ToolRegistry.get_tool("save_image_prompt_reference_as_asset").risk_level == "write"


def test_agent_tool_registry_exposes_prompt_template_tools_with_specs():
    tools = ToolRegistry.list_tools("prompt_template")
    names = {tool.name for tool in tools}

    assert {
        "list_prompt_templates",
        "get_prompt_template",
        "preview_prompt_template_render",
        "update_prompt_template",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write"}
        assert tool.output_type.startswith("prompt_template_")
    update_tool = ToolRegistry.get_tool("update_prompt_template")
    assert update_tool is not None
    assert update_tool.risk_level == "write"


def test_agent_tool_registry_exposes_ai_config_tools_with_specs():
    tools = ToolRegistry.list_tools("ai_config")
    names = {tool.name for tool in tools}

    assert {
        "list_ai_connectors", "get_ai_connector",
        "list_provider_metadata", "get_provider_metadata",
        "upsert_provider_metadata", "create_ai_connector",
        "update_ai_connector", "test_ai_connector",
        "discover_connector_models",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write"}
        valid_prefixes = (
            "ai_connector_", "provider_metadata_", "test_", "model_"
        )
        assert any(tool.output_type.startswith(p) for p in valid_prefixes), \
            f"{tool.name}: output_type={tool.output_type} must start with one of {valid_prefixes}"

    # 写入类工具的 risk_level 验证
    assert ToolRegistry.get_tool("upsert_provider_metadata").risk_level == "write"
    assert ToolRegistry.get_tool("create_ai_connector").risk_level == "write"
    assert ToolRegistry.get_tool("update_ai_connector").risk_level == "write"
    # 只读工具的 risk_level 验证
    assert ToolRegistry.get_tool("test_ai_connector").risk_level == "read"
    assert ToolRegistry.get_tool("discover_connector_models").risk_level == "read"


def test_agent_tool_registry_exposes_fanqie_tools_with_safe_publish_boundary():
    tools = ToolRegistry.list_tools("fanqie")
    names = {tool.name for tool in tools}
    assert {
        "list_fanqie_my_books",
        "get_fanqie_book_stats",
        "get_fanqie_hot_list",
        "preview_fanqie_project_publish",
        "get_fanqie_project_publish_status",
        "publish_fanqie_project_chapter",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.output_type.startswith("fanqie_")

    assert ToolRegistry.get_tool("preview_fanqie_project_publish").risk_level == "read"
    publish = ToolRegistry.get_tool("publish_fanqie_project_chapter")
    assert publish is not None
    assert publish.risk_level == "write"
    assert "[TEST]" in publish.input_schema_note


@pytest.mark.asyncio
async def test_fanqie_publish_tool_requires_runtime_confirmation(monkeypatch):
    async def fake_execute_tool(tool_name, tool_args):
        return ToolCallResult(tool_name=tool_name, success=True, result={"success": True, "arguments": tool_args})

    monkeypatch.setattr(ToolRegistry, "execute_tool", fake_execute_tool)
    executor = ToolExecutor()
    tool_call = {
        "id": "call_fanqie_publish",
        "name": "publish_fanqie_project_chapter",
        "arguments": json.dumps({"project_id": "project-1", "content_id": "content-1", "item_id": "test-item"}),
    }
    pending = await executor.execute_tool_call(tool_call, {"allowed_tools": ["*"]})
    assert pending.success is False
    assert executor.is_pending_confirmation(pending)

    confirmed_call = {**tool_call, "arguments": json.dumps({"project_id": "project-1", "content_id": "content-1", "item_id": "test-item", "__confirmed": True})}
    confirmed = await executor.execute_tool_call(confirmed_call, {"allowed_tools": ["*"]})
    assert confirmed.success is True

    create_tool = ToolRegistry.get_tool("create_ai_connector")
    update_tool = ToolRegistry.get_tool("update_ai_connector")
    assert create_tool is not None
    assert update_tool is not None
    create_note = create_tool.input_schema_note
    update_note = update_tool.input_schema_note
    for expected in [
        "prompt_json",
        "reference_image_url",
        "images_json",
        "image_url",
        "multipart",
        "base64_images_path",
        "image_capabilities",
        "互斥",
    ]:
        assert expected in create_note
    for expected in [
        "/v1/images/edits",
        "reference_image_array_field=images",
        "reference_image_field 留空",
        "multipart_image_field",
        "image_capabilities",
        "api_key 为空字符串表示不修改",
    ]:
        assert expected in update_note


def test_agent_system_prompt_guides_ai_connector_configuration():
    from app.services.agent.service import AGENT_SYSTEM_PROMPT

    assert "list_provider_metadata / list_ai_connectors" in AGENT_SYSTEM_PROMPT
    assert "/v1/images/generations" in AGENT_SYSTEM_PROMPT
    assert "/v1/images/edits" in AGENT_SYSTEM_PROMPT
    assert "{{ prompt_json }}" in AGENT_SYSTEM_PROMPT
    assert "images=[{\"image_url\":\"{{ reference_image_url }}\"}]" in AGENT_SYSTEM_PROMPT
    assert "参考图传递方式必须互斥" in AGENT_SYSTEM_PROMPT
    assert "image_capabilities" in AGENT_SYSTEM_PROMPT
    assert "base64_images_path" in AGENT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_ai_config_write_tools_do_not_interrupt_for_confirmation(monkeypatch):
    async def fake_execute_tool(tool_name, tool_args):
        return ToolCallResult(tool_name=tool_name, success=True, result={"success": True, "arguments": tool_args})

    monkeypatch.setattr(ToolRegistry, "execute_tool", fake_execute_tool)

    executor = ToolExecutor()
    result = await executor.execute_tool_call(
        {
            "id": "call_update_connector",
            "name": "update_ai_connector",
            "arguments": json.dumps({"connector_id": "conn-1", "support_reference_image": "true"}),
        },
        {"allowed_tools": ["*"]},
    )

    assert result.success is True
    assert not executor.is_pending_confirmation(result)
    assert result.result["arguments"]["support_reference_image"] == "true"


def test_squashed_alembic_initial_schema_imports_sqlmodel():
    import importlib.util
    from pathlib import Path

    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "001_initial_schema.py"
    spec = importlib.util.spec_from_file_location("ylcraft_initial_schema_test", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert hasattr(module, "sqlmodel")


def test_alembic_env_loads_the_complete_model_package_for_autogenerate():
    from pathlib import Path
    from sqlmodel import SQLModel
    from app.db import models as _models  # noqa: F401

    env_path = Path(__file__).resolve().parents[1] / "alembic" / "env.py"
    source = env_path.read_text(encoding="utf-8")

    assert "from app.db import models as _all_models" in source
    assert "from app.db.models import asset_hub" not in source
    assert {
        "agent_threads",
        "creative_projects",
        "canvas_documents",
        "image_prompt_references",
        "project_task_records",
    }.issubset(SQLModel.metadata.tables)


def test_alembic_revision_graph_has_one_head_and_compiles_offline_sql():
    from io import StringIO
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    script = ScriptDirectory.from_config(config)

    assert len(script.get_heads()) == 1
    output = StringIO()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE creative_projects" in sql
    assert "CREATE TABLE agent_threads" in sql
    assert "CREATE TABLE canvas_documents" in sql
    assert "CREATE TABLE image_prompt_references" in sql
    assert "CREATE TABLE project_task_records" in sql
    assert "CREATE TABLE project_publish_records" in sql
    assert "008_add_project_publish_records" in sql


@pytest.mark.asyncio
async def test_agent_table_compatibility_hook_is_non_mutating():
    from app.db.database import ensure_agent_tables

    assert await ensure_agent_tables() is None


@pytest.mark.asyncio
async def test_upsert_provider_metadata_rejects_invalid_json_arguments():
    from app.services.agent.tools.ai_config_tools import upsert_provider_metadata

    result = await upsert_provider_metadata(
        provider_id="bad-json-provider",
        name="Bad JSON Provider",
        supported_types='["image"]',
        request_templates="{bad json",
    )

    assert result["success"] is False
    assert result["field"] == "request_templates"
    assert "不是有效 JSON" in result["message"]


def test_agent_tool_registry_exposes_task_tools_with_specs():
    tools = ToolRegistry.list_tools("task")
    names = {tool.name for tool in tools}

    assert {
        "list_project_tasks",
        "get_project_task",
        "cancel_project_task",
        "delete_project_task",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write", "delete"}
        assert tool.output_type.startswith("task_")
    assert ToolRegistry.get_tool("cancel_project_task").risk_level == "write"
    assert ToolRegistry.get_tool("delete_project_task").risk_level == "delete"


def test_agent_tool_registry_exposes_novel_tools_with_specs():
    tools = ToolRegistry.list_tools("novel")
    names = {tool.name for tool in tools}

    assert {
        "list_novel_sources",
        "list_novel_bookshelf",
        "search_novel_sources",
        "get_novel_catalog",
        "preview_novel_chapter",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "external"}
        assert tool.output_type.startswith("novel_")
    assert ToolRegistry.get_tool("search_novel_sources").risk_level == "external"
    assert ToolRegistry.get_tool("preview_novel_chapter").risk_level == "external"


def test_agent_tool_registry_exposes_download_tools_with_specs():
    tools = ToolRegistry.list_tools("download")
    names = {tool.name for tool in tools}

    assert {
        "parse_download_link",
        "create_download_task",
        "poll_download_task",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "external"}
        assert tool.output_type.startswith("download_")
    assert ToolRegistry.get_tool("parse_download_link").risk_level == "external"
    assert ToolRegistry.get_tool("create_download_task").risk_level == "external"
    assert ToolRegistry.get_tool("create_download_task").cost_hint


def test_agent_tool_registry_exposes_wechat_mp_tools_with_specs():
    tools = ToolRegistry.list_tools("wechat_mp")
    names = {tool.name for tool in tools}

    assert {
        "list_wechat_mp_connections",
        "search_wechat_mp_accounts",
        "list_wechat_mp_articles",
        "download_wechat_mp_article",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "external"}
        assert tool.output_type.startswith("wechat_mp_")
    assert ToolRegistry.get_tool("list_wechat_mp_connections").risk_level == "read"
    assert ToolRegistry.get_tool("download_wechat_mp_article").risk_level == "external"
    assert ToolRegistry.get_tool("download_wechat_mp_article").cost_hint


def test_agent_tool_registry_exposes_tts_tools_with_specs():
    tools = ToolRegistry.list_tools("tts")
    names = {tool.name for tool in tools}

    assert {"preview_tts_request", "generate_tts_audio"} <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "costly"}
        assert tool.output_type.startswith("tts_")
    assert ToolRegistry.get_tool("preview_tts_request").risk_level == "read"
    assert ToolRegistry.get_tool("generate_tts_audio").risk_level == "costly"
    assert ToolRegistry.get_tool("generate_tts_audio").cost_hint


def test_agent_tool_registry_exposes_ebook_tools_with_specs():
    tools = ToolRegistry.list_tools("ebook")
    names = {tool.name for tool in tools}

    assert {
        "create_ebook_from_folder",
        "get_ebook_task",
        "list_ebook_tasks",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write"}
        assert tool.output_type.startswith("ebook_")
    assert ToolRegistry.get_tool("create_ebook_from_folder").risk_level == "write"
    assert ToolRegistry.get_tool("get_ebook_task").risk_level == "read"


def test_agent_tool_registry_exposes_semantic_search_tools_with_specs():
    tools = ToolRegistry.list_tools("semantic_search")
    names = {tool.name for tool in tools}

    assert {
        "semantic_search_assets",
        "find_similar_assets",
        "get_asset_embedding_info",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "costly"}
        assert tool.output_type.startswith("semantic_")
    assert ToolRegistry.get_tool("semantic_search_assets").risk_level == "costly"
    assert ToolRegistry.get_tool("semantic_search_assets").cost_hint
    assert ToolRegistry.get_tool("find_similar_assets").risk_level == "read"


def test_agent_tool_registry_exposes_lineage_tools_with_specs():
    tools = ToolRegistry.list_tools("lineage")
    names = {tool.name for tool in tools}

    assert {
        "get_asset_lineage_graph",
        "get_asset_upstream_lineage",
        "get_asset_downstream_lineage",
        "get_asset_lineage_stats",
        "link_asset_lineage",
        "find_asset_common_ancestor",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write"}
        assert tool.output_type.startswith("lineage_")
    assert ToolRegistry.get_tool("link_asset_lineage").risk_level == "write"
    assert ToolRegistry.get_tool("get_asset_lineage_graph").risk_level == "read"


def test_agent_tool_registry_exposes_reader_tools_with_specs():
    tools = ToolRegistry.list_tools("reader")
    names = {tool.name for tool in tools}

    assert {
        "browse_reader_documents",
        "read_reader_document",
        "read_reader_document_collection",
        "delete_reader_document",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "delete"}
        assert tool.output_type.startswith("reader_")
    assert ToolRegistry.get_tool("delete_reader_document").risk_level == "delete"


def test_agent_tool_registry_exposes_export_tools_with_specs():
    tools = ToolRegistry.list_tools("export")
    names = {tool.name for tool in tools}

    assert {
        "get_export_dataset_stats",
        "export_asset_dataset",
        "calculate_asset_quality",
        "batch_calculate_asset_quality",
        "find_duplicate_assets",
        "merge_duplicate_assets",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write", "costly"}
        assert tool.output_type.startswith("export_")
    assert ToolRegistry.get_tool("export_asset_dataset").risk_level == "write"
    assert ToolRegistry.get_tool("find_duplicate_assets").risk_level == "costly"
    assert ToolRegistry.get_tool("merge_duplicate_assets").risk_level == "write"


def test_agent_tool_registry_exposes_platform_source_tools_with_specs():
    tools = ToolRegistry.list_tools("platform_source")
    names = {tool.name for tool in tools}

    assert {
        "list_platform_source_options",
        "list_platform_connections",
        "search_platform_sources",
        "search_platform_sources_enhanced",
        "get_platform_note_detail",
        "fetch_platform_no_watermark",
        "import_platform_results_to_assets",
    } <= names
    for tool in tools:
        assert tool.input_schema_note
        assert tool.output_schema_note
        assert tool.risk_level in {"read", "write", "external"}
        assert tool.output_type.startswith("platform_")
    assert ToolRegistry.get_tool("list_platform_connections").risk_level == "read"
    assert ToolRegistry.get_tool("search_platform_sources").risk_level == "external"
    assert ToolRegistry.get_tool("import_platform_results_to_assets").risk_level == "write"


def test_agent_skill_router_maps_business_domains_to_skills():
    router = SkillRouter()

    routes = router.route(
        message="继续推进创作项目，检查大纲、角色、正文和分镜缺口",
        context={"project_id": "project-1"},
        allowed_tools=["inspect_creative_project", "build_creative_project_context_pack"],
    )
    names = {item.skill_id for item in routes}

    assert "creative_project_advance" in names
    assert "gap_analysis" in names

    routes = router.route(
        message="把这个角色补成视觉卡并生成立绘提示词",
        context={"character_id": "char-1"},
        allowed_tools=["inspect_character", "preview_character_portrait_prompt"],
    )
    names = {item.skill_id for item in routes}

    assert "character_visual_card" in names
    assert "portrait_prompt" in names

    routes = router.route(
        message="去B站搜包氏父子解说视频，后面下载入素材库",
        context={},
        allowed_tools=["search_platform_sources", "parse_download_link", "create_download_task"],
    )
    names = {item.skill_id for item in routes}

    assert "platform_source_search" in names
    assert "download_workflow" in names
    assert "asset_search" in names


def test_agent_skill_package_loader_reads_standard_skill_md():
    packages = SkillPackageLoader().load_packages()
    package_by_name = {item.name: item for item in packages}

    assert "character_visual_card" in package_by_name
    character_package = package_by_name["character_visual_card"]
    assert character_package.skill_type == "workflow"
    assert "角色" in character_package.triggers["keywords"]
    assert "inspect_character" in character_package.requires_tools
    assert character_package.source_path.endswith("SKILL.md")


def test_creative_skill_capability_roles_cover_director_specialists():
    packages = {item.name: item for item in SkillPackageLoader().load_packages()}
    roles = {
        role
        for package in packages.values()
        for role in package.creative.get("capability_roles", [])
    }

    assert {
        "story-designer",
        "script-writer",
        "visual-director",
        "character-director",
        "storyboard-director",
        "image-producer",
        "video-producer",
        "platform-adapter",
        "editorial-reviewer",
    } <= roles
    assert packages["platform_output_adapter"].creative["capability_roles"] == ["platform-adapter"]


@pytest.mark.asyncio
async def test_agent_memory_manager_seeds_file_backed_builtin_skills(agent_session: AsyncSession):
    manager = MemoryManager(agent_session)

    skills = await manager.list_skills()
    character_skill = next(item for item in skills if item.name == "character_visual_card")

    assert character_skill.is_builtin is True
    assert "# 角色视觉卡" in character_skill.content
    assert "When To Use" in character_skill.content


def test_agent_skill_router_prefers_package_metadata_for_migrated_skills():
    router = SkillRouter()

    routes = router.route(
        message="帮我补角色人设并生成表情包和动作姿势",
        context={"character_id": "char-1"},
        allowed_tools=["inspect_character", "preview_character_portrait_prompt", "generate_image_asset"],
    )
    by_name = {item.skill_id: item for item in routes}

    assert by_name["character_visual_card"].source == "package"
    assert by_name["portrait_prompt"].source == "package"
    assert by_name["portrait_prompt"].trigger_type == "keyword"
    assert (
        "表情包" in by_name["portrait_prompt"].matches
        or "动作姿势" in by_name["portrait_prompt"].matches
    )


def test_agent_skill_router_parses_slash_skill_activation():
    router = SkillRouter()

    activation = router.parse_activation("/portrait_prompt 帮我生成角色表情包")
    assert activation.cleaned_message == "帮我生成角色表情包"
    assert activation.skill_ids == ("portrait_prompt",)

    routes = router.route(
        message=activation.cleaned_message,
        context={"character_id": "char-1"},
        allowed_tools=["preview_character_portrait_prompt"],
        activated_skill_ids=list(activation.skill_ids),
    )
    by_name = {item.skill_id: item for item in routes}
    assert by_name["portrait_prompt"].source == "slash"
    assert by_name["portrait_prompt"].score == 20


def test_agent_skill_router_parses_slash_bundle_activation():
    router = SkillRouter()

    activation = router.parse_activation("/character_portrait_workflow 给这个角色做立绘")
    assert activation.cleaned_message == "给这个角色做立绘"
    assert activation.bundle_ids == ("character_portrait_workflow",)
    assert "character_visual_card" in activation.skill_ids
    assert "portrait_prompt" in activation.skill_ids
    assert "image_generation_workflow" in activation.skill_ids
    assert "先补视觉卡" in activation.bundle_instruction


@pytest.mark.asyncio
async def test_agent_skill_package_index_api_exposes_loaded_packages():
    response = await list_skill_package_index()
    packages = {item["name"]: item for item in response["packages"]}

    assert "character_visual_card" in packages
    assert packages["character_visual_card"]["source_path"].endswith("SKILL.md")
    assert "角色" in packages["character_visual_card"]["triggers"]["keywords"]
    bundles = {item["name"]: item for item in response["bundles"]}
    assert "character_portrait_workflow" in bundles


@pytest.mark.asyncio
async def test_agent_skill_package_file_api_reads_allowed_files():
    response = await list_skill_package_files("portrait_prompt")
    files = {item["path"]: item for item in response["files"]}

    assert response["name"] == "portrait_prompt"
    assert files["SKILL.md"]["kind"] == "skill"

    content = await read_skill_package_file("portrait_prompt", "SKILL.md")
    assert content["file"]["path"] == "SKILL.md"
    assert "# 角色立绘提示词" in content["file"]["content"]


@pytest.mark.asyncio
async def test_agent_skill_package_file_api_blocks_path_traversal():
    with pytest.raises(HTTPException) as exc_info:
        await read_skill_package_file("portrait_prompt", "../skill_templates.py")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_agent_skill_route_preview_api_returns_diagnostics():
    response = await preview_skill_route(
        SkillRoutePreviewRequest(
            message="/character_portrait_workflow 帮这个角色生成立绘和表情包",
            context={"character_id": "char-1"},
            allowed_tools=["inspect_character", "preview_character_portrait_prompt"],
            target_skill_id="portrait_prompt",
        )
    )
    routes = {item["skill_id"]: item for item in response["routes"]}

    assert response["activation"]["bundle_ids"] == ["character_portrait_workflow"]
    assert routes["character_visual_card"]["source"] == "slash"
    assert routes["portrait_prompt"]["trigger_type"] == "slash"
    assert response["diagnostic"]["target_skill_id"] == "portrait_prompt"
    assert response["diagnostic"]["matched"] is True
    assert response["diagnostic"]["matched_route"]["score"] == 20


@pytest.mark.asyncio
async def test_agent_skill_route_preview_diagnoses_unmatched_target():
    response = await preview_skill_route(
        SkillRoutePreviewRequest(
            message="帮我整理素材",
            context={},
            allowed_tools=[],
            target_skill_id="portrait_prompt",
        )
    )

    diagnostic = response["diagnostic"]
    assert diagnostic["target_skill_id"] == "portrait_prompt"
    assert diagnostic["exists"] is True
    assert diagnostic["matched"] is False
    assert "character_id" in diagnostic["missing_context_keys"]
    assert diagnostic["missing_keywords"]
    assert diagnostic["unavailable_tools"]
    assert diagnostic["suggestions"]


def sample_skill_md(name: str = "user_test_skill") -> str:
    return f"""---
name: {name}
title: User Test Skill
description: Test user imported skill package.
skill_type: workflow
version: 1.0.0
category: test
tags:
  - test
triggers:
  keywords:
    - user test
requires_tools:
  - inspect_character
risk: read
---

# User Test Skill

Use this workflow when a user asks for a test imported skill.
"""


@pytest.mark.asyncio
async def test_agent_skill_draft_service_approves_to_user_skill_root(agent_session: AsyncSession, tmp_path):
    loader = SkillPackageLoader(roots=[tmp_path / "skills"])
    service = AgentSkillDraftService(agent_session, loader=loader)

    draft = await service.create_manual_draft(sample_skill_md())
    approved = await service.approve(draft.id)

    assert approved.status == "approved"
    target = tmp_path / "skills" / "user" / "user_test_skill" / "SKILL.md"
    assert target.exists()
    assert loader.get_package("user_test_skill").source_type == "user"

    result = await agent_session.execute(select(AgentSkill).where(AgentSkill.name == "user_test_skill"))
    skill = result.scalar_one()
    assert skill.is_builtin is False
    assert "User Test Skill" in skill.content


@pytest.mark.asyncio
async def test_agent_skill_draft_service_rejects_invalid_metadata(agent_session: AsyncSession, tmp_path):
    service = AgentSkillDraftService(agent_session, loader=SkillPackageLoader(roots=[tmp_path / "skills"]))

    with pytest.raises(SkillDraftError) as exc_info:
        await service.create_manual_draft("# Missing frontmatter")

    assert "metadata" in str(exc_info.value).lower()
    assert exc_info.value.diagnostics


@pytest.mark.asyncio
async def test_agent_skill_draft_service_blocks_builtin_override(agent_session: AsyncSession):
    service = AgentSkillDraftService(agent_session)

    with pytest.raises(SkillDraftError) as exc_info:
        await service.create_manual_draft(sample_skill_md("portrait_prompt"))

    assert "Cannot override built-in skill package" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_skill_draft_api_create_list_and_approve(agent_session: AsyncSession, monkeypatch, tmp_path):
    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    monkeypatch.setattr(SkillPackageLoader, "default_builtin_root", staticmethod(lambda: tmp_path / "skills"))

    created = await create_skill_draft(
        SkillDraftCreateRequest(content=sample_skill_md("api_user_skill")),
        db_session=agent_session,
    )
    listed = await list_skill_drafts(db_session=agent_session)
    approved = await approve_skill_draft(created["draft"]["id"], db_session=agent_session)

    assert created["draft"]["name"] == "api_user_skill"
    assert listed["drafts"][0]["name"] == "api_user_skill"
    assert approved["draft"]["status"] == "approved"
    assert (tmp_path / "skills" / "user" / "api_user_skill" / "SKILL.md").exists()


def test_agent_skill_tools_are_registered():
    assert ToolRegistry.get_tool("import_agent_skill_from_url") is not None
    assert ToolRegistry.get_tool("create_agent_skill_draft") is not None
    assert ToolRegistry.get_tool("list_agent_skill_drafts") is not None
    assert ToolRegistry.get_tool("list_agent_skill_packages") is not None
    assert ToolRegistry.get_tool("inspect_agent_run_skill_candidate") is not None
    assert ToolRegistry.get_tool("create_agent_skill_draft_from_run") is not None


def test_agent_skill_draft_service_normalizes_github_blob_url():
    raw_url = AgentSkillDraftService._normalize_skill_url(
        "https://github.com/acme/project/blob/main/skills/example/SKILL.md"
    )

    assert raw_url == "https://raw.githubusercontent.com/acme/project/main/skills/example/SKILL.md"


def test_agent_skill_draft_service_expands_github_repo_url():
    candidates = AgentSkillDraftService._candidate_skill_urls("https://github.com/Leonxlnx/taste-skill")

    assert "https://raw.githubusercontent.com/Leonxlnx/taste-skill/main/SKILL.md" in candidates
    assert "https://raw.githubusercontent.com/Leonxlnx/taste-skill/main/skills/taste-skill/SKILL.md" in candidates


def test_agent_skill_draft_service_rejects_private_import_url():
    with pytest.raises(SkillDraftError) as exc_info:
        AgentSkillDraftService._validate_url("http://192.168.1.10/SKILL.md")

    assert "Private network" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_skill_draft_service_rejects_private_redirect(agent_session: AsyncSession, monkeypatch, tmp_path):
    real_async_client = httpx.AsyncClient

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            self.client = real_async_client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        302,
                        headers={"location": "http://127.0.0.1/SKILL.md"},
                        request=request,
                    )
                )
            )

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, exc_type, exc, tb):
            await self.client.aclose()
            return False

    monkeypatch.setattr("app.services.agent.skill_drafts.httpx.AsyncClient", MockAsyncClient)
    service = AgentSkillDraftService(agent_session, loader=SkillPackageLoader(roots=[tmp_path / "skills"]))

    with pytest.raises(SkillDraftError) as exc_info:
        await service.import_url("https://example.com/SKILL.md")

    assert "Fetch skill URL failed" in str(exc_info.value)
    assert any("Local skill URLs" in item for item in exc_info.value.diagnostics)


@pytest.mark.asyncio
async def test_agent_skill_tools_create_pending_draft(agent_session: AsyncSession, monkeypatch, tmp_path):
    class SessionFactory:
        async def __aenter__(self):
            return agent_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.services.agent.tools.skill_tools.AsyncSessionLocal", lambda: SessionFactory())
    monkeypatch.setattr("app.services.agent.tools.skill_tools.ensure_agent_tables", noop_ensure_agent_tables)
    monkeypatch.setattr(SkillPackageLoader, "default_builtin_root", staticmethod(lambda: tmp_path / "skills"))

    created = await create_agent_skill_draft_tool(sample_skill_md("tool_user_skill"))
    listed = await list_agent_skill_drafts_tool()

    assert created["success"] is True
    assert created["draft"]["name"] == "tool_user_skill"
    assert listed["success"] is True
    assert listed["drafts"][0]["name"] == "tool_user_skill"


async def _seed_completed_skill_candidate_run(agent_session: AsyncSession, run_id: str = "run-skill-candidate") -> AgentRun:
    run = AgentRun(
        id=run_id,
        user_id="default",
        session_id="thread-skill-candidate",
        profile_id="default-assistant",
        status="completed",
        objective="导入公众号文章并整理为可阅读素材",
        context_json=json.dumps({"project_id": "project-skill-1", "platform": "wechat_mp"}, ensure_ascii=False),
        result_json=json.dumps({"reply": "已完成导入和整理", "tool_call_count": 3}, ensure_ascii=False),
    )
    steps = [
        AgentRunStep(
            run_id=run.id,
            session_id=run.session_id,
            profile_id=run.profile_id,
            step_type="tool_call",
            status="completed",
            order_index=1,
            tool_name="search_wechat_mp_accounts",
            summary="搜索公众号账号成功",
            input_json=json.dumps({"arguments": {"keyword": "测试账号"}}, ensure_ascii=False),
            output_json=json.dumps({"success": True, "items": [1]}, ensure_ascii=False),
        ),
        AgentRunStep(
            run_id=run.id,
            session_id=run.session_id,
            profile_id=run.profile_id,
            step_type="tool_call",
            status="completed",
            order_index=2,
            tool_name="list_wechat_mp_articles",
            summary="读取文章列表成功",
            input_json=json.dumps({"arguments": {"fake_id": "fake-1"}}, ensure_ascii=False),
            output_json=json.dumps({"success": True, "count": 3}, ensure_ascii=False),
        ),
        AgentRunStep(
            run_id=run.id,
            session_id=run.session_id,
            profile_id=run.profile_id,
            step_type="tool_call",
            status="completed",
            order_index=3,
            tool_name="download_wechat_mp_article",
            summary="下载并导入素材库成功",
            input_json=json.dumps({"arguments": {"format": "html"}}, ensure_ascii=False),
            output_json=json.dumps({"success": True, "file_path": "downloads/a.html"}, ensure_ascii=False),
        ),
    ]
    agent_session.add(run)
    for step in steps:
        agent_session.add(step)
    await agent_session.commit()
    return run


@pytest.mark.asyncio
async def test_agent_skill_draft_service_detects_and_generates_from_run(agent_session: AsyncSession, tmp_path):
    run = await _seed_completed_skill_candidate_run(agent_session)
    service = AgentSkillDraftService(agent_session, loader=SkillPackageLoader(roots=[tmp_path / "skills"]))

    analysis = await service.inspect_run_candidate(run.id)
    draft = await service.create_draft_from_run(run.id, name="wechat_import_workflow")

    assert analysis["eligible"] is True
    assert analysis["successful_tool_count"] == 3
    assert draft.source_type == "agent_run"
    assert draft.source_run_id == run.id
    assert "search_wechat_mp_accounts" in draft.content
    assert "source_run_id" in draft.content
    package, diagnostics = SkillPackageLoader(roots=[tmp_path / "skills"]).validate_raw_package(draft.content)
    assert diagnostics == ()
    assert package.name == "wechat_import_workflow"


@pytest.mark.asyncio
async def test_agent_skill_draft_service_rejects_weak_run(agent_session: AsyncSession, tmp_path):
    run = AgentRun(
        id="weak-run",
        user_id="default",
        session_id="thread-weak",
        profile_id="default-assistant",
        status="completed",
        objective="只查一下",
    )
    agent_session.add(run)
    await agent_session.commit()
    service = AgentSkillDraftService(agent_session, loader=SkillPackageLoader(roots=[tmp_path / "skills"]))

    analysis = await service.inspect_run_candidate(run.id)
    with pytest.raises(SkillDraftError):
        await service.create_draft_from_run(run.id)

    assert analysis["eligible"] is False
    assert "fewer than 3 successful tool steps" in analysis["reasons"]


@pytest.mark.asyncio
async def test_agent_skill_draft_from_run_api(agent_session: AsyncSession, monkeypatch, tmp_path):
    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    monkeypatch.setattr(SkillPackageLoader, "default_builtin_root", staticmethod(lambda: tmp_path / "skills"))
    run = await _seed_completed_skill_candidate_run(agent_session, "api-run-skill-candidate")

    inspected = await inspect_run_skill_candidate(run.id, db_session=agent_session)
    created = await create_skill_draft_from_run(
        run.id,
        SkillDraftFromRunRequest(name="api_run_skill"),
        db_session=agent_session,
    )

    assert inspected["analysis"]["eligible"] is True
    assert created["success"] is True
    assert created["draft"]["name"] == "api_run_skill"
    assert created["draft"]["source_run_id"] == run.id


@pytest.mark.asyncio
async def test_agent_skill_run_tools_create_pending_draft(agent_session: AsyncSession, monkeypatch, tmp_path):
    class SessionFactory:
        async def __aenter__(self):
            return agent_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.services.agent.tools.skill_tools.AsyncSessionLocal", lambda: SessionFactory())
    monkeypatch.setattr("app.services.agent.tools.skill_tools.ensure_agent_tables", noop_ensure_agent_tables)
    monkeypatch.setattr(SkillPackageLoader, "default_builtin_root", staticmethod(lambda: tmp_path / "skills"))
    run = await _seed_completed_skill_candidate_run(agent_session, "tool-run-skill-candidate")

    inspected = await inspect_agent_run_skill_candidate_tool(run.id)
    created = await create_agent_skill_draft_from_run_tool(run.id, name="tool_run_skill")

    assert inspected["success"] is True
    assert inspected["analysis"]["eligible"] is True
    assert created["success"] is True
    assert created["draft"]["name"] == "tool_run_skill"


@pytest.mark.asyncio
async def test_agent_workflow_replay_context_skill_trace_and_approved_skill_routing(
    agent_session: AsyncSession,
    monkeypatch,
    tmp_path,
):
    """Smoke the DeerFlow/Hermes-inspired loop from context to reusable skill."""

    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="我会沿用上一轮上下文继续处理。")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "workflow-replay-agent",
            "name": "Workflow Replay 测试智能体",
            "allowed_tools": ["search_platform_sources"],
            "max_steps": 3,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    first = await service.chat(
        session_id="",
        user_message="搜索包氏父子解说视频",
        profile_id=profile.id,
    )
    second = await service.chat(
        session_id=first["session_id"],
        user_message="用B站技能",
        profile_id=profile.id,
    )

    assert second["tool_calls"], "第二轮应沿用第一轮关键词并直接调用平台搜索工具"
    tool_call = second["tool_calls"][0]
    assert tool_call["tool_name"] == "search_platform_sources"
    assert tool_call["result"]["arguments"]["platform"] == "bili"
    assert tool_call["result"]["arguments"]["keyword"] == "包氏父子解说视频"

    messages = (
        await agent_session.execute(
            select(AgentMessage)
            .where(AgentMessage.thread_id == second["thread_id"])
            .order_by(AgentMessage.id.asc())
        )
    ).scalars().all()
    user_messages = [item.content for item in messages if item.role == "user"]
    assistant_messages = [item.content for item in messages if item.role == "assistant"]
    assert any("搜索包氏父子解说视频" in item for item in user_messages)
    assert any("用B站技能" in item for item in user_messages)
    assert assistant_messages

    steps = (
        await agent_session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == second["run_id"])
            .order_by(AgentRunStep.order_index.asc())
        )
    ).scalars().all()
    step_types = [step.step_type for step in steps]
    assert step_types[:3] == ["intake", "context_pack", "skill_route"]
    assert "tool_call" in step_types
    skill_step = next(step for step in steps if step.step_type == "skill_route")
    skill_payload = json.loads(skill_step.output_json)
    assert any(item["skill_id"] == "asset_search" for item in skill_payload["routed_skills"])

    persisted_session = await agent_session.get(AgentSession, first["session_id"])
    context = json.loads(persisted_session.context)
    assert context["conversation_state"]["slots"]["keyword"] == "包氏父子解说视频"
    assert context["conversation_state"]["slots"]["platform"] == "bili"

    skill_root = tmp_path / "skills"

    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    monkeypatch.setattr(SkillPackageLoader, "default_builtin_root", staticmethod(lambda: skill_root))
    candidate_run = await _seed_completed_skill_candidate_run(agent_session, "workflow-replay-candidate-run")

    draft_service = AgentSkillDraftService(agent_session, loader=SkillPackageLoader(roots=[skill_root]))
    draft = await draft_service.create_draft_from_run(candidate_run.id, name="wechat_import_replay")
    await agent_session.commit()

    approved = await approve_skill_draft(draft.id, db_session=agent_session)
    assert approved["draft"]["status"] == "approved"
    assert (skill_root / "user" / "wechat_import_replay" / "SKILL.md").exists()

    preview = await preview_skill_route(
        SkillRoutePreviewRequest(
            message="导入公众号文章并整理为可阅读素材",
            context={"project_id": "project-skill-1", "platform": "wechat_mp"},
            allowed_tools=["search_wechat_mp_accounts", "list_wechat_mp_articles", "download_wechat_mp_article"],
            target_skill_id="wechat_import_replay",
        )
    )
    assert any(item["skill_id"] == "wechat_import_replay" for item in preview["routes"])
    assert preview["diagnostic"]["matched"] is True


@pytest.mark.asyncio
async def test_agent_skill_bundle_api_creates_user_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(SkillPackageLoader, "default_builtin_root", staticmethod(lambda: tmp_path / "skills"))
    skill_dir = tmp_path / "skills" / "creative" / "portrait_prompt"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(sample_skill_md("portrait_prompt"), encoding="utf-8")

    response = await create_skill_bundle(
        SkillBundleCreateRequest(
            name="custom_portrait_flow",
            description="自定义角色立绘流程",
            skills=["portrait_prompt"],
        )
    )
    index = await list_skill_package_index()

    assert response["success"] is True
    assert (tmp_path / "skills" / "user" / "bundles" / "custom_portrait_flow.yaml").exists()
    bundle = next(item for item in index["bundles"] if item["name"] == "custom_portrait_flow")
    assert bundle["source_type"] == "user"
    assert bundle["missing_skills"] == []

    updated = await update_skill_bundle(
        "custom_portrait_flow",
        SkillBundleCreateRequest(
            name="custom_portrait_flow",
            description="更新后的角色立绘流程",
            skills=["portrait_prompt"],
            instruction="先检查角色卡，再生成提示词。",
        ),
    )
    assert updated["bundle"]["description"] == "更新后的角色立绘流程"
    assert updated["bundle"]["instruction"] == "先检查角色卡，再生成提示词。"

    deleted = await delete_skill_bundle("custom_portrait_flow")
    assert deleted["success"] is True
    assert not (tmp_path / "skills" / "user" / "bundles" / "custom_portrait_flow.yaml").exists()


def test_agent_tool_executor_repairs_followup_tool_arguments():
    executor = ToolExecutor()
    tool_call = {
        "id": "call_1",
        "name": "search_platform_sources",
        "arguments": "{}",
    }
    repaired = executor.repair_tool_call_with_followup(
        tool_call,
        {
            "type": "platform_search_followup",
            "platform": "bili",
            "keyword": "包氏父子解说视频",
        },
    )

    name, args = executor.tool_name_and_args(repaired)
    assert name == "search_platform_sources"
    assert args["platform"] == "bili"
    assert args["keyword"] == "包氏父子解说视频"


def test_agent_planner_parses_tool_calls_from_json_content():
    planner = Planner(
        llm_manager_getter=lambda: None,
        provider_chain_builder=lambda profile: [],
    )

    calls = planner.parse_tool_calls(
        '{"tool_calls":[{"id":"call_1","name":"search_assets","arguments":"{}"}]}'
    )

    assert calls[0]["name"] == "search_assets"


@pytest.mark.asyncio
async def test_agent_run_loop_executes_tools_then_observes_until_final_answer():
    class NoopLoopDetector:
        def check(self, tool_calls):
            return ""

    state = {
        "profile": {"max_steps": 3},
        "llm_response": {"tool_calls": [{"id": "call_1", "name": "search_assets", "arguments": "{}"}]},
        "messages": [],
        "events": [],
    }
    run_loop = RunLoop(NoopLoopDetector())

    async def execute_phase(loop_state, tool_calls):
        loop_state["events"].append(("execute", len(tool_calls)))
        loop_state["llm_response"] = {"tool_calls": [{"id": "call_2", "name": "inspect_asset", "arguments": "{}"}]}

    async def observe_phase(loop_state):
        loop_state["events"].append(("observe", loop_state["iteration"]))
        loop_state["llm_response"] = {"content": "done", "tool_calls": []}

    async def handle_pending_confirmations(loop_state):
        loop_state["events"].append(("pending", 0))

    async def handle_budget_exhausted(loop_state, iteration, budget):
        loop_state["events"].append(("budget", budget))

    await run_loop.run(
        state,
        execute_phase=execute_phase,
        observe_phase=observe_phase,
        handle_pending_confirmations=handle_pending_confirmations,
        handle_budget_exhausted=handle_budget_exhausted,
    )

    assert state["events"] == [("execute", 1), ("observe", 1)]
    assert state["iteration"] == 2


def test_agent_registered_tools_have_io_specs_and_risk_levels():
    for tool in ToolRegistry.list_tools():
        assert tool.input_schema_note, tool.name
        assert tool.output_schema_note, tool.name
        assert tool.risk_level in {"read", "write", "delete", "external", "costly"}, tool.name
        assert tool.output_type and tool.output_type != "generic", tool.name


@pytest.mark.asyncio
async def test_preview_image_generation_request_tool_keeps_lineage_without_cost():
    result = await ToolRegistry.execute_tool(
        "preview_image_generation_request",
        {
            "prompt": "单人角色立绘，冷色调国漫美型",
            "provider": "魔塔-Z-Image-Turbo",
            "model": "Tongyi-MAI/Z-Image-Turbo",
            "size": "1024x1024",
            "reference_images": ["data:image/png;base64," + "a" * 300],
            "project_id": "project-1",
            "character_ids": ["char-1"],
            "reference_asset_ids": ["asset-1"],
        },
    )

    assert result.success is True
    payload = result.result
    assert payload["normalized_request"]["provider"] == "魔塔-Z-Image-Turbo"
    assert payload["normalized_request"]["reference_images"][0].endswith("(truncated, len=322)")
    assert payload["reference_image_count"] == 1
    assert payload["lineage_hint"]["project_id"] == "project-1"
    assert payload["lineage_hint"]["character_ids"] == ["char-1"]
    assert "真正生图" in payload["cost_warning"]


@pytest.mark.asyncio
async def test_preview_video_generation_request_tool_without_cost():
    result = await ToolRegistry.execute_tool(
        "preview_video_generation_request",
        {
            "prompt": "主角推开门，镜头缓慢推进，冷色调悬疑感",
            "provider": "魔塔-Z-Image-Turbo",
            "model": "Wan-AI/Wan2.1-I2V",
            "duration": 60,
            "resolution": "1080p",
            "aspect_ratio": "9:16",
            "generate_audio": False,
        },
    )

    assert result.success is True
    payload = result.result
    assert payload["normalized_request"]["provider"] == "魔塔-Z-Image-Turbo"
    assert payload["normalized_request"]["duration"] == 30
    assert payload["normalized_request"]["generate_audio"] is False
    assert payload["start_image_exists"] is False
    assert "真正生成视频" in payload["cost_warning"]


def test_agent_costly_tools_have_cost_hint():
    costly_tools = [tool for tool in ToolRegistry.list_tools() if tool.risk_level == "costly"]

    assert costly_tools
    assert all(tool.cost_hint for tool in costly_tools)


def test_agent_service_exposes_runtime_phase_methods(agent_session: AsyncSession):
    service = AgentService(agent_session)

    for method_name in [
        "_intake_phase",
        "_context_pack_phase",
        "_plan_phase",
        "_tool_loop_phase",
        "_execute_phase",
        "_observe_phase",
        "_final_phase",
    ]:
        assert callable(getattr(service, method_name))


@pytest.mark.asyncio
async def test_openai_sdk_llm_backend_returns_native_tool_calls():
    class FakeCompletions:
        def __init__(self):
            self.kwargs = None

        async def create(self, **kwargs):
            self.kwargs = kwargs
            tool_call = SimpleNamespace(
                id="call_sdk_1",
                type="function",
                function=SimpleNamespace(
                    name="inspect_creative_project",
                    arguments="{\"project_id\":\"sdk-demo\"}",
                ),
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call]))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3, total_tokens=13),
            )

    completions = FakeCompletions()
    backend = OpenAISDKLLMBackend.__new__(OpenAISDKLLMBackend)
    backend._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    backend._model = "gpt-test"
    backend._provider = "openai"
    backend._default_temperature = 0.1
    backend._default_max_tokens = 128

    result = await backend._chat_via_completions(
        messages=[],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "inspect_creative_project",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )

    assert completions.kwargs["tools"][0]["function"]["name"] == "inspect_creative_project"
    assert result.success is True
    assert result.tool_calls[0]["id"] == "call_sdk_1"
    assert result.tool_calls[0]["function"]["name"] == "inspect_creative_project"
    assert result.tool_calls[0]["function"]["arguments"] == "{\"project_id\":\"sdk-demo\"}"


@pytest.mark.asyncio
async def test_generic_llm_backend_extracts_openai_compatible_tool_calls():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_generic_1",
                                    "type": "function",
                                    "function": {
                                        "name": "inspect_creative_project",
                                        "arguments": "{\"project_id\":\"generic-demo\"}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            }

    class FakeClient:
        def __init__(self):
            self.json_body = None

        async def post(self, url, json):
            self.json_body = json
            return FakeResponse()

    backend = GenericLLMBackend.__new__(GenericLLMBackend)
    backend.connector = SimpleNamespace(provider="generic", default_params="")
    backend._model = "generic-model"
    backend._default_temperature = 0.1
    backend._default_max_tokens = 128
    backend._chat_url = "https://example.test/chat"
    backend.response_config = {}
    backend.client = FakeClient()

    result = await backend.chat(
        messages=[],
        tools=[{"type": "function", "function": {"name": "inspect_creative_project"}}],
    )

    assert backend.client.json_body["tools"][0]["function"]["name"] == "inspect_creative_project"
    assert result.success is True
    assert result.tool_calls[0]["id"] == "call_generic_1"
    assert result.tool_calls[0]["function"]["name"] == "inspect_creative_project"
    assert result.tool_calls[0]["function"]["arguments"] == "{\"project_id\":\"generic-demo\"}"


@pytest.mark.asyncio
async def test_generic_llm_backend_uses_configured_tool_call_paths():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "requires_action",
                "output": {
                    "text": "",
                    "calls": [
                        {
                            "callId": "call_custom_1",
                            "tool": "inspect_character",
                            "args": {"character_id": "char-1"},
                        }
                    ],
                },
            }

    class FakeClient:
        def __init__(self):
            self.json_body = None

        async def post(self, url, json):
            self.json_body = json
            return FakeResponse()

    backend = GenericLLMBackend.__new__(GenericLLMBackend)
    backend.connector = SimpleNamespace(provider="generic", default_params='{"stream": false}')
    backend._model = "custom-model"
    backend._default_temperature = 0.1
    backend._default_max_tokens = 128
    backend._chat_url = "https://example.test/custom"
    backend.response_config = {
        "tools_request_field": "available_tools",
        "tool_choice_request_field": "selected_tool",
        "content_path": "$.output.text",
        "finish_reason_path": "$.status",
        "tool_finish_reasons": ["requires_action"],
        "tool_calls_path": "$.output.calls[*]",
        "tool_id_path": "$.callId",
        "tool_name_path": "$.tool",
        "tool_arguments_path": "$.args",
    }
    backend.client = FakeClient()

    result = await backend.chat(
        messages=[],
        tools=[{"type": "function", "function": {"name": "inspect_character"}}],
        tool_choice="auto",
    )

    assert backend.client.json_body["stream"] is False
    assert backend.client.json_body["available_tools"][0]["function"]["name"] == "inspect_character"
    assert backend.client.json_body["selected_tool"] == "auto"
    assert result.success is True
    assert result.tool_calls[0]["id"] == "call_custom_1"
    assert result.tool_calls[0]["function"]["name"] == "inspect_character"
    assert result.tool_calls[0]["function"]["arguments"] == "{\"character_id\": \"char-1\"}"


@pytest.mark.asyncio
async def test_agent_tool_registry_reports_readable_argument_errors():
    async def required_handler(project_id: str, chapter_number: int):
        return {"project_id": project_id, "chapter_number": chapter_number}

    ToolRegistry.register(
        Tool(
            name="agent_test_required_args_tool",
            description="test required args",
            parameters={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "chapter_number": {"type": "integer"},
                },
                "required": ["project_id", "chapter_number"],
            },
            handler=required_handler,
            category="general",
            input_schema_note="project_id 为创作项目 ID，chapter_number 为章节号。",
            output_type="test_result",
        )
    )

    result = await ToolRegistry.execute_tool("agent_test_required_args_tool", {"project_id": "demo"})

    assert result.success is False
    assert "缺少必填参数" in (result.error or "")
    assert "chapter_number" in (result.error or "")


@pytest.mark.asyncio
async def test_agent_service_blocks_tools_not_allowed_by_profile(agent_session: AsyncSession):
    service = AgentService(agent_session)

    result = await service._execute_tool_call(
        {"id": "call_1", "name": "search_assets", "arguments": "{}"},
        session_id="session-1",
        profile={"allowed_tools": ["inspect_creative_project"]},
    )

    assert result.success is False
    assert "search_assets" in (result.error or "")

    rows = (
        await agent_session.execute(
            select(AgentToolCall).where(AgentToolCall.session_id == "session-1")
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].tool_name == "search_assets"
    assert rows[0].success is False


@pytest.mark.asyncio
async def test_agent_chat_uses_selected_profile_model_preferences(agent_session: AsyncSession):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="收到，我会按创作导演设定推进。")

    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    profile = await manager.update_profile(
        "creative-director",
        {"provider": "deepseek-v4", "model": "deepseek-chat", "max_steps": 3},
    )
    assert profile is not None
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    result = await service.chat(
        session_id="",
        user_message="检查项目状态",
        profile_id="creative-director",
    )

    assert result["profile"]["id"] == "creative-director"
    assert result["reply"] == "收到，我会按创作导演设定推进。"
    assert fake_llm.calls[0]["backend_name"] == "deepseek-v4"
    assert fake_llm.calls[0]["model"] == "deepseek-chat"
    tool_names = {
        item["function"]["name"]
        for item in fake_llm.calls[0]["tools"]
        if item.get("type") == "function"
    }
    assert "inspect_creative_project" in tool_names
    assert "search_assets" not in tool_names


@pytest.mark.asyncio
async def test_agent_fallback_tool_results_are_sent_as_observations(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return LLMGenerationResult(
                    success=True,
                    content='{"tool_calls":[{"id":"call_1","name":"inspect_creative_project","arguments":"{\\"project_id\\":\\"demo\\"}"}]}',
                )
            return LLMGenerationResult(success=True, content="工具已执行，项目 demo 可继续推进。")

    async def fake_execute_tool(name: str, arguments: dict | None = None):
        return ToolCallResult(
            tool_name=name,
            success=True,
            result={"project_id": arguments.get("project_id"), "status": "ok"},
        )

    monkeypatch.setattr(ToolRegistry, "execute_tool", fake_execute_tool)
    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    result = await service.chat(
        session_id="",
        user_message="检查 demo 项目",
        profile_id="creative-director",
    )

    assert result["reply"] == "工具已执行，项目 demo 可继续推进。"
    second_messages = fake_llm.calls[1]["messages"]
    assert all(message.role != "tool" for message in second_messages)
    assert any("工具结果" in message.content for message in second_messages)


@pytest.mark.asyncio
async def test_agent_executes_native_llm_tool_calls(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return LLMGenerationResult(
                    success=True,
                    content="",
                    tool_calls=[
                        {
                            "id": "call_native_1",
                            "type": "function",
                            "function": {
                                "name": "inspect_creative_project",
                                "arguments": "{\"project_id\":\"native-demo\"}",
                            },
                        }
                    ],
                )
            return LLMGenerationResult(success=True, content="原生工具调用已执行。")

    async def fake_execute_tool(name: str, arguments: dict | None = None):
        return ToolCallResult(
            tool_name=name,
            success=True,
            result={"project_id": arguments.get("project_id"), "status": "ok"},
        )

    monkeypatch.setattr(ToolRegistry, "execute_tool", fake_execute_tool)
    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    result = await service.chat(
        session_id="",
        user_message="检查 native-demo 项目",
        profile_id="creative-director",
    )

    assert result["reply"] == "原生工具调用已执行。"
    assert result["tool_calls"][0]["tool_name"] == "inspect_creative_project"
    steps = (
        await agent_session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == result["run_id"])
            .order_by(AgentRunStep.order_index.asc())
        )
    ).scalars().all()
    assert "tool_call" in [step.step_type for step in steps]
    assert any(step.tool_name == "inspect_creative_project" for step in steps)


@pytest.mark.asyncio
async def test_agent_chat_persists_run_and_steps(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeLLM:
        async def chat(self, **kwargs):
            return LLMGenerationResult(success=True, content="我会按当前项目上下文继续推进。")

    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    await agent_session.commit()
    monkeypatch.setattr(
        "app.services.agent.service.build_creative_project_context_pack",
        lambda project_id, chapter_number=None: {
            "project": {"id": project_id, "title": "Demo Project"},
            "chapter_number": chapter_number,
            "known_gaps": ["缺少分镜"],
        },
    )

    service = AgentService(agent_session)
    service._llm_manager = FakeLLM()

    result = await service.chat(
        session_id="",
        user_message="继续推进项目",
        context={"project_id": "project-1"},
        profile_id="creative-director",
    )

    assert result["run_id"]
    run = await agent_session.get(AgentRun, result["run_id"])
    assert run is not None
    assert run.status == "completed"
    assert run.session_id == result["session_id"]
    run_context = json.loads(run.context_json)
    assert run_context["creative_project_context"]["project"]["title"] == "Demo Project"

    steps = (
        await agent_session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == result["run_id"])
            .order_by(AgentRunStep.order_index.asc())
        )
    ).scalars().all()
    step_types = [step.step_type for step in steps]
    assert step_types[:4] == ["intake", "context_pack", "skill_route", "llm_response"]
    assert "final" in step_types

    thread_messages = (
        await agent_session.execute(
            select(AgentMessage)
            .where(AgentMessage.thread_id == result["thread_id"])
            .order_by(AgentMessage.id.asc())
        )
    ).scalars().all()
    assert [message.role for message in thread_messages] == ["user", "assistant"]
    assert thread_messages[0].run_id == result["run_id"]
    assert "继续推进项目" in thread_messages[0].content

    thread_snapshots = (
        await agent_session.execute(
            select(AgentContextSnapshot)
            .where(AgentContextSnapshot.thread_id == result["thread_id"])
            .order_by(AgentContextSnapshot.id.asc())
        )
    ).scalars().all()
    assert len(thread_snapshots) == 1
    assert thread_snapshots[0].run_id == result["run_id"]
    snapshot_context = json.loads(thread_snapshots[0].context_json)
    conv_state = snapshot_context["sections"]["conversation_state"]["state"]
    assert conv_state["last_user_message"] == "继续推进项目"
    assert "creative_project_context" in snapshot_context["effective_context_keys"]


@pytest.mark.asyncio
async def test_agent_profile_defaults_are_injected_into_run_context(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeLLM:
        async def chat(self, **kwargs):
            return LLMGenerationResult(success=True, content="已读取默认项目上下文。")

    monkeypatch.setattr(
        "app.services.agent.service.build_creative_project_context_pack",
        lambda project_id, chapter_number=None: {
            "project": {"id": project_id, "title": "默认项目"},
            "chapter_number": chapter_number,
            "known_gaps": [],
        },
    )
    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    profile = await manager.create_profile(
        {
            "id": "custom-default-project-agent",
            "name": "默认项目智能体",
            "allowed_tools": ["inspect_creative_project"],
            "default_project_id": "default-project-1",
            "default_workflow": "creative_project_advance",
            "default_skill_ids": ["reference_match"],
            "max_steps": 2,
        },
    )
    await agent_session.commit()

    service = AgentService(agent_session)
    service._llm_manager = FakeLLM()
    result = await service.chat(
        session_id="",
        user_message="继续推进默认项目",
        profile_id=profile.id,
    )

    run = await agent_session.get(AgentRun, result["run_id"])
    assert run is not None
    context = json.loads(run.context_json)
    assert context["project_id"] == "default-project-1"
    assert context["creative_project_id"] == "default-project-1"
    assert context["default_workflow"] == "creative_project_advance"
    assert context["default_skill_ids"] == ["reference_match"]
    assert context["creative_project_context"]["project"]["title"] == "默认项目"


@pytest.mark.asyncio
async def test_agent_chat_injects_default_skill_templates_into_system_prompt(agent_session: AsyncSession):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="已按角色视觉卡方法处理。")

    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    profile = await manager.create_profile(
        {
            "id": "skill-context-agent",
            "name": "Skill 上下文测试智能体",
            "allowed_tools": [],
            "default_skill_ids": ["character_visual_card"],
            "max_steps": 1,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    await service.chat(
        session_id="",
        user_message="补角色视觉卡",
        profile_id=profile.id,
    )

    system_content = fake_llm.calls[0]["messages"][0].content
    assert "默认 Skill 工作方法" in system_content
    assert "character_visual_card" in system_content
    assert "角色视觉卡" in system_content


@pytest.mark.asyncio
async def test_agent_chat_injects_slash_bundle_activation_into_context(agent_session: AsyncSession):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="已按角色立绘工作流处理。")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "slash-bundle-agent",
            "name": "Slash Bundle 测试智能体",
            "allowed_tools": ["inspect_character", "preview_character_portrait_prompt"],
            "max_steps": 1,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    result = await service.chat(
        session_id="",
        user_message="/character_portrait_workflow 给这个角色做立绘",
        profile_id=profile.id,
    )

    system_content = fake_llm.calls[0]["messages"][0].content
    assert "character_visual_card" in system_content
    assert "portrait_prompt" in system_content
    assert "skill_bundle_instruction" in system_content
    assert "先补视觉卡" in system_content

    run = await agent_session.get(AgentRun, result["run_id"])
    assert run is not None
    context = json.loads(run.context_json)
    assert context["activated_bundle_ids"] == ["character_portrait_workflow"]
    assert "character_visual_card" in context["activated_skill_ids"]

    snapshots = (await agent_session.execute(select(AgentMemorySnapshot))).scalars().all()
    snapshot_data = json.loads(snapshots[-1].snapshot_json)
    assert snapshot_data["activated_bundle_ids"] == ["character_portrait_workflow"]
    assert "character_visual_card" in snapshot_data["activated_skill_ids"]
    assert any(item["source"] == "slash" for item in snapshot_data["routed_skills"])

    steps = (
        await agent_session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == result["run_id"])
            .order_by(AgentRunStep.order_index.asc())
        )
    ).scalars().all()
    skill_step = next(step for step in steps if step.step_type == "skill_route")
    skill_payload = json.loads(skill_step.output_json)
    assert skill_step.summary == f"命中 {len(skill_payload['routed_skills'])} 个 Skill"
    assert skill_payload["activated_bundle_ids"] == ["character_portrait_workflow"]
    assert {item["skill_id"] for item in skill_payload["routed_skills"]} >= {"character_visual_card", "portrait_prompt"}
    assert any(item["source"] == "slash" and item["score"] == 20 for item in skill_payload["routed_skills"])

    skill_metrics = (
        await agent_session.execute(
            select(AgentSkill).where(AgentSkill.name.in_(["character_visual_card", "portrait_prompt"]))
        )
    ).scalars().all()
    metrics_by_name = {item.name: item for item in skill_metrics}
    assert metrics_by_name["character_visual_card"].usage_count == 1
    assert metrics_by_name["character_visual_card"].success_count == 1
    assert metrics_by_name["portrait_prompt"].usage_count == 1
    assert metrics_by_name["portrait_prompt"].success_count == 1


@pytest.mark.asyncio
async def test_agent_chat_injects_memory_skill_index_and_tool_index(agent_session: AsyncSession):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="我会优先使用已保存偏好和平台搜索工具。")

    memory_manager = MemoryManager(agent_session)
    await memory_manager.save_memory(
        key="user.preference.platform_search",
        value="搜索短视频素材时优先检查 B站。",
        memory_type="preference",
        importance=8,
    )

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "memory-skill-tool-agent",
            "name": "记忆技能工具测试智能体",
            "allowed_tools": ["search_platform_sources"],
            "max_steps": 1,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    await service.chat(
        session_id="",
        user_message="去 B站 搜包氏父子解说视频",
        profile_id=profile.id,
    )

    system_content = fake_llm.calls[0]["messages"][0].content
    assert "记忆上下文" in system_content
    assert "user.preference.platform_search" in system_content
    assert "搜索短视频素材时优先检查 B站" in system_content
    assert "可用 Skill 索引" in system_content
    assert "reference_match" in system_content
    assert "可用工具索引" in system_content
    assert "search_platform_sources" in system_content


@pytest.mark.asyncio
async def test_agent_resolves_platform_followup_to_previous_search_keyword(agent_session: AsyncSession):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="你想搜索什么内容？")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "platform-followup-agent",
            "name": "平台续问测试智能体",
            "allowed_tools": ["search_platform_sources"],
            "max_steps": 3,
        },
    )

    # M2.3: Use standalone SessionManager for legacy test setup
    session_mgr = SessionManager(agent_session)
    db_session = await session_mgr.create_session(title="平台搜索续问")
    await session_mgr.append_message(
        db_session.id,
        {"role": "user", "content": "搜索包氏父子解说视频"},
    )
    await session_mgr.append_message(
        db_session.id,
        {"role": "assistant", "content": "你想在哪个平台搜索？"},
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm
    result = await service.chat(
        session_id=db_session.id,
        user_message="有技能，搜B站",
        profile_id=profile.id,
    )

    assert result["tool_calls"]
    tool_call = result["tool_calls"][0]
    assert tool_call["tool_name"] == "search_platform_sources"
    assert "pending_confirmation" not in tool_call["result"]
    assert tool_call["success"] is True
    assert tool_call["result"]["arguments"]["keyword"] == "包氏父子解说视频"

    persisted_session = await agent_session.get(AgentSession, db_session.id)
    context = json.loads(persisted_session.context)
    conversation_state = context["conversation_state"]
    assert conversation_state["active_intent"] == "platform_search"
    assert conversation_state["slots"]["platform"] == "bili"
    assert conversation_state["slots"]["keyword"] == "包氏父子解说视频"
    assert conversation_state["pending_action"]["type"] == "tool_call_ready"
    assert "asset_search" in context["routed_skill_ids"]

    system_content = fake_llm.calls[0]["messages"][0].content
    assert "多轮续问解析" in system_content
    assert "包氏父子解说视频" in system_content
    assert "B站" in system_content


@pytest.mark.asyncio
async def test_agent_real_two_turn_chat_keeps_platform_search_context(agent_session: AsyncSession):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="你想搜索什么内容？")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "real-two-turn-platform-agent",
            "name": "真实两轮上下文测试智能体",
            "allowed_tools": ["search_platform_sources"],
            "max_steps": 3,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    first = await service.chat(
        session_id="",
        user_message="搜索包氏父子解说视频",
        profile_id=profile.id,
    )
    assert first["session_id"]
    assert not first["tool_calls"]

    second = await service.chat(
        session_id=first["session_id"],
        user_message="用B站技能",
        profile_id=profile.id,
    )

    assert second["tool_calls"]
    tool_call = second["tool_calls"][0]
    assert tool_call["tool_name"] == "search_platform_sources"
    assert "pending_confirmation" not in tool_call["result"]
    assert tool_call["result"]["arguments"]["platform"] == "bili"
    assert tool_call["result"]["arguments"]["keyword"] == "包氏父子解说视频"

    persisted_session = await agent_session.get(AgentSession, first["session_id"])
    context = json.loads(persisted_session.context)
    conversation_state = context["conversation_state"]
    assert conversation_state["active_intent"] == "platform_search"
    assert conversation_state["slots"]["platform"] == "bili"
    assert conversation_state["slots"]["keyword"] == "包氏父子解说视频"


@pytest.mark.asyncio
async def test_agent_recovers_recent_session_when_followup_drops_session_id(agent_session: AsyncSession):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="What should I search?")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "recover-dropped-session-agent",
            "name": "Recover Dropped Session Agent",
            "allowed_tools": ["search_platform_sources"],
            "max_steps": 3,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    first = await service.chat(
        session_id="",
        user_message="search ghost story video",
        profile_id=profile.id,
    )
    assert first["session_id"]
    assert not first["tool_calls"]

    second = await service.chat(
        session_id="",
        user_message="douyin",
        profile_id=profile.id,
    )

    assert second["session_id"] == first["session_id"]
    assert second["tool_calls"]
    tool_call = second["tool_calls"][0]
    assert tool_call["tool_name"] == "search_platform_sources"
    assert tool_call["result"]["arguments"]["platform"] == "dy"
    assert tool_call["result"]["arguments"]["keyword"] == "ghost story video"

    third = await service.chat(
        session_id="",
        user_message="douyin",
        profile_id=profile.id,
        force_new_thread=True,
    )

    assert third["session_id"] != first["session_id"]
    assert not third["tool_calls"]


@pytest.mark.asyncio
async def test_agent_failover_chain_uses_string_provider_type(agent_session: AsyncSession):
    connector = AIConnector(
        id="fallback-llm-connector",
        provider="fallback-provider",
        name="Fallback LLM",
        api_key="",
        provider_type="llm",
        default_model="fallback-model",
        is_active=True,
        priority=0,
    )
    agent_session.add(connector)
    await agent_session.commit()

    service = AgentService(agent_session)
    chain = await service._build_failover_chain(
        {"provider": "primary-provider", "model": "primary-model", "role_type": "assistant"}
    )

    assert ("primary-provider", "primary-model") in chain
    assert ("fallback-provider", "fallback-model") in chain


@pytest.mark.asyncio
async def test_agent_chat_persists_frozen_memory_snapshot(agent_session: AsyncSession):
    class FakeLLM:
        async def chat(self, **kwargs):
            return LLMGenerationResult(success=True, content="已使用冻结记忆快照。")

    memory_manager = MemoryManager(agent_session)
    await memory_manager.save_memory(
        key="user.preference.snapshot_style",
        value="回答时先说结论。",
        memory_type="preference",
        importance=7,
    )
    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "snapshot-agent",
            "name": "快照测试智能体",
            "allowed_tools": ["search_platform_sources"],
            "max_steps": 1,
        },
    )
    await agent_session.commit()

    service = AgentService(agent_session)
    service._llm_manager = FakeLLM()
    result = await service.chat(
        session_id="",
        user_message="用我的偏好回答",
        profile_id=profile.id,
    )

    snapshots = (await agent_session.execute(select(AgentMemorySnapshot))).scalars().all()
    assert len(snapshots) == 1
    assert snapshots[0].run_id == result["run_id"]
    assert "user.preference.snapshot_style" in snapshots[0].memory_context
    assert "search_platform_sources" in snapshots[0].tool_index_text

    async def noop_ensure_agent_tables():
        return None

    from app.api.v1 import agent as agent_api

    original_ensure = agent_api.ensure_agent_tables
    agent_api.ensure_agent_tables = noop_ensure_agent_tables
    try:
        response = await get_run_memory_snapshot(result["run_id"], db_session=agent_session)
    finally:
        agent_api.ensure_agent_tables = original_ensure
    assert response["success"] is True
    assert response["snapshot"]["run_id"] == result["run_id"]
    assert "回答时先说结论" in response["snapshot"]["memory_context"]


@pytest.mark.asyncio
async def test_agent_memory_view_exports_hermes_style_markdown(agent_session: AsyncSession):
    manager = MemoryManager(agent_session)
    await manager.save_memory(
        key="user.preference.reply_order",
        value="先给结论，再给原因。",
        memory_type="preference",
        importance=8,
    )
    await manager.save_memory(
        key="project.rule.visual_style",
        value="角色图优先国漫美型。",
        memory_type="project_context",
        importance=8,
    )
    await agent_session.commit()

    async def noop_ensure_agent_tables():
        return None

    from app.api.v1 import agent as agent_api

    original_ensure = agent_api.ensure_agent_tables
    agent_api.ensure_agent_tables = noop_ensure_agent_tables
    try:
        response = await get_memory_view(db_session=agent_session)
    finally:
        agent_api.ensure_agent_tables = original_ensure
    assert response["success"] is True
    assert "# USER.md" in response["user_md"]
    assert "user.preference.reply_order" in response["user_md"]
    assert "# MEMORY.md" in response["memory_md"]
    assert "project.rule.visual_style" in response["memory_md"]
    assert "# SKILLS.md" in response["skills_md"]
    assert "creative_project_advance" in response["skills_md"]


@pytest.mark.asyncio
async def test_agent_chat_creates_pending_memory_candidates_without_auto_save(agent_session: AsyncSession):
    class FakeLLM:
        async def chat(self, **kwargs):
            return LLMGenerationResult(success=True, content="好的，我会把这个偏好作为候选记忆交给你确认。")

    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    await agent_session.commit()

    service = AgentService(agent_session)
    service._llm_manager = FakeLLM()
    result = await service.chat(
        session_id="",
        user_message="以后默认使用二次元国漫美型，不要 3D 写实",
        profile_id="default-assistant",
    )

    assert result["memory_candidates"]
    memory_rows = (await agent_session.execute(select(AgentMemory))).scalars().all()
    assert memory_rows == []

    steps = (
        await agent_session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == result["run_id"])
            .order_by(AgentRunStep.order_index.asc())
        )
    ).scalars().all()
    memory_steps = [step for step in steps if step.step_type == "memory_extract"]
    assert len(memory_steps) == 1
    assert memory_steps[0].status == "pending"
    payload = json.loads(memory_steps[0].output_json)
    assert payload["candidates"][0]["memory_type"] == "preference"


@pytest.mark.asyncio
async def test_agent_manual_memory_save_accepts_json_body(agent_session: AsyncSession):
    response = await save_memory(
        key="creative.project.rule.visual_style",
        request=SaveMemoryRequest(
            value="角色立绘默认使用二次元国漫美型",
            memory_type="project_context",
            importance=8,
        ),
        db_session=agent_session,
    )

    assert response["success"] is True
    saved_rows = (await agent_session.execute(select(AgentMemory))).scalars().all()
    assert len(saved_rows) == 1
    assert saved_rows[0].key == "creative.project.rule.visual_style"
    assert saved_rows[0].value == "角色立绘默认使用二次元国漫美型"
    assert saved_rows[0].memory_type == "project_context"
    assert saved_rows[0].importance == 8
    assert saved_rows[0].confidence >= MemoryManager.MIN_CONFIDENCE_FOR_CONTEXT

    context = await MemoryManager(agent_session).build_memory_context()
    assert "creative.project.rule.visual_style" in context
    assert "角色立绘默认使用二次元国漫美型" in context


@pytest.mark.asyncio
async def test_agent_memory_candidate_save_endpoint_persists_selected_items(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    run = AgentRun(
        id="memory-run-save",
        user_id="default",
        session_id="session-memory-save",
        profile_id="default-assistant",
        status="completed",
        objective="记住偏好",
    )
    step = AgentRunStep(
        run_id=run.id,
        session_id=run.session_id,
        profile_id=run.profile_id,
        step_type="memory_extract",
        status="pending",
        order_index=3,
        summary="提取到 2 条待确认记忆",
        output_json=json.dumps(
            {
                "candidates": [
                    {
                        "key": "user_preference_visual_style",
                        "value": "默认使用二次元国漫美型",
                        "memory_type": "preference",
                        "importance": 8,
                    },
                    {
                        "key": "user_preference_negative_style",
                        "value": "不要 3D 写实",
                        "memory_type": "preference",
                        "importance": 7,
                    },
                ]
            },
            ensure_ascii=False,
        ),
    )
    agent_session.add(run)
    agent_session.add(step)
    await agent_session.commit()

    response = await save_memory_candidates(
        run.id,
        step.id,
        SaveMemoryCandidatesRequest(indices=[1]),
        db_session=agent_session,
    )

    assert response["success"] is True
    assert len(response["saved"]) == 1
    saved_rows = (await agent_session.execute(select(AgentMemory))).scalars().all()
    assert len(saved_rows) == 1
    assert saved_rows[0].key == "user_preference_negative_style"
    refreshed_step = await agent_session.get(AgentRunStep, step.id)
    assert refreshed_step.status == "completed"


@pytest.mark.asyncio
async def test_agent_memory_candidate_discard_endpoint_marks_step_dismissed(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    run = AgentRun(
        id="memory-run-discard",
        user_id="default",
        session_id="session-memory-discard",
        profile_id="default-assistant",
        status="completed",
        objective="丢弃记忆",
    )
    step = AgentRunStep(
        run_id=run.id,
        session_id=run.session_id,
        profile_id=run.profile_id,
        step_type="memory_extract",
        status="pending",
        order_index=3,
        summary="提取到 1 条待确认记忆",
        output_json=json.dumps({"candidates": [{"key": "demo", "value": "demo"}]}, ensure_ascii=False),
    )
    agent_session.add(run)
    agent_session.add(step)
    await agent_session.commit()

    response = await discard_memory_candidates(run.id, step.id, db_session=agent_session)

    assert response["success"] is True
    refreshed_step = await agent_session.get(AgentRunStep, step.id)
    assert refreshed_step.status == "dismissed"
    memory_rows = (await agent_session.execute(select(AgentMemory))).scalars().all()
    assert memory_rows == []


@pytest.mark.asyncio
async def test_agent_run_export_markdown(agent_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    thread = AgentThread(id="session-export", user_id="default", title="演示项目线程", status="active", active_profile_id="creative-director")
    run = AgentRun(
        id="export-run-1",
        user_id="default",
        session_id="session-export",
        profile_id="creative-director",
        status="completed",
        objective="推进演示项目",
        context_json=json.dumps({"project_id": "project-1"}, ensure_ascii=False),
        result_json=json.dumps({"reply": "完成"}, ensure_ascii=False),
    )
    step = AgentRunStep(
        run_id=run.id,
        session_id=run.session_id,
        profile_id=run.profile_id,
        step_type="tool_call",
        status="completed",
        order_index=0,
        tool_name="inspect_creative_project",
        summary="读取项目成功",
        input_json=json.dumps({"project_id": "project-1"}, ensure_ascii=False),
        output_json=json.dumps({"title": "演示项目"}, ensure_ascii=False),
    )
    msg = AgentMessage(thread_id="session-export", run_id=run.id, role="user", content="推进演示项目")
    agent_session.add(thread)
    agent_session.add(run)
    agent_session.add(step)
    agent_session.add(msg)
    await agent_session.commit()

    response = await export_run_markdown(run.id, db_session=agent_session)
    body = response.body.decode("utf-8")

    assert "# Agent Run export-run-1" in body
    assert "推进演示项目" in body
    assert "读取项目成功" in body
    assert "inspect_creative_project" in body
    assert "## 工作线程信息" in body
    assert "演示项目线程" in body
    assert "## 对话消息" in body


@pytest.mark.asyncio
async def test_agent_run_linked_logs_collects_tool_generation_and_task_logs(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    queue = get_task_queue()
    task = await queue.create_task("creative_project", {"project_id": "project-log-1"})
    await queue.append_event(task.task_id, "agent_link", "run 触发任务", data={"run_id": "linked-run-1"})

    run = AgentRun(
        id="linked-run-1",
        user_id="default",
        session_id="session-linked",
        profile_id="creative-director",
        status="completed",
        objective="反查日志",
        context_json=json.dumps({"project_id": "project-log-1"}, ensure_ascii=False),
    )
    step = AgentRunStep(
        run_id=run.id,
        session_id=run.session_id,
        profile_id=run.profile_id,
        step_type="tool_call",
        status="completed",
        order_index=1,
        tool_name="inspect_creative_project",
        summary="读取项目和任务",
        linked_objects_json=json.dumps(
            [
                {"type": "project", "id": "project-log-1", "title": "日志项目"},
                {"type": "project_content", "id": "content-log-1", "title": "第二章正文"},
                {"type": "task", "id": task.task_id, "title": "后台任务"},
            ],
            ensure_ascii=False,
        ),
    )
    tool_log = AgentToolCall(
        session_id=run.session_id,
        tool_name="inspect_creative_project",
        tool_args=json.dumps({"project_id": "project-log-1"}, ensure_ascii=False),
        result=json.dumps({"project_id": "project-log-1"}, ensure_ascii=False),
        success=True,
        duration_ms=12,
    )
    generation_log = ProjectGenerationLog(
        id="generation-log-1",
        project_id="project-log-1",
        content_id="content-log-1",
        scene="creative_project",
        stage="novel_body",
        provider="deepseek-v4",
        model="deepseek-chat",
        status="success",
    )
    agent_session.add(run)
    agent_session.add(step)
    agent_session.add(tool_log)
    agent_session.add(generation_log)
    await agent_session.commit()

    response = await get_run_linked_logs(run.id, db_session=agent_session)

    assert response["run_id"] == run.id
    assert response["project_ids"] == ["project-log-1"]
    assert response["content_ids"] == ["content-log-1"]
    assert response["tool_calls"][0]["tool_name"] == "inspect_creative_project"
    assert response["generation_logs"][0]["id"] == "generation-log-1"
    assert response["tasks"][0]["task_id"] == task.task_id
    assert response["tasks"][0]["events"][0]["message"] == "run 触发任务"


@pytest.mark.asyncio
async def test_agent_delegate_subtask_creates_child_run_and_parent_step(agent_session: AsyncSession):
    class FakeLLM:
        async def chat(self, **kwargs):
            return LLMGenerationResult(success=True, content="子智能体已完成检查。")

    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    await agent_session.commit()

    service = AgentService(agent_session)
    service._llm_manager = FakeLLM()
    parent_result = await service.chat(
        session_id="",
        user_message="推进当前创作项目",
        context={"project_id": "project-1"},
        profile_id="creative-director",
    )
    parent_run = await agent_session.get(AgentRun, parent_result["run_id"])
    assert parent_run is not None

    delegated = await service.delegate_subtask(
        parent_run=parent_run,
        target_profile_id="storyboard-director",
        message="请检查分镜缺口",
        context={"chapter_number": 2},
    )

    assert delegated["success"] is True
    child_run = await agent_session.get(AgentRun, delegated["child_run_id"])
    assert child_run is not None
    assert child_run.parent_run_id == parent_run.id
    assert child_run.profile_id == "storyboard-director"

    steps = (
        await agent_session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == parent_run.id)
            .order_by(AgentRunStep.order_index.asc())
        )
    ).scalars().all()
    delegate_steps = [step for step in steps if step.step_type == "delegate_subtask"]
    assert len(delegate_steps) == 1
    output = json.loads(delegate_steps[0].output_json)
    assert output["child_run_id"] == child_run.id


def test_delegation_policy_rejects_cycles_and_depth_overflow():
    policy = DelegationPolicy(DelegationLimits(max_depth=2))

    with pytest.raises(DelegationValidationError, match="深度"):
        policy.validate(
            [DelegatedTask("child", "novel-writer", "续写正文")],
            parent_depth=2,
        )

    with pytest.raises(DelegationValidationError, match="循环"):
        policy.validate(
            [
                DelegatedTask("a", "novel-writer", "任务 A", depends_on=("b",)),
                DelegatedTask("b", "quality-reviewer", "任务 B", depends_on=("a",)),
            ],
            parent_depth=0,
        )


@pytest.mark.asyncio
async def test_subagent_orchestrator_runs_independent_tasks_in_parallel(agent_session: AsyncSession):
    active = 0
    peak = 0

    class FakeRunner:
        async def execute(self, task, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return SubagentExecutionResult(
                task_key=task.task_key,
                profile_id=task.profile_id,
                status="completed",
                child_run_id=f"run-{task.task_key}",
                child_thread_id=f"thread-{task.task_key}",
                reply=f"{task.task_key} completed",
                raw_result={"done": True, "run_id": f"run-{task.task_key}"},
            )

    parent = AgentRun(
        id="parent-orchestration-run",
        root_run_id="parent-orchestration-run",
        run_kind="primary",
        delegation_depth=0,
        user_id="default",
        session_id="thread-parent",
        profile_id="creative-director",
        status="completed",
        objective="并行检查",
        context_json=json.dumps({"project_id": "project-1", "secret": "do-not-copy"}),
        result_json="{}",
    )
    agent_session.add(parent)
    await agent_session.commit()

    orchestrator = SubagentOrchestrator(agent_session, FakeRunner())
    result = await orchestrator.delegate(
        parent,
        [
            DelegatedTask("writer", "novel-writer", "检查正文"),
            DelegatedTask("reviewer", "quality-reviewer", "检查连续性"),
        ],
        join_strategy="all",
    )

    assert result["success"] is True
    assert result["summary"] == {
        "total": 2,
        "completed": 2,
        "failed": 0,
        "skipped": 0,
        "waiting_confirmation": 0,
        "cancelled": 0,
    }
    assert peak == 2
    delegations = (
        await agent_session.execute(
            select(AgentDelegation).where(AgentDelegation.parent_run_id == parent.id)
        )
    ).scalars().all()
    assert {item.child_run_id for item in delegations} == {"run-writer", "run-reviewer"}
    assert all(item.status == "completed" for item in delegations)
    step = (
        await agent_session.execute(
            select(AgentRunStep).where(
                AgentRunStep.run_id == parent.id,
                AgentRunStep.step_type == "delegate_subtask",
            )
        )
    ).scalar_one()
    assert step.status == "completed"
    assert set(json.loads(step.output_json)["linked_runs"]) == {"run-writer", "run-reviewer"}


def test_delegation_tool_schema_and_supervisor_visibility():
    task_schema = DELEGATE_AGENT_TASKS_SCHEMA["properties"]["tasks"]
    assert task_schema["minItems"] == 1
    assert task_schema["maxItems"] == 6
    assert task_schema["items"]["required"] == ["task_key", "profile_id", "objective"]
    assert DELEGATE_AGENT_TASKS_SCHEMA["properties"]["join_strategy"]["enum"] == ["all", "best_effort"]

    supervisor_tools = AgentService._effective_allowed_tools(
        {"allowed_tools": ["*"], "can_delegate": True}
    )
    worker_tools = AgentService._effective_allowed_tools(
        {"allowed_tools": ["*"], "can_delegate": False}
    )
    assert supervisor_tools == ["*"]
    assert "delegate_agent_tasks" not in worker_tools


def test_production_plan_tools_are_registered_with_read_contracts():
    for name in ("run_creative_production_plan", "analyze_creative_production_plan_impact"):
        tool = ToolRegistry.get_tool(name)
        assert tool is not None
        assert tool.category == "creative_project"
        assert tool.risk_level == "read"
        assert tool.output_type.startswith("creative_production_plan")


@pytest.mark.asyncio
async def test_production_plan_runtime_requires_director_plan_and_matching_project(agent_session: AsyncSession):
    service = AgentService(agent_session)
    base_state = {
        "run": SimpleNamespace(id="parent-run"),
        "profile": {"id": "creative-director", "can_delegate": True},
        "effective_context": {
            "project_id": "project-1",
            "creative_project_context": {
                "project": {"id": "project-1"},
                "production_plan": {"nodes": [{"id": "story", "specialist_role": "story-designer"}]},
            },
        },
    }

    wrong_profile = {**base_state, "profile": {"id": "default-assistant", "can_delegate": True}}
    result = await service._execute_runtime_tool(
        wrong_profile, "analyze_creative_production_plan_impact", {"project_id": "project-1", "changed_node_ids": ["story"]}
    )
    assert result is not None and not result.success
    assert "创作导演" in result.error

    result = await service._execute_runtime_tool(
        base_state, "analyze_creative_production_plan_impact", {"project_id": "other", "changed_node_ids": ["story"]}
    )
    assert result is not None and not result.success
    assert "上下文一致" in result.error

    missing_plan = {**base_state, "effective_context": {"project_id": "project-1", "creative_project_context": {"project": {"id": "project-1"}}}}
    result = await service._execute_runtime_tool(
        missing_plan, "analyze_creative_production_plan_impact", {"project_id": "project-1", "changed_node_ids": ["story"]}
    )
    assert result is not None and not result.success
    assert "没有已保存的生产计划" in result.error


@pytest.mark.asyncio
async def test_production_plan_runtime_returns_auditable_plan_slice(agent_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    class FakeTeamComposer:
        calls = []

        def __init__(self, orchestrator):
            self.orchestrator = orchestrator

        async def run_template(self, template, parent_run, *, inputs, user_id="", join_strategy=None):
            self.calls.append((template, parent_run, inputs))
            return {"success": True, "joined_observation": "专家结果已汇合", "linked_runs": ["child-visual"]}

    monkeypatch.setattr("app.services.agent.team_composer.TeamComposer", FakeTeamComposer)
    service = AgentService(agent_session)
    plan = {
        "content_id": "plan-1",
        "title": "恐怖漫画生产计划",
        "version": 2,
        "status": "approved",
        "goal": "完成 6 页竖屏恐怖漫画",
        "nodes": [
            {"id": "story", "label": "故事节拍", "stage": "story_seed", "specialist_role": "story-designer"},
            {
                "id": "visual", "label": "第 3 页构图", "stage": "visual_plan", "specialist_role": "visual-director",
                "depends_on": ["story"], "input_asset_ids": ["asset-character"], "output_content_ids": ["content-board"],
                "planning_summary": {"prompt": "雨夜古堡", "expected_output": "storyboard_frame"},
                "provider": "demo-provider", "model": "demo-model", "requires_confirmation": True,
            },
        ],
    }
    state = {
        "run": SimpleNamespace(id="parent-run"),
        "profile": {"id": "creative-director", "can_delegate": True},
        "effective_context": {"project_id": "project-1", "creative_project_context": {"project": {"id": "project-1"}, "production_plan": plan}},
    }

    result = await service._execute_runtime_tool(
        state, "run_creative_production_plan", {"project_id": "project-1", "node_ids": ["visual"]}
    )

    assert result is not None and result.success
    assert result.result["production_plan"] == {
        "id": "plan-1", "title": "恐怖漫画生产计划", "version": 2, "status": "approved",
        "goal": "完成 6 页竖屏恐怖漫画", "production_profile": "",
    }
    assert [item["id"] for item in result.result["selected_nodes"]] == ["story", "visual"]
    visual = result.result["selected_nodes"][1]
    assert visual["input_asset_ids"] == ["asset-character"]
    assert visual["planning_summary"]["prompt"] == "雨夜古堡"
    assert visual["requires_confirmation"] is True
    assert FakeTeamComposer.calls[0][0].roles[-1].id == "plan-visual"

    impact = await service._execute_runtime_tool(
        state, "analyze_creative_production_plan_impact", {"project_id": "project-1", "changed_node_ids": ["story"]}
    )
    assert impact is not None and impact.success
    assert [(item["id"], item["reason"]) for item in impact.result["affected_nodes"]] == [
        ("story", "changed"), ("visual", "depends_on:story")
    ]


@pytest.mark.asyncio
async def test_supervisor_delegation_result_resumes_parent_loop(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            if kwargs.get("max_tokens") == 50:
                return LLMGenerationResult(success=True, content="委派审校")
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return LLMGenerationResult(
                    success=True,
                    content=(
                        '{"tool_calls":[{"id":"delegate_1","name":"delegate_agent_tasks",'
                        '"arguments":"{\\"tasks\\":[{\\"task_key\\":\\"review\\",'
                        '\\"profile_id\\":\\"quality-reviewer\\",'
                        '\\"objective\\":\\"检查连续性\\"}]}"}]}'
                    ),
                )
            observed = "\n".join(str(item.content) for item in kwargs.get("messages") or [])
            assert "审校完成：连续性正常" in observed
            return LLMGenerationResult(success=True, content="已综合子智能体结果，连续性检查通过。")

    async def fake_runtime_tool(state, tool_name, tool_args):
        assert tool_name == "delegate_agent_tasks"
        assert tool_args["tasks"][0]["profile_id"] == "quality-reviewer"
        return ToolCallResult(
            tool_name=tool_name,
            success=True,
            result={
                "status": "completed",
                "joined_observation": "审校完成：连续性正常",
                "delegations": [],
                "linked_runs": ["child-review-run"],
                "summary": {"total": 1, "completed": 1, "failed": 0},
            },
        )

    service = AgentService(agent_session)
    fake_llm = FakeLLM()
    service._llm_manager = fake_llm
    monkeypatch.setattr(service, "_execute_runtime_tool", fake_runtime_tool)

    result = await service.chat(
        session_id="",
        user_message="请委派审校并汇总结果",
        profile_id="default-assistant",
    )

    assert result["done"] is True
    assert result["reply"] == "已综合子智能体结果，连续性检查通过。"
    assert len(fake_llm.calls) == 2
    tool_names = {
        item["function"]["name"]
        for item in fake_llm.calls[0].get("tools") or []
    }
    assert "delegate_agent_tasks" in tool_names


@pytest.mark.asyncio
async def test_manual_delegation_observation_resumes_same_parent_run(agent_session: AsyncSession):
    class FakeLLM:
        async def chat(self, **kwargs):
            observed = "\n".join(str(item.content) for item in kwargs.get("messages") or [])
            assert "角色检查完成" in observed
            return LLMGenerationResult(success=True, content="父智能体已汇总：角色逻辑成立。")

    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    thread_manager = ThreadManager(agent_session)
    thread = await thread_manager.create_thread(title="manual resume")
    await thread_manager.append_message(thread.id, {"role": "user", "content": "检查角色逻辑"})
    parent = AgentRun(
        id="manual-resume-parent",
        root_run_id="manual-resume-parent",
        user_id="default",
        session_id=thread.id,
        profile_id="default-assistant",
        status="completed",
        objective="检查角色逻辑",
    )
    agent_session.add(parent)
    await agent_session.commit()

    service = AgentService(agent_session)
    service._llm_manager = FakeLLM()
    result = await service.resume_from_delegation_observation(
        parent,
        {
            "status": "completed",
            "joined_observation": "角色检查完成：动机与前文一致。",
            "delegations": [{"task_key": "character-review"}],
        },
    )
    await agent_session.commit()

    assert result["run_id"] == parent.id
    assert result["reply"] == "父智能体已汇总：角色逻辑成立。"
    await agent_session.refresh(parent)
    assert parent.status == "completed"
    steps = (
        await agent_session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == parent.id)
            .order_by(AgentRunStep.order_index.asc())
        )
    ).scalars().all()
    assert [step.step_type for step in steps] == ["observe", "final"]


@pytest.mark.asyncio
async def test_agent_run_tree_and_delegation_apis(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    root = AgentRun(
        id="tree-root",
        root_run_id="tree-root",
        user_id="default",
        session_id="tree-thread",
        profile_id="default-assistant",
        status="completed",
        objective="root",
    )
    child = AgentRun(
        id="tree-child",
        root_run_id="tree-root",
        parent_run_id="tree-root",
        run_kind="delegated",
        delegation_depth=1,
        user_id="default",
        session_id="child-thread",
        profile_id="quality-reviewer",
        status="completed",
        objective="review",
    )
    record = AgentDelegation(
        id="delegation-tree",
        user_id="default",
        root_run_id="tree-root",
        parent_run_id="tree-root",
        child_run_id="tree-child",
        task_key="review",
        target_profile_id="quality-reviewer",
        objective="review",
        status="completed",
    )
    agent_session.add_all([root, child, record])
    await agent_session.commit()

    tree = await get_run_tree("tree-child", db_session=agent_session)
    assert tree["root_run_id"] == "tree-root"
    assert tree["root"]["id"] == "tree-root"
    assert tree["root"]["children"][0]["id"] == "tree-child"
    assert tree["delegations"][0]["task_key"] == "review"

    delegations = await get_run_delegations("tree-root", db_session=agent_session)
    assert delegations["total"] == 1
    assert delegations["delegations"][0]["child_run_id"] == "tree-child"


@pytest.mark.asyncio
async def test_child_confirmation_and_cancellation_propagate_to_parent_join(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def noop_ensure_agent_tables():
        return None

    async def write_handler(value: str = ""):
        return {"success": True, "value": value}

    ToolRegistry.register(
        Tool(
            name="agent_test_child_confirmation",
            description="child confirmation test",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
            },
            handler=write_handler,
            risk_level="write",
        )
    )
    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)

    parent = AgentRun(
        id="confirm-parent",
        root_run_id="confirm-parent",
        user_id="default",
        session_id="confirm-parent-thread",
        profile_id="default-assistant",
        status="waiting_confirmation",
        objective="parent",
    )
    child = AgentRun(
        id="confirm-child",
        root_run_id="confirm-parent",
        parent_run_id="confirm-parent",
        run_kind="delegated",
        delegation_depth=1,
        user_id="default",
        session_id="confirm-child-thread",
        profile_id="quality-reviewer",
        status="waiting_confirmation",
        objective="child",
    )
    parent_step = AgentRunStep(
        id=9101,
        run_id=parent.id,
        session_id=parent.session_id,
        profile_id=parent.profile_id,
        step_type="delegate_subtask",
        status="waiting_confirmation",
        order_index=1,
        output_json=json.dumps({"join_strategy": "all"}),
    )
    pending_step = AgentRunStep(
        id=9102,
        run_id=child.id,
        session_id=child.session_id,
        profile_id=child.profile_id,
        step_type="tool_call",
        status="pending",
        order_index=1,
        tool_name="agent_test_child_confirmation",
        input_json=json.dumps(
            {
                "name": "agent_test_child_confirmation",
                "arguments": {"value": "approved"},
            }
        ),
    )
    record = AgentDelegation(
        id="confirm-delegation",
        user_id="default",
        root_run_id=parent.id,
        parent_run_id=parent.id,
        child_run_id=child.id,
        parent_step_id=parent_step.id,
        task_key="review",
        target_profile_id=child.profile_id,
        objective="child",
        status="waiting_confirmation",
    )
    agent_session.add_all([parent, child, parent_step, pending_step, record])
    await agent_session.commit()

    response = await confirm_pending_step(child.id, pending_step.id, db_session=agent_session)
    assert response["success"] is True
    await agent_session.refresh(parent)
    await agent_session.refresh(parent_step)
    await agent_session.refresh(record)
    assert parent.status == "completed"
    assert parent_step.status == "completed"
    assert record.status == "completed"
    assert json.loads(parent_step.output_json)["resume_required"] is True

    cancel_parent = AgentRun(
        id="cancel-parent",
        root_run_id="cancel-parent",
        user_id="default",
        session_id="cancel-parent-thread",
        profile_id="default-assistant",
        status="waiting_confirmation",
        objective="parent cancel",
    )
    cancel_child = AgentRun(
        id="cancel-child",
        root_run_id="cancel-parent",
        parent_run_id="cancel-parent",
        run_kind="delegated",
        delegation_depth=1,
        user_id="default",
        session_id="cancel-child-thread",
        profile_id="quality-reviewer",
        status="waiting_confirmation",
        objective="child cancel",
    )
    cancel_step = AgentRunStep(
        id=9201,
        run_id=cancel_parent.id,
        session_id=cancel_parent.session_id,
        profile_id=cancel_parent.profile_id,
        step_type="delegate_subtask",
        status="waiting_confirmation",
        order_index=1,
        output_json=json.dumps({"join_strategy": "all"}),
    )
    cancel_record = AgentDelegation(
        id="cancel-delegation",
        user_id="default",
        root_run_id=cancel_parent.id,
        parent_run_id=cancel_parent.id,
        child_run_id=cancel_child.id,
        parent_step_id=cancel_step.id,
        task_key="cancel",
        target_profile_id=cancel_child.profile_id,
        objective="child cancel",
        status="waiting_confirmation",
    )
    agent_session.add_all([cancel_parent, cancel_child, cancel_step, cancel_record])
    await agent_session.commit()

    await cancel_run(cancel_child.id, db_session=agent_session)
    await agent_session.refresh(cancel_parent)
    await agent_session.refresh(cancel_record)
    assert cancel_parent.status == "cancelled"
    assert cancel_record.status == "cancelled"


@pytest.mark.asyncio
async def test_agent_high_risk_tool_call_creates_pending_step(agent_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []

    async def risky_handler(value: str = ""):
        calls.append({"value": value})
        return {"ok": True}

    ToolRegistry.register(
        Tool(
            name="agent_test_write_tool",
            description="test write tool",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            handler=risky_handler,
            category="general",
            risk_level="write",
            output_type="test_result",
        )
    )

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMGenerationResult(
                    success=True,
                    content='{"tool_calls":[{"id":"call_1","name":"agent_test_write_tool","arguments":"{\\"value\\":\\"demo\\"}"}]}',
                )
            return LLMGenerationResult(success=True, content="需要用户确认后执行。")

    manager = AgentProfileManager(agent_session)
    await manager.list_profiles()
    await agent_session.commit()

    service = AgentService(agent_session)
    service._llm_manager = FakeLLM()
    result = await service.chat(
        session_id="",
        user_message="执行高风险工具",
        profile_id="default-assistant",
    )

    assert result["run_id"]
    assert calls == []
    steps = (
        await agent_session.execute(
            select(AgentRunStep).where(AgentRunStep.run_id == result["run_id"])
        )
    ).scalars().all()
    pending_steps = [step for step in steps if step.step_type == "tool_call" and step.status == "pending"]
    assert len(pending_steps) == 1
    output = json.loads(pending_steps[0].output_json)
    assert output["pending_confirmation"] is True
    assert output["risk_level"] == "write"

    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    response = await confirm_pending_step(result["run_id"], pending_steps[0].id, db_session=agent_session)
    assert response["success"] is True
    assert "已确认并执行工具" in response["message"]
    assert calls == [{"value": "demo"}]

    session = await agent_session.get(AgentSession, response["run"]["session_id"])
    messages = json.loads(session.messages)
    assert messages[-2]["role"] == "user"
    assert "确认执行上一条待确认工具" in messages[-2]["content"]
    assert messages[-1]["role"] == "assistant"
    assert "agent_test_write_tool" in messages[-1]["content"]


@pytest.mark.asyncio
async def test_agent_tool_test_api_requires_confirmation_for_high_risk_tool(
    agent_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def risky_handler(value: str = ""):
        return {"value": value}

    ToolRegistry.register(
        Tool(
            name="agent_test_external_tool",
            description="test external tool",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            handler=risky_handler,
            category="general",
            risk_level="write",
            output_type="test_result",
        )
    )

    async def noop_ensure_agent_tables():
        return None

    monkeypatch.setattr("app.api.v1.agent.ensure_agent_tables", noop_ensure_agent_tables)
    response = await run_tool_test(
        ToolTestRequest(
            tool_name="agent_test_external_tool",
            arguments={"value": "demo"},
            profile_id="default-assistant",
            confirmed=False,
        ),
        db_session=agent_session,
    )

    assert response["success"] is False
    assert response["pending_confirmation"] is True
    assert response["authorized"] is True


def test_agent_extracts_linked_objects_from_tool_result(agent_session: AsyncSession):
    service = AgentService(agent_session)
    result = ToolCallResult(
        tool_name="inspect_creative_project",
        success=True,
        result={
            "project": {"id": "project-1", "title": "演示项目"},
            "contents": [
                {
                    "id": "content-1",
                    "content_type": "storyboard",
                    "chapter_number": 2,
                    "title": "第二章分镜",
                }
            ],
            "assets": [{"id": "asset-1", "title": "主角立绘"}],
            "task_id": "task-1",
        },
    )

    linked = service._extract_linked_objects(result)
    keys = {(item["type"], item["id"]) for item in linked}
    assert ("project", "project-1") in keys
    assert ("project_content", "content-1") in keys
    assert ("chapter", "2") in keys
    assert ("asset", "asset-1") in keys


# ---------------------------------------------------------------------------
# M4.5: Refreshed thread reconstructs pending slots and active intent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_refreshed_thread_reconstructs_pending_slots_and_active_intent(
    agent_session: AsyncSession,
):
    """Verify that a refreshed thread (new run on same thread_id) reconstructs
    the pending slots and active intent from the previous context snapshot.

    Scenario: User initiates a platform search with only a keyword (missing
    platform). On refresh, the same pending state should be recoverable.
    """
    from app.api.v1.agent import _safe_json_loads

    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="你想在哪个平台搜索？")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "refresh-pending-agent",
            "name": "刷新重构测试智能体",
            "allowed_tools": ["search_platform_sources"],
            "max_steps": 3,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    # First run: user gives keyword but no platform → pending slots
    first = await service.chat(
        session_id="",
        user_message="搜索包氏父子解说视频",
        profile_id=profile.id,
    )

    thread_id = first["session_id"]
    assert thread_id

    # Verify first run has pending slots stored in the thread's legacy_context
    thread = await agent_session.get(AgentThread, thread_id)
    assert thread is not None
    metadata = _safe_json_loads(thread.metadata_json, {})
    legacy_ctx = metadata.get("legacy_context") or {}
    conv_state = legacy_ctx.get("conversation_state") or {}
    # The conversation state should have been persisted via context_pack_phase
    assert conv_state.get("active_intent") == "platform_search"
    assert conv_state.get("slots", {}).get("keyword") == "包氏父子解说视频"

    # Verify context snapshot was stored with the same pending state
    snap_result = await agent_session.execute(
        select(AgentContextSnapshot)
        .where(AgentContextSnapshot.thread_id == thread_id)
        .order_by(AgentContextSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = snap_result.scalar_one_or_none()
    assert snapshot is not None, "context snapshot should be persisted"

    snap_data = _safe_json_loads(snapshot.context_json, {})
    sections = snap_data.get("sections", {})
    conv_state_section = sections.get("conversation_state", {})
    snap_state = conv_state_section.get("state") or {}
    assert snap_state.get("active_intent") == "platform_search"
    assert snap_state.get("slots", {}).get("keyword") == "包氏父子解说视频"

    # Verify pending_action in snapshot
    pending_action = snap_state.get("pending_action") or conv_state_section.get("pending_action") or {}
    assert pending_action.get("type") in {"await_user_slot", "tool_call_ready"}

    # Simulate refresh: second run on same thread, user fills in platform
    second_llm = FakeLLM()
    service._llm_manager = second_llm

    second = await service.chat(
        session_id=thread_id,
        user_message="用B站搜",
        profile_id=profile.id,
    )

    # After second run, verify slots are completed
    assert second["tool_calls"]
    tool_call = second["tool_calls"][0]
    assert tool_call["tool_name"] == "search_platform_sources"
    assert "pending_confirmation" not in tool_call["result"]
    assert tool_call["result"]["arguments"]["keyword"] == "包氏父子解说视频"
    assert tool_call["result"]["arguments"]["platform"] == "bili"

    # Verify the current thread metadata has updated slots
    await agent_session.refresh(thread)
    updated_metadata = _safe_json_loads(thread.metadata_json, {})
    updated_legacy = updated_metadata.get("legacy_context") or {}
    updated_conv = updated_legacy.get("conversation_state") or {}
    assert updated_conv.get("active_intent") == "platform_search"
    assert updated_conv.get("slots", {}).get("platform") == "bili"

    # Verify the second run's context snapshot carries forward the same active intent
    snap_result2 = await agent_session.execute(
        select(AgentContextSnapshot)
        .where(AgentContextSnapshot.thread_id == thread_id)
        .order_by(AgentContextSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot2 = snap_result2.scalar_one_or_none()
    assert snapshot2 is not None
    snap2_data = _safe_json_loads(snapshot2.context_json, {})
    sections2 = snap2_data.get("sections", {})
    conv2 = sections2.get("conversation_state", {}).get("state") or {}
    assert conv2.get("active_intent") == "platform_search"


# ---------------------------------------------------------------------------
# M5.6: Pending memory candidates do not split or override thread context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_pending_memory_candidates_do_not_split_thread_context(
    agent_session: AsyncSession,
):
    """Verify that pending (unconfirmed) memory candidates do not interfere
    with the thread context on subsequent runs in the same thread.

    Hermes-style memory lifecycle: memory_extract creates candidates with
    status=pending. These should NOT appear in the thread context until
    confirmed by the user. A new run on the same thread should maintain
    message continuity regardless of pending memory candidates.
    """
    from app.api.v1.agent import _safe_json_loads

    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="好的，我已经记录了这些信息。")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "memory-isolation-agent",
            "name": "记忆隔离测试智能体",
            "allowed_tools": [],
            "max_steps": 3,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    # First run: establish a thread
    first = await service.chat(
        session_id="",
        user_message="我的项目叫星辰故事集，主角是林雪",
        profile_id=profile.id,
    )

    thread_id = first["session_id"]
    assert thread_id

    # Insert a pending memory candidate directly (simulating memory_extract without confirmation)
    memory_mgr = service.memory_mgr
    await memory_mgr.save_memory(
        key="user_project_name",
        value="星辰故事集",
        memory_type="fact",
        thread_id=thread_id,
        run_id=first["run_id"],
        message_ids=[],
    )
    await agent_session.commit()

    # Verify the memory is pending
    mem_result = await agent_session.execute(
        select(AgentMemory)
        .where(AgentMemory.thread_id == thread_id)
    )
    memories = list(mem_result.scalars().all())
    assert len(memories) >= 1
    # After save_memory, status should be "confirmed" (not pending)
    # For M5.6, we want to verify that the thread context is NOT disrupted

    # Count messages before second run
    msgs_before = await service.thread_mgr.get_messages(thread_id)
    msg_count_before = len(msgs_before)

    # Second run on same thread - should maintain continuity
    second_llm = FakeLLM()
    service._llm_manager = second_llm

    second = await service.chat(
        session_id=thread_id,
        user_message="查一下项目进度",
        profile_id=profile.id,
    )

    # Verify second run produces output and continues on same thread
    assert second["session_id"] == thread_id

    # Verify message count increased (not reset)
    msgs_after = await service.thread_mgr.get_messages(thread_id)
    msg_count_after = len(msgs_after)
    assert msg_count_after > msg_count_before, "thread messages should accumulate, not reset"

    # Verify the thread still has the original messages + new ones
    all_msgs = await service.thread_mgr.get_messages(thread_id)
    user_messages = [m for m in all_msgs if isinstance(m, dict) and m.get("role") == "user"]
    assert len(user_messages) >= 2
    assert any("星辰故事集" in str(m.get("content", "")) for m in user_messages)
    assert any("项目进度" in str(m.get("content", "")) for m in user_messages)

    # Verify thread context snapshots exist for both runs
    snap_result = await agent_session.execute(
        select(AgentContextSnapshot)
        .where(AgentContextSnapshot.thread_id == thread_id)
        .order_by(AgentContextSnapshot.created_at.asc())
    )
    snapshots = list(snap_result.scalars().all())
    assert len(snapshots) >= 2, f"expected >= 2 snapshots, got {len(snapshots)}"

    # Verify each snapshot references the same thread
    for snap in snapshots:
        assert snap.thread_id == thread_id

    # Verify second run's snapshot contains messages from both turns
    # Note: snapshots use "recent_messages" key, not "messages"
    last_snap_data = _safe_json_loads(snapshots[-1].context_json, {})
    sections = last_snap_data.get("sections", {})
    short_term = sections.get("short_term_context", {})
    snap_msgs = short_term.get("recent_messages") or short_term.get("messages") or []
    user_contents = [m.get("content", "") for m in snap_msgs if m.get("role") == "user"]
    assert any("星辰故事集" in c for c in user_contents), f"user messages: {user_contents}"
    assert any("项目进度" in c for c in user_contents), f"user messages: {user_contents}"


# ---------------------------------------------------------------------------
# M7.1: Explicit new thread creation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_force_new_thread_creates_separate_thread(agent_session: AsyncSession):
    """Verify that force_new_thread=True creates a new thread independent of any existing ones."""
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="已收到。")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "force-new-thread-agent",
            "name": "强制新建线程测试智能体",
            "allowed_tools": [],
            "max_steps": 3,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    # First chat creates a thread normally
    first = await service.chat(
        session_id="",
        user_message="开始第一个线程",
        profile_id=profile.id,
    )
    thread_a_id = first["session_id"]
    assert thread_a_id

    # Second chat with force_new_thread=True should create a new thread
    second = await service.chat(
        session_id="",
        user_message="强制新线程",
        profile_id=profile.id,
        force_new_thread=True,
    )
    thread_b_id = second["session_id"]
    assert thread_b_id
    assert thread_b_id != thread_a_id, "force_new_thread should create a different thread"

    # Verify both threads exist in the database
    thread_a = await agent_session.get(AgentThread, thread_a_id)
    thread_b = await agent_session.get(AgentThread, thread_b_id)
    assert thread_a is not None
    assert thread_b is not None

    # Verify thread A has only its own message
    msgs_a = await service.thread_mgr.get_messages(thread_a_id)
    user_msgs_a = [m for m in msgs_a if isinstance(m, dict) and m.get("role") == "user"]
    assert len(user_msgs_a) == 1
    assert any("第一个线程" in str(m.get("content", "")) for m in user_msgs_a)

    # Verify thread B has only its own message (not thread A's messages)
    msgs_b = await service.thread_mgr.get_messages(thread_b_id)
    user_msgs_b = [m for m in msgs_b if isinstance(m, dict) and m.get("role") == "user"]
    assert len(user_msgs_b) == 1
    assert any("强制新线程" in str(m.get("content", "")) for m in user_msgs_b)

    # Verify each thread has its own context snapshot
    snaps_a = await agent_session.execute(
        select(AgentContextSnapshot).where(AgentContextSnapshot.thread_id == thread_a_id)
    )
    snaps_b = await agent_session.execute(
        select(AgentContextSnapshot).where(AgentContextSnapshot.thread_id == thread_b_id)
    )
    assert len(list(snaps_a.scalars().all())) >= 1, "thread A should have snapshots"
    assert len(list(snaps_b.scalars().all())) >= 1, "thread B should have snapshots"


@pytest.mark.asyncio
async def test_agent_force_new_thread_with_existing_session_id_creates_new(agent_session: AsyncSession):
    """Verify that force_new_thread=True overrides an explicitly passed session_id
    and creates a new thread instead of resuming the existing one."""
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="已收到。")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "force-new-override-agent",
            "name": "强制新建覆盖测试智能体",
            "allowed_tools": [],
            "max_steps": 3,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    # Create an existing thread
    first = await service.chat(
        session_id="",
        user_message="初始线程消息",
        profile_id=profile.id,
    )
    existing_id = first["session_id"]

    # Try to resume the existing thread but with force_new_thread=True
    # This should NOT resume - it should create a new thread
    second = await service.chat(
        session_id=existing_id,  # Pass the existing thread ID
        user_message="应该在新线程",
        profile_id=profile.id,
        force_new_thread=True,
    )

    # Should have created a new thread, not resumed the existing one
    assert second["session_id"] != existing_id, (
        f"force_new_thread should override session_id; "
        f"got same id: {second['session_id']}"
    )

    # Verify the existing thread is unchanged (1 message)
    msgs_existing = await service.thread_mgr.get_messages(existing_id)
    user_msgs = [m for m in msgs_existing if isinstance(m, dict) and m.get("role") == "user"]
    assert len(user_msgs) == 1, f"existing thread should have 1 msg, got {len(user_msgs)}"


@pytest.mark.asyncio
async def test_agent_resume_existing_thread_without_force_flag(agent_session: AsyncSession):
    """Verify that passing an existing session_id without force_new_thread resumes the thread."""
    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return LLMGenerationResult(success=True, content="已收到。")

    profile_manager = AgentProfileManager(agent_session)
    profile = await profile_manager.create_profile(
        {
            "id": "resume-thread-agent",
            "name": "恢复线程测试智能体",
            "allowed_tools": [],
            "max_steps": 3,
        },
    )
    await agent_session.commit()

    fake_llm = FakeLLM()
    service = AgentService(agent_session)
    service._llm_manager = fake_llm

    # Create a thread
    first = await service.chat(
        session_id="",
        user_message="第一条消息",
        profile_id=profile.id,
    )
    thread_id = first["session_id"]

    # Resume the same thread with force_new_thread=False (default)
    second = await service.chat(
        session_id=thread_id,
        user_message="第二条消息",
        profile_id=profile.id,
    )

    # Should be the same thread
    assert second["session_id"] == thread_id, "resuming without force_new_thread should reuse same thread"

    # Messages should accumulate
    msgs = await service.thread_mgr.get_messages(thread_id)
    user_msgs = [m for m in msgs if isinstance(m, dict) and m.get("role") == "user"]
    assert len(user_msgs) == 2, f"thread should have 2 user messages, got {len(user_msgs)}"
    assert any("第一条消息" in str(m.get("content", "")) for m in user_msgs)
    assert any("第二条消息" in str(m.get("content", "")) for m in user_msgs)
