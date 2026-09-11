"""写作风格档案 Agent 工具的聚焦测试。

锁住三件事：工具已注册且风险分级正确、Agent 与真人走同一服务层、
草稿→审核→激活→绑定是分离的步骤（提取绝不会自动生效）。
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from app.db.models.creative_project import (
    CreativeProject,
    ProjectWritingStyleLink,
    WritingStyleProfile,
)
from app.db.models.novel_source import NovelSourceSnapshot, NovelTextChunk
from app.services.agent.registry import ToolRegistry


@pytest.fixture
def env(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'styles.db'}", connect_args={"check_same_thread": False}
    )
    CreativeProject.__table__.create(engine)
    WritingStyleProfile.__table__.create(engine)
    ProjectWritingStyleLink.__table__.create(engine)
    NovelSourceSnapshot.__table__.create(engine)
    NovelTextChunk.__table__.create(engine)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    @contextlib.contextmanager
    def _session_local():
        with factory() as session:
            yield session

    return engine, factory, _session_local


def test_writing_style_tools_registered_with_risk_levels():
    """13 个风格工具都应注册：5 个只读，8 个写。"""
    import app.services.agent.tools  # noqa: F401  触发注册

    read_tools = {
        "list_writing_style_profiles",
        "get_writing_style_profile",
        "list_writing_style_projects",
        "export_writing_style_skill",
        "review_prose_style_deviation",
    }
    write_tools = {
        "extract_writing_style_from_source",
        "review_writing_style_profile",
        "activate_writing_style_profile",
        "bind_project_writing_style",
        "unbind_project_writing_style",
        "archive_writing_style_profile",
        "restore_writing_style_profile",
        "import_writing_style_skill",
    }
    for name in read_tools | write_tools:
        tool = ToolRegistry.get_tool(name)
        assert tool is not None, f"{name} 未注册"
        expected = "read" if name in read_tools else "write"
        assert tool.risk_level == expected, f"{name} 风险分级应为 {expected}"


def _seed(env):
    engine, _factory, session_local = env
    with session_local() as session:
        project = CreativeProject(title="改编项目", project_type="novel", source_type="original_idea")
        session.add(project)
        snapshot = NovelSourceSnapshot(title="活着", author="余华")
        session.add(snapshot)
        session.flush()
        session.add(
            NovelTextChunk(
                snapshot_id=snapshot.id,
                ordinal=0,
                start_offset=0,
                end_offset=30,
                content="福贵牵着牛走过田埂。天很热。\n\n“歇会儿吧。”他说。",
            )
        )
        session.commit()
        return project.id, snapshot.id


def test_profile_lifecycle_is_stepwise_for_agent(env, monkeypatch):
    """提取只出 draft；激活与绑定必须显式调用，且不改项目正典。"""
    from app.services.agent.tools import writing_style_tools

    project_id, snapshot_id = _seed(env)
    writing_style_tools.SessionLocal = env[2]

    class _FakeAI:
        async def chat(self, messages, provider=None, model=None, **kwargs):
            return type(
                "R",
                (),
                {
                    "success": True,
                    "content": json.dumps(
                        {
                            "dimensions": {
                                "句式长度与节奏": {
                                    "value": "短句推进",
                                    "confidence": 0.7,
                                    "evidence_summary": "平均句长低",
                                }
                            },
                            "new_examples": ["他推开门。"],
                            "anti_template_constraints": ["避免三段式"],
                            "prohibited_source_material": ["禁止带出角色名"],
                        },
                        ensure_ascii=False,
                    ),
                    "error": None,
                },
            )()

    monkeypatch.setattr("app.services.ai.get_ai_service", lambda: _FakeAI())

    extracted = asyncio.run(
        writing_style_tools.extract_writing_style_from_source(snapshot_id=snapshot_id)
    )
    assert extracted["success"] is True
    profile = extracted["profile"]
    assert profile["status"] == "draft"  # 绝不会自动激活
    profile_id = profile["id"]

    # 未审核直接激活会被拒绝（确认边界与真人一致）
    denied = writing_style_tools.activate_writing_style_profile(profile_id)
    assert denied["success"] is False

    reviewed = writing_style_tools.review_writing_style_profile(profile_id)
    assert reviewed["success"] is True and reviewed["profile"]["status"] == "reviewed"

    activated = writing_style_tools.activate_writing_style_profile(profile_id)
    assert activated["profile"]["status"] == "active"

    bound = writing_style_tools.bind_project_writing_style(
        project_id, profile_id, intensity="subtle"
    )
    assert bound["success"] is True and bound["intensity"] == "subtle"

    # 绑定只是运行时关联，不把风格内容复制进项目
    with env[2]() as session:
        links = session.exec(select(ProjectWritingStyleLink)).all()
        assert len(links) == 1
        assert links[0].project_id == project_id
        project = session.get(CreativeProject, project_id)
        assert "句式" not in json.dumps(
            {
                "outline": project.outline_json,
                "settings": project.settings_json,
            },
            ensure_ascii=False,
        )

    unbound = writing_style_tools.unbind_project_writing_style(project_id, profile_id)
    assert unbound["success"] is True
    with env[2]() as session:
        assert len(session.exec(select(ProjectWritingStyleLink)).all()) == 0


def test_list_and_get_tools_return_profiles(env):
    from app.services.agent.tools import writing_style_tools
    from app.services.creative_project.writing_style import WritingStyleService

    writing_style_tools.SessionLocal = env[2]
    with env[2]() as session:
        WritingStyleService(session).create_profile(
            name="冷峻白描", profile={"dimensions": {"语体": {"value": "白描"}}}
        )
        session.commit()

    listed = writing_style_tools.list_writing_style_profiles()
    assert listed["total"] == 1
    got = writing_style_tools.get_writing_style_profile(listed["profiles"][0]["id"])
    assert got["success"] is True and got["profile"]["name"] == "冷峻白描"
    assert writing_style_tools.get_writing_style_profile("missing")["success"] is False


def test_extract_tool_reports_missing_snapshot(env):
    from app.services.agent.tools import writing_style_tools

    writing_style_tools.SessionLocal = env[2]

    import asyncio

    result = asyncio.run(
        writing_style_tools.extract_writing_style_from_source(snapshot_id="missing")
    )
    assert result["success"] is False
    assert "来源快照不存在" in result["error"]


def test_agent_can_undo_its_own_archive(env):
    """Agent 能归档就必须能撤销归档，否则归档等于删除。

    恢复到草稿、不跳级；绑定保留但要重走审核与激活才生效。
    """
    from app.services.agent.tools import writing_style_tools
    from app.services.creative_project.writing_style import WritingStyleService

    writing_style_tools.SessionLocal = env[2]
    with env[2]() as session:
        service = WritingStyleService(session)
        project = CreativeProject(title="Agent 归档", project_type="novel")
        session.add(project)
        session.flush()
        item = service.create_profile(
            name="待归档", profile={"dimensions": {"语体": {"value": "白描"}}}
        )
        service.review(item.id)
        service.activate(item.id)
        service.bind(project.id, item.id, stage_scope=["novel_body"])
        project_id, profile_id = project.id, item.id

    archived = writing_style_tools.archive_writing_style_profile(profile_id)
    assert archived["success"] is True
    assert archived["profile"]["status"] == "archived"

    restored = writing_style_tools.restore_writing_style_profile(profile_id)
    assert restored["success"] is True
    assert restored["profile"]["status"] == "draft"  # 只回草稿，不跳级

    with env[2]() as session:
        service = WritingStyleService(session)
        # 绑定关系保留，但取消归档不等于重新生效
        assert service.runtime_profiles(project_id, stage="novel_body") == []
        service.review(profile_id)
        service.activate(profile_id)
        assert [
            p["id"] for p in service.runtime_profiles(project_id, stage="novel_body")
        ] == [profile_id]

    # 未知 id 给出明确错误，而不是静默成功
    assert writing_style_tools.restore_writing_style_profile("missing")["success"] is False
