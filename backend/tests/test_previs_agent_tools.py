"""预演台 Agent 工具的注册、授权与只读行为（tasks 5.1–5.4）。

分两层：
    A. 注册与授权：三个新工具注册成功且风险等级为 read；写工具的授权边界不变
    B. 只读行为：动作清单 / 可摆对象 / 初稿生成返回事实或空集，且**不写任何数据**
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from app.db.models.creative_project import ProjectContent
from app.db.models.previs import PrevisMotionAsset, PrevisSceneDocument
from app.services.agent.profile import DEFAULT_AGENT_PROFILES
from app.services.agent.registry import ToolRegistry
from app.services.agent.tools import previs_tools
from app.services.previs import draft_service

NEW_READ_TOOLS = ("list_previs_motions", "get_previs_composition_options", "generate_previs_draft")
WRITE_TOOL = "previs_apply_operations"
#: 允许持有预演写工具的角色（tasks 5.3：写操作授权边界**不变**）
DIRECTOR_ROLES = {"creative-director", "storyboard-director"}


def _run(coro):
    return asyncio.run(coro)


def _tools_of(profile: dict) -> list[str]:
    return list(profile.get("allowed_tools") or [])


# ---------------------------------------------------------------- A. 注册与授权

def test_new_previs_tools_are_registered_as_read_only():
    """5.1 / 5.2：三个新工具都要真的注册上，且风险等级是 read（不写库）。"""
    for name in NEW_READ_TOOLS:
        tool = ToolRegistry.get_tool(name)
        assert tool is not None, f"{name} 未注册"
        assert tool.risk_level == "read", name
        assert tool.category == "creative_project", name
        # 描述与参数说明是 Agent 唯一的文档来源，不能空着
        assert tool.description and tool.description.strip(), name


def test_new_read_tools_are_granted_to_the_two_director_roles():
    for name in NEW_READ_TOOLS:
        holders = {profile["id"] for profile in DEFAULT_AGENT_PROFILES if name in _tools_of(profile)}
        assert holders == DIRECTOR_ROLES, (name, holders)


def test_write_tool_stays_restricted_to_the_two_director_roles():
    """5.3：新增只读工具**不得**顺带放宽写工具的授权边界。

    只按**显式授权**统计：`general-director` 那类 `allowed_tools=["*"]` 的通配角色
    本来就持有全部工具（既有设计），不算"被额外角色获取"。
    """
    holders = {profile["id"] for profile in DEFAULT_AGENT_PROFILES if WRITE_TOOL in _tools_of(profile)}
    assert holders == DIRECTOR_ROLES, holders

    explicit_only = {profile["id"] for profile in DEFAULT_AGENT_PROFILES if "*" not in _tools_of(profile)}
    assert holders <= explicit_only
    # 反向核对：除这两个角色外，其余**显式列工具**的角色都不该出现写工具
    leaked = {
        profile["id"]
        for profile in DEFAULT_AGENT_PROFILES
        if profile["id"] not in DIRECTOR_ROLES and WRITE_TOOL in _tools_of(profile)
    }
    assert leaked == set(), leaked


# ---------------------------------------------------------------- B. 只读行为

class _SharedSession:
    """让工具里的 `with SessionLocal() as session` 用到测试会话，而不是提前关掉它。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *exc) -> bool:
        return False


@pytest.fixture()
def previs_session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PrevisSceneDocument.__table__.create(engine)
    ProjectContent.__table__.create(engine)
    PrevisMotionAsset.__table__.create(engine)
    with Session(engine) as session:
        monkeypatch.setattr(previs_tools, "SessionLocal", lambda: _SharedSession(session))
        monkeypatch.setattr(draft_service, "SessionLocal", lambda: _SharedSession(session))
        yield session


def _insert_motion(session: Session, slug: str, *, carrier: str = "params", category: str = "视线") -> PrevisMotionAsset:
    row = PrevisMotionAsset(
        id=f"motion-{slug}", slug=slug, name=f"{slug} 动作", carrier=carrier, category=category,
        duration_seconds=1.0, fps=24, frame_count=24, loopable=False,
        payload_json={"channels": {"head.0": [[0, 20], [12, 26]]}},
        origin="测试", license="测试许可", license_url="https://example.com/license",
    )
    session.add(row)
    session.commit()
    return row


