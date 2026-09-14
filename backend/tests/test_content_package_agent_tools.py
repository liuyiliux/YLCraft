"""内容包 Agent 工具的聚焦测试。

锁住四件事：
1. 六个工具都已注册，且风险分级与「是否产生消耗」一致（读 / 写 / 消耗）；
2. 创作导演 profile 授权了这些工具——注册了但没授权等于不可用；
3. **手工改条目与重跑条目得到同一结论**：只把引用该条目的平台输出标为过期；
4. 按条目修改是「只动那一条」，其余条目与包级字段逐字不变。
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from app.db.models.creative_project import CreativeProject, ProjectContent
from app.services.agent.registry import ToolRegistry
from app.services.creative_project.service import CreativeProjectService

#: 工具名 -> 期望风险分级。消耗型（会调用模型）必须与纯写入区分开。
EXPECTED_TOOLS = {
    "get_content_package": "read",
    "plan_content_package": "costly",
    "update_content_package_item": "write",
    "retry_content_package_item": "costly",
    "save_content_package": "write",
    "build_content_package_outputs": "write",
}


@pytest.fixture
def env(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'packages.db'}", connect_args={"check_same_thread": False}
    )
    CreativeProject.__table__.create(engine)
    ProjectContent.__table__.create(engine)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    @contextlib.contextmanager
    def _session_local():
        with factory() as session:
            yield session

    return engine, factory, _session_local


@pytest.fixture(autouse=True)
def _no_model_calls(monkeypatch):
    """这些用例都不该触碰模型：内容包服务构造期会取 AIService，这里换成会报错的假件。

    本文件的写入/读取路径都不应调用模型，因此假件一旦被调用就直接失败——顺带把
    「这些工具不会偷偷产生消耗」变成一条被测试固定的性质。
    """

    class _ForbiddenAI:
        async def chat(self, *args, **kwargs):
            raise AssertionError("内容包工具的读/写路径不应调用模型")

    monkeypatch.setattr("app.services.ai.get_ai_service", lambda: _ForbiddenAI())


def _latest_package_row(env, project_id: str) -> ProjectContent:
    """按版本倒序取最新内容包（内容包与其它 ProjectContent 共表）。"""
    session_local = env[2]
    with session_local() as session:
        row = session.exec(
            select(ProjectContent)
            .where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "content_package",
            )
            .order_by(ProjectContent.version.desc(), ProjectContent.updated_at.desc())
        ).first()
        assert row is not None
        return row


def _seed(env, *, with_outputs: bool = True, output_item_ids: list[str] | None = None):
    """建一个 storybook 项目并落一份两页绘本包，可选产出平台输出。

    `output_item_ids` 用来构造「输出只引用部分条目」的情形，以便验证过期是**按依赖**
    判定的，而不是无差别作废全部输出。
    """
    _engine, _factory, session_local = env
    with session_local() as session:
        project = CreativeProject(
            title="十二生肖绘本",
            project_type="manga",
            settings_json=json.dumps({"production_profile": "storybook"}, ensure_ascii=False),
        )
        session.add(project)
        session.flush()

        package = {
            "package_type": "page_book",
            "title": "十二生肖绘本",
            "topic": "十二生肖",
            "brief": "一页一个生肖",
            "style": "中国剪纸",
            "items": [
                {
                    "id": "rat",
                    "index": 1,
                    "title": "鼠",
                    "text": "机灵的老鼠排在第一位",
                    "image_prompt": "剪纸风格的小老鼠",
                    "status": "ready",
                },
                {
                    "id": "ox",
                    "index": 2,
                    "title": "牛",
                    "text": "踏实的牛排在第二位",
                    "image_prompt": "剪纸风格的老牛",
                    "status": "ready",
                },
            ],
        }
        service = CreativeProjectService(session)
        content = service.save_content_package(project_id=project.id, package=package)

        if with_outputs:
            service.build_content_package_outputs(
                project.id, adapters=["pdf_ebook", "asset_bundle"], save=True
            )
        if output_item_ids is not None:
            # 直接改写最新版输出的 source_item_ids，构造「只依赖部分条目」的情形
            row = session.exec(
                select(ProjectContent)
                .where(
                    ProjectContent.project_id == project.id,
                    ProjectContent.content_type == "content_package",
                )
                .order_by(ProjectContent.version.desc(), ProjectContent.updated_at.desc())
            ).first()
            assert row is not None
            data = json.loads(row.data_json)
            data["outputs"] = [
                {**item, "source_item_ids": list(output_item_ids)}
                for item in data.get("outputs") or []
            ]
            row.data_json = json.dumps(data, ensure_ascii=False)
            session.add(row)
            session.commit()

        return project.id, content.id


# ---------------------------------------------------------------------------
# 1. 注册与风险分级
# ---------------------------------------------------------------------------


def test_content_package_tools_registered_with_risk_levels():
    """六个工具都应注册，风险分级与「是否消耗额度」一致。"""
    import app.services.agent.tools  # noqa: F401  触发注册

    for name, risk in EXPECTED_TOOLS.items():
        tool = ToolRegistry.get_tool(name)
        assert tool is not None, f"{name} 未注册"
        assert tool.risk_level == risk, f"{name} 风险分级应为 {risk}"
        assert tool.category == "creative_project", f"{name} 分类应为 creative_project"


def test_package_tools_are_authorized_for_creative_director():
    """注册了但没进 allowed_tools 等于不可用，因此必须显式断言授权。"""
    from app.services.agent.profile import DEFAULT_AGENT_PROFILES

    director = next(item for item in DEFAULT_AGENT_PROFILES if item["id"] == "creative-director")
    allowed = set(director["allowed_tools"])
    for name in EXPECTED_TOOLS:
        assert name in allowed, f"创作导演未授权 {name}"


def test_costly_tools_are_separated_from_plain_writes():
    """消耗型必须与纯写入分开——前者要用户确认，后者只是改项目内容。"""
    import app.services.agent.tools  # noqa: F401

    costly = {name for name, risk in EXPECTED_TOOLS.items() if risk == "costly"}
    assert costly == {"plan_content_package", "retry_content_package_item"}
    for name in costly:
        assert ToolRegistry.get_tool(name).cost_hint, f"{name} 应给出成本提示"


# ---------------------------------------------------------------------------
# 2. 读取
# ---------------------------------------------------------------------------


def test_get_content_package_returns_latest_and_history(env):
    from app.services.agent.tools import creative_project_tools

    project_id, first_version_id = _seed(env, with_outputs=False)
    creative_project_tools.SessionLocal = env[2]

    latest = asyncio.run(creative_project_tools.get_content_package(project_id))
    assert latest["success"] is True
    package = latest["package"]
    assert package is not None
    assert package["data"]["package_type"] == "page_book"
    assert [item["id"] for item in package["data"]["items"]] == ["rat", "ox"]

    history = asyncio.run(
        creative_project_tools.get_content_package(project_id, include_history=True)
    )
    assert history["success"] is True
    assert [item["id"] for item in history["packages"]] == [first_version_id]


def test_get_content_package_on_project_without_package_returns_none(env):
    """没有内容包时返回 None，而不是抛错——调用方据此判断「还没生成」。"""
    from app.services.agent.tools import creative_project_tools

    _engine, _factory, session_local = env
    with session_local() as session:
        project = CreativeProject(
            title="空的绘本",
            project_type="manga",
            settings_json=json.dumps({"production_profile": "storybook"}),
        )
        session.add(project)
        session.commit()
        project_id = project.id

    creative_project_tools.SessionLocal = env[2]
    result = asyncio.run(creative_project_tools.get_content_package(project_id))
    assert result["success"] is True
    assert result["package"] is None


# ---------------------------------------------------------------------------
# 3. 按条目修改：只动一条 + 只让引用它的输出过期
# ---------------------------------------------------------------------------


def test_update_item_changes_only_that_item_and_stales_dependent_outputs(env):
    """核心语义：改一条 → 其余条目逐字不变；引用它的输出标记过期；版本链指向上一版。"""
    from app.services.agent.tools import creative_project_tools

    project_id, _ = _seed(env)
    creative_project_tools.SessionLocal = env[2]

    before_package = asyncio.run(creative_project_tools.get_content_package(project_id))["package"]
    before_data = before_package["data"]

    result = asyncio.run(
        creative_project_tools.update_content_package_item(
            project_id, "rat", text="机灵的老鼠抢到了头香"
        )
    )
    assert result["success"] is True

    after = result["package"]["data"]
    items = {item["id"]: item for item in after["items"]}

    # 目标条目被改写
    assert items["rat"]["text"] == "机灵的老鼠抢到了头香"
    # 兄弟条目逐字不变（含未被 patch 的字段）
    assert items["ox"] == next(i for i in before_data["items"] if i["id"] == "ox")
    # 包级字段不变
    assert after["package_type"] == before_data["package_type"]
    assert after["style"] == before_data["style"]

    # 版本链：新版本指回保存前的那一版
    assert result["package"]["source_content_id"] == before_package["id"]

    # 当前适配器产物是整包级的，其 source_item_ids 覆盖全部条目 → 改任一条都会过期
    assert result["stale_adapter_types"], "引用该条目的输出应被标记过期"
    stale = [o for o in after["outputs"] if o.get("status") == "stale"]
    assert stale, "应有被标记过期的输出"
    assert all(o.get("stale_reason") == "来源条目已变更" for o in stale)


def test_update_item_leaves_unrelated_output_ready(env):
    """按依赖判定：只引用**另一条**的输出不得被作废。"""
    from app.services.agent.tools import creative_project_tools

    project_id, _ = _seed(env, output_item_ids=["ox"])
    creative_project_tools.SessionLocal = env[2]

    result = asyncio.run(
        creative_project_tools.update_content_package_item(project_id, "rat", title="灵鼠")
    )
    assert result["success"] is True
    assert result["stale_adapter_types"] == []
    # 输出只依赖 ox，而改动的是 rat → 应保持原状
    assert all(o["status"] != "stale" for o in result["package"]["data"]["outputs"])


def test_update_item_requires_a_field_and_known_item(env):
    """给不出字段、或条目不存在时都要明确报错，而不是静默成功。"""
    from app.services.agent.tools import creative_project_tools

    project_id, _ = _seed(env, with_outputs=False)
    creative_project_tools.SessionLocal = env[2]

    with pytest.raises(ValueError, match="至少要提供一个要修改的字段"):
        asyncio.run(creative_project_tools.update_content_package_item(project_id, "rat"))

    with pytest.raises(ValueError, match="没有 id 为 nope 的条目"):
        asyncio.run(creative_project_tools.update_content_package_item(project_id, "nope", text="x"))


def test_update_item_rejects_illegal_status(env):
    """status 越界必须被契约挡住——它来自 content_package_schema 的硬校验。"""
    from app.services.agent.tools import creative_project_tools

    project_id, _ = _seed(env, with_outputs=False)
    creative_project_tools.SessionLocal = env[2]

    with pytest.raises(ValueError, match="status 非法"):
        asyncio.run(
            creative_project_tools.update_content_package_item(project_id, "rat", status="bogus")
        )


# ---------------------------------------------------------------------------
# 4. 保存与平台输出
# ---------------------------------------------------------------------------


def test_save_tool_rejects_non_object_json(env):
    from app.services.agent.tools import creative_project_tools

    project_id, _ = _seed(env, with_outputs=False)
    creative_project_tools.SessionLocal = env[2]

    with pytest.raises(ValueError, match="必须是有效 JSON 对象"):
        asyncio.run(creative_project_tools.save_content_package(project_id, "[]"))


def test_build_outputs_preview_does_not_persist(env):
    """save=False 只预览：不得追加新版本（否则界面「输出适配」会被未确认的结果点亮）。"""
    from app.services.agent.tools import creative_project_tools

    project_id, _ = _seed(env, with_outputs=False)
    creative_project_tools.SessionLocal = env[2]

    preview = asyncio.run(
        creative_project_tools.build_content_package_outputs(project_id, save=False)
    )
    assert preview["success"] is True
    assert preview["outputs"], "预览也应产出适配器结果"
    assert preview["package"] is None, "save=False 不应落库"

    versions = asyncio.run(
        creative_project_tools.get_content_package(project_id, include_history=True)
    )
    assert len(versions["packages"]) == 1, "预览不应新增版本"


def test_build_outputs_defaults_to_profile_declared_adapters(env):
    """不传 adapters 时按方案声明出——storybook 声明的是 pdf + 素材包。"""
    from app.services.agent.tools import creative_project_tools

    project_id, _ = _seed(env, with_outputs=False)
    creative_project_tools.SessionLocal = env[2]

    result = asyncio.run(creative_project_tools.build_content_package_outputs(project_id))
    assert result["success"] is True
    assert [item["adapter_type"] for item in result["outputs"]] == ["pdf_ebook", "asset_bundle"]
    # 每条输出都带溯源，才能判定「源包改了、输出过期了」
    for output in result["outputs"]:
        assert output["source_package_id"]
        assert output["source_package_version"] >= 1
        assert output["source_item_ids"] == ["rat", "ox"]
