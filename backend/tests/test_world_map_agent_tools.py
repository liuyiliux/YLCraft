"""世界地图 Agent 工具的聚焦测试。

覆盖工具注册与风险分级、结构化读写的 revision CAS、派生动作（提示词优化
/ 成图）不改正典、版本历史 append-only 与回滚产生新版本。
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.db.models.novel_source import WorldMapDocument, WorldMapRevision
from app.services.agent.registry import ToolRegistry


def _make_env(tmp_path: Path, db_name: str = "maps.db"):
    engine = create_engine(
        f"sqlite:///{tmp_path / db_name}", connect_args={"check_same_thread": False}
    )
    WorldMapDocument.__table__.create(engine)
    WorldMapRevision.__table__.create(engine)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    @contextlib.contextmanager
    def _session_local():
        with factory() as session:
            yield session

    return engine, factory, _session_local


SAMPLE_MAP = {
    "regions": [
        {"id": "r1", "name": "北岭", "kind": "山岭"},
        {"id": "r2", "name": "南港", "kind": "港湾"},
    ],
    "nodes": [
        {"id": "n1", "name": "客栈", "kind": "据点", "x": 10, "y": 20, "region_id": "r1"},
        {"id": "n2", "name": "灯塔", "kind": "据点", "x": 80, "y": 85, "region_id": "r2"},
        {"id": "n3", "name": "关口", "kind": "关隘", "x": 50, "y": 50, "region_id": ""},
    ],
    "routes": [{"id": "rt1", "from": "n1", "to": "n2", "kind": "道路"}],
}


def test_world_map_tools_registered_with_risk_levels():
    """12 个地图工具都应注册，且写工具标记 write。"""
    import app.services.agent.tools  # noqa: F401  触发注册

    expected_read = {
        "list_world_maps",
        "get_world_map",
        "render_world_map_svg",
        "export_world_map_points",
        "resolve_world_map_entities",
        "build_world_map_visual_prompt",
        "optimize_world_map_visual_prompt",
        "list_world_map_revisions",
    }
    expected_write = {
        "create_world_map",
        "save_world_map",
        "generate_world_map_visual",
        "rollback_world_map",
    }
    for name in expected_read | expected_write:
        tool = ToolRegistry.get_tool(name)
        assert tool is not None, f"工具未注册: {name}"
        assert tool.category == "novel_source"
        assert tool.risk_level == ("write" if name in expected_write else "read")


def test_world_map_agent_read_and_cas_write(tmp_path):
    """读取 → CAS 保存：版本一致才成功，旧版本必须被拒绝。"""
    from app.services.agent.tools import world_map_tools

    engine, factory, session_local = _make_env(tmp_path)
    world_map_tools.SessionLocal = session_local
    try:
        created = world_map_tools.create_world_map(
            title="北境舆图", map_json=SAMPLE_MAP, operator="tester"
        )
        assert created["success"] is True
        map_id = created["map"]["id"]
        assert created["revision"] == 1

        detail = world_map_tools.get_world_map(map_id)
        assert detail["success"] is True
        assert len(detail["map"]["map_json"]["nodes"]) == 3

        # CAS 冲突：用旧 revision 保存应被拒绝，并告知当前版本。
        stale = world_map_tools.save_world_map(
            map_id,
            map_json={**SAMPLE_MAP, "nodes": SAMPLE_MAP["nodes"][:1]},
            expected_revision=1,
        )
        assert stale["success"] is True  # 当前就是 v1，符合预期
        assert stale["revision"] == 2

        conflict = world_map_tools.save_world_map(
            map_id,
            map_json=SAMPLE_MAP,
            expected_revision=1,
        )
        assert conflict["success"] is False
        assert "v" not in conflict["error"] or "当前版本" in conflict["error"]
        assert "2" in conflict["error"]

        # 列表与渲染
        listed = world_map_tools.list_world_maps()
        assert listed["total"] >= 1
        svg = world_map_tools.render_world_map_svg(map_id)
        assert svg["success"] is True
        assert "<svg" in svg["svg"] and "客栈" in svg["svg"]

        # 导出点位：结构化数据带据点与路线
        exported = world_map_tools.export_world_map_points(map_id)
        assert exported["success"] is True
        assert exported["data"]["nodes"]
    finally:
        engine.dispose()


def test_world_map_orphan_detection(tmp_path):
    """没有 entity_id 的据点应被识别为游离标记，而不是当作正典实体。"""
    from app.services.agent.tools import world_map_tools

    engine, factory, session_local = _make_env(tmp_path, "orphan.db")
    world_map_tools.SessionLocal = session_local
    try:
        with factory() as session:
            from app.services.novel_source.world_map import WorldMapService

            document = WorldMapService(session).create_map(title="游离测试", map_json=SAMPLE_MAP)
            map_id = document.id

        resolved = world_map_tools.resolve_world_map_entities(map_id)
        assert resolved["success"] is True
        # SAMPLE_MAP 三个据点都没有 entity_id，全部应识别为游离
        assert len(resolved["orphan_node_ids"]) == 3
        assert resolved["linked_count"] == 0
    finally:
        engine.dispose()


def test_world_map_prompt_optimize_does_not_persist(tmp_path, monkeypatch):
    """提示词优化只改写文本：不落库、不生成图、revision 不变。"""
    from app.services.agent.tools import world_map_tools
    from app.services.novel_source import world_map_visual

    class _FakeResponse:
        success = True
        content = "优化后的北境舆图提示词，保留全部地名与坐标。"

    class _FakeAI:
        def is_loaded(self):
            return True

        async def chat(self, messages, **kwargs):
            assert len(messages) == 2
            return _FakeResponse()

    monkeypatch.setattr(world_map_visual, "get_ai_service", lambda: _FakeAI())

    engine, factory, session_local = _make_env(tmp_path, "optimize.db")
    world_map_tools.SessionLocal = session_local
    try:
        with factory() as session:
            from app.services.novel_source.world_map import WorldMapService

            document = WorldMapService(session).create_map(
                title="北境舆图", map_json=SAMPLE_MAP
            )
            map_id = document.id
            before_revision = int(document.revision or 1)

        built = world_map_tools.build_world_map_visual_prompt_tool(map_id, style="水墨")
        assert built["success"] is True
        assert "北境舆图" in built["prompt"] and "北岭" in built["prompt"]
        assert "北" in built["prompt"]  # 坐标约定里的方位说明

        import asyncio

        optimized = asyncio.run(
            world_map_tools.optimize_world_map_visual_prompt_tool(
                map_id, focus="强调北岭雪线"
            )
        )
        assert optimized["success"] is True
        assert optimized["optimized_prompt"].startswith("优化后的")
        assert "北岭" in optimized["prompt"]

        # 优化不落库：版本与内容都不变
        after = world_map_tools.get_world_map(map_id)
        assert after["revision"] == before_revision
        assert len(after["map"]["map_json"]["nodes"]) == 3
    finally:
        engine.dispose()


def test_world_map_generate_visual_only_appends_reference(tmp_path, monkeypatch):
    """成图是派生资产：只追加 visuals 引用，结构化空间关系不被改写。"""
    from app.services.agent.tools import world_map_tools
    from app.services.novel_source import world_map_visual

    class _FakeResult:
        success = True
        urls = ["https://example.com/map.png"]
        all_local_paths = []
        local_path = ""
        url = "https://example.com/map.png"
        provider = "fake"
        model = "fake-model"
        task_id = "task-1"
        status = "succeeded"
        seed = None

    class _FakeAI:
        def is_loaded(self):
            return True

        async def generate_image(self, request):
            assert "北境舆图" in request.prompt
            return _FakeResult()

    monkeypatch.setattr(world_map_visual, "get_ai_service", lambda: _FakeAI())

    engine, factory, session_local = _make_env(tmp_path, "visual.db")
    world_map_tools.SessionLocal = session_local
    try:
        with factory() as session:
            from app.services.novel_source.world_map import WorldMapService

            document = WorldMapService(session).create_map(
                title="北境舆图", map_json=SAMPLE_MAP
            )
            map_id = document.id

        import asyncio

        generated = asyncio.run(
            world_map_tools.generate_world_map_visual_tool(
                map_id, style="水墨", save_to_asset_hub=False
            )
        )
        assert generated["success"] is True
        assert generated["url"].endswith(".png")

        detail = world_map_tools.get_world_map(map_id)
        data = detail["map"]["map_json"]
        assert len(data["visuals"]) == 1
        assert data["visuals"][0]["prompt"]  # 实际使用的 prompt 被记录
        # 正典数据不变：据点、区域、路线仍是原样
        assert len(data["nodes"]) == 3
        assert len(data["regions"]) == 2
        assert len(data["routes"]) == 1
    finally:
        engine.dispose()


def test_world_map_revisions_and_rollback_are_append_only(tmp_path):
    """版本历史 append-only：回滚以旧快照为内容产生新版本，历史链不被改写。"""
    from app.services.agent.tools import world_map_tools

    engine, factory, session_local = _make_env(tmp_path, "revisions.db")
    world_map_tools.SessionLocal = session_local
    try:
        created = world_map_tools.create_world_map(title="版本测试", map_json=SAMPLE_MAP)
        map_id = created["map"]["id"]

        saved = world_map_tools.save_world_map(
            map_id,
            map_json={**SAMPLE_MAP, "nodes": SAMPLE_MAP["nodes"][:1]},
            expected_revision=1,
        )
        assert saved["revision"] == 2

        history = world_map_tools.list_world_map_revisions(map_id)
        assert history["total"] == 2
        assert [row["revision"] for row in history["revisions"]] == [2, 1]

        detail = world_map_tools.list_world_map_revisions(map_id, revision=1)
        assert detail["success"] is True
        assert len(detail["revision_detail"]["map_json"]["nodes"]) == 3

        # CAS 校验：持有过期版本时拒绝回滚
        conflict = world_map_tools.rollback_world_map(map_id, 1, expected_revision=1)
        assert conflict["success"] is False
        assert "当前版本" in conflict["error"]

        rolled = world_map_tools.rollback_world_map(map_id, 1, expected_revision=2)
        assert rolled["success"] is True
        assert rolled["rolled_back_to"] == 1
        assert rolled["revision"] == 3

        after = world_map_tools.get_world_map(map_id)
        assert len(after["map"]["map_json"]["nodes"]) == 3  # 内容回到 v1
        history = world_map_tools.list_world_map_revisions(map_id)
        assert history["total"] == 3  # 历史仍在，未被改写
    finally:
        engine.dispose()