def _insert_bound_scene(session: Session, *, content_id: str = "content-1", panel_number: int = 1) -> PrevisSceneDocument:
    session.add(ProjectContent(
        id=content_id,
        project_id="project-1",
        content_type="storyboard",
        data_json=json.dumps({"panels": [{
            "panel_number": panel_number,
            "characters": ["萧然"],
            "action": "萧然点头",
            "shot_size": "近景",
            "camera_angle": "平视",
            "duration_seconds": 3,
        }]}, ensure_ascii=False),
    ))
    row = PrevisSceneDocument(
        id="scene-tools", project_id="project-1", storyboard_content_id=content_id,
        panel_number=panel_number, title="第 1 格",
        scene_json={"fps": 24, "nodes": [], "cameras": [], "keyframes": []},
        revision=3,
    )
    session.add(row)
    session.commit()
    return row


def test_motion_catalog_returns_facts_and_an_empty_set_instead_of_guesses(previs_session):
    _insert_motion(previs_session, "nod", category="交流")
    result = _run(previs_tools.list_previs_motions())
    assert result["success"] is True and result["total"] == 1
    motion = result["motions"][0]
    assert motion["slug"] == "nod"
    assert motion["carrier"] == "params"
    assert motion["license_status"] == "recorded"
    assert result["carrier_guide"]["params"], "载体说明是 Agent 判断\"谁能吃这个动作\"的唯一依据"

    # 筛选无匹配 → 空数组 + 说明，而不是编造一个标识
    empty = _run(previs_tools.list_previs_motions(carrier="params", category="不存在的分类"))
    assert empty["motions"] == [] and empty["total"] == 0
    assert empty["empty_hint"]


def test_composition_options_only_offer_loadable_models(previs_session, monkeypatch):
    """素材库同名的图片/视频不少：只列可加载的模型格式，避免写出"加载失败"的节点。"""

    async def _fake_search(**kwargs):
        return {"success": True, "assets": [
            {"id": "asset-1", "title": "长桌", "file_path": "/data/assets/asset-1/table.glb"},
            {"id": "asset-2", "title": "参考图", "file_path": "/data/assets/asset-2/ref.png"},
        ]}

    monkeypatch.setattr("app.services.agent.tools.asset_tools.search_assets", _fake_search)
    result = _run(previs_tools.get_previs_composition_options())
    assert {item["kind"] for item in result["node_kinds"]} >= {
        "human_proxy", "asset_model", "primitive", "panorama", "light",
    }
    assert result["human_proxy"]["height_range_m"] == [0.5, 2.5]
    assert "person" in result["size_anchors_m"]
    assert [item["asset_id"] for item in result["library_models"]] == ["asset-1"]
    # 每个模型条目都必须带 asset_id：空 id 会让调用方拿到一个落不了库的引用
    assert all(item["asset_id"] for item in result["library_models"])


def test_composition_options_degrade_to_an_empty_list_when_the_library_is_unavailable(previs_session, monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("素材库不可用")

    monkeypatch.setattr("app.services.agent.tools.asset_tools.search_assets", _boom)
    result = _run(previs_tools.get_previs_composition_options())
    # 素材库挂了不该让"能摆什么"整体失败；此时是空数组 + 说明，而不是编一个 asset_id
    assert result["success"] is True
    assert result["library_models"] == []
    assert result["library_models_note"]


def test_generate_draft_returns_operations_without_writing(previs_session):
    row = _insert_bound_scene(previs_session)
    _insert_motion(previs_session, "nod", category="交流")
    before = (row.revision, dict(row.scene_json))

    result = _run(previs_tools.generate_previs_draft(scene_id=row.id))

    assert result["success"] is True and result["read_only"] is True
    assert result["panel_number"] == 1
    assert result["scene_revision"] == 3
    # 分镜的 action「点头」应被翻译成动作指派，且**通过自检**（动作清单已喂给校验器）
    assert any(item["type"] == "assign_motion" for item in result["operations"])
    assert [item["reason"] for item in result["rejected"]] == []
    assert result["summary"]["shot_size"] == "近景"
    assert result["defaults"], "分镜没写的字段必须显式列进默认值清单"
    # 刻意不返回完整场景对象：工具结果有长度上限，塞进来只会把有用信息挤掉
    assert "proposed_scene" not in result

    previs_session.refresh(row)
    assert (row.revision, dict(row.scene_json)) == before, "初稿生成必须只读"


def test_generate_draft_reports_readable_reasons_instead_of_inventing(previs_session):
    previs_session.add(PrevisSceneDocument(
        id="scene-free", title="独立场景",
        scene_json={"fps": 24, "nodes": [], "cameras": [], "keyframes": []}, revision=1,
    ))
    previs_session.commit()

    unbound = _run(previs_tools.generate_previs_draft(scene_id="scene-free"))
    assert unbound["success"] is False
    assert "未绑定项目分镜面板" in unbound["error"]

    missing = _run(previs_tools.generate_previs_draft(scene_id="nope"))
    assert missing["success"] is False
    assert "不存在" in missing["error"]
