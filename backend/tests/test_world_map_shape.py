"""区域形状语义参数（阶段 4）的聚焦测试。

覆盖：受控词表校验与越界回退、map_json 宽松清理（未知字段保留）、
SVG 渲染使用新几何、shape/generate 预览端点（显式参数 + LLM 推断）、
Agent 工具 generate_region_shape / list_region_shape_presets。

纪律基线（决策 D-1）：后端只产语义参数与 seed，**任何路径都不产生顶点**。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.db.models.novel_source import WorldMapDocument, WorldMapRevision
from app.services.novel_source.world_map import (
    MAX_SHAPE_VERTICES,
    WorldMapService,
    render_map_svg,
    sanitize_map_json,
)
from app.services.novel_source.world_map_shape import (
    DEFAULT_SHAPE_PARAMS,
    hash_seed,
    normalize_shape_params,
)


def _make_env(tmp_path: Path, db_name: str = "shape.db"):
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


SHAPE_REGION_MAP = {
    "regions": [
        {
            "id": "r1",
            "name": "徐家村",
            "kind": "村落",
            "parent_id": None,
            "custom_note": "未知字段应原样保留",
        },
        {"id": "r2", "name": "县城", "kind": "城池"},
    ],
    "nodes": [
        {"id": "n1", "name": "福贵的房子", "kind": "据点", "x": 40, "y": 50, "region_id": "r1"},
        {"id": "n2", "name": "村口老槐树", "kind": "场景", "x": 55, "y": 60, "region_id": "r1"},
    ],
    "routes": [],
}


def test_normalize_shape_params_falls_back_and_records():
    """词表内的值原样通过；越界值回退默认并记录键名；irregularity 夹到 0-1。"""
    params, fallbacks = normalize_shape_params(
        {
            "nature": "河谷",
            "settlement": "沿河狭长",
            "structure": "",
            "scale": "大",
            "irregularity": 0.7,
        }
    )
    assert params == {
        "nature": "河谷",
        "settlement": "沿河狭长",
        "structure": "",
        "scale": "大",
        "irregularity": 0.7,
    }
    assert fallbacks == []

    bad, bad_keys = normalize_shape_params(
        {"nature": "星空", "settlement": "环形都市", "structure": "轨道电梯", "scale": "巨大", "irregularity": 9}
    )
    assert bad["nature"] == DEFAULT_SHAPE_PARAMS["nature"]
    assert bad["settlement"] == DEFAULT_SHAPE_PARAMS["settlement"]
    assert bad["structure"] == ""  # structure 越界回退为"无"
    assert bad["scale"] == DEFAULT_SHAPE_PARAMS["scale"]
    assert bad["irregularity"] == 1.0  # 夹到上限而不是回退默认
    assert set(bad_keys) == {"nature", "settlement", "structure", "scale"}

    non_numeric, _ = normalize_shape_params({"irregularity": "很碎"})
    assert non_numeric["irregularity"] == DEFAULT_SHAPE_PARAMS["irregularity"]


def test_hash_seed_is_stable_fnv1a():
    """FNV-1a 32bit（与前端 hashSeed 同算法）：同输入同输出，非负整数。"""
    assert hash_seed("r1") == hash_seed("r1")
    assert hash_seed("r1") != hash_seed("r2")
    assert 0 <= hash_seed("anything") < 2**32


def test_sanitize_map_json_keeps_unknown_fields_and_clamps_vertices():
    """宽松校验：未知字段原样保留；顶点截断/裁剪；非对象 shape 丢弃；parent_id 收敛。"""
    bad_vertices = [[5, 5]] * (MAX_SHAPE_VERTICES + 10) + [["x", "y"], 42, [1, 2, 3]]
    cleaned = sanitize_map_json(
        {
            "regions": [
                {
                    "id": "r1",
                    "name": "徐家村",
                    "custom": {"anything": 1},
                    "parent_id": 99,
                    "shape": {"mode": "manual", "seed": 7, "params": {"nature": "山地"}, "vertices": bad_vertices},
                },
                {"id": "r2", "shape": "not-a-dict"},
                "not-a-region",
            ],
            "nodes": [{"id": "n1", "x": 1, "y": 2}],
        }
    )
    regions = cleaned["regions"]
    assert regions[2] == "not-a-region"  # 非 dict 区域原样保留（宽松）
    shape = regions[0]["shape"]
    assert len(shape["vertices"]) == MAX_SHAPE_VERTICES  # 截断到上限
    assert all(len(pair) == 2 and 0 <= pair[0] <= 100 and 0 <= pair[1] <= 100 for pair in shape["vertices"])
    assert shape["params"] == {"nature": "山地"}  # shape 内未知字段不动
    assert regions[0]["custom"] == {"anything": 1}
    assert regions[0]["parent_id"] is None  # 非字符串归 None
    assert regions[1].get("shape") is None  # 非 dict shape 丢弃
    assert cleaned["nodes"] == [{"id": "n1", "x": 1, "y": 2}]  # 节点透传

    assert sanitize_map_json(None)["regions"] == []
    assert sanitize_map_json("junk")["regions"] == []


def test_sanitize_applied_on_save(tmp_path):
    """写入路径（create/update CAS）都过宽松校验：超限顶点入库时被收敛。"""
    engine, factory, _session_local = _make_env(tmp_path)
    try:
        with factory() as session:
            service = WorldMapService(session)
            document = service.create_map(
                title="清理测试",
                map_json={
                    "regions": [
                        {"id": "r1", "name": "徐家村", "shape": {"mode": "auto", "vertices": [[300, -5]] * 70}}
                    ],
                    "nodes": [],
                    "routes": [],
                },
            )
            data = json.loads(document.map_json)
            vertices = data["regions"][0]["shape"]["vertices"]
            assert len(vertices) == MAX_SHAPE_VERTICES
            assert vertices[0] == [100.0, 0.0]  # 300→100, -5→0
    finally:
        engine.dispose()


def test_render_map_svg_draws_region_polygons_with_depth(tmp_path):
    """SVG 用已入库形状画区域：父淡虚线、子实线，无顶点的区域跳过。"""
    engine, factory, _session_local = _make_env(tmp_path)
    try:
        with factory() as session:
            document = WorldMapService(session).create_map(
                title="区域渲染",
                map_json={
                    "regions": [
                        {
                            "id": "r1",
                            "name": "北岭",
                            "shape": {
                                "mode": "auto",
                                "vertices": [[10, 10], [10, 90], [90, 90], [90, 10]],
                            },
                        },
                        {
                            "id": "r2",
                            "name": "县城",
                            "parent_id": "r1",
                            "shape": {
                                "mode": "auto",
                                "vertices": [[40, 40], [40, 60], [60, 60], [60, 40]],
                            },
                        },
                        {"id": "r3", "name": "无形状区域"},
                    ],
                    "nodes": [{"id": "n1", "name": "客栈", "x": 50, "y": 50, "region_id": "r2"}],
                    "routes": [],
                },
            )
            svg = render_map_svg(document)
    finally:
        engine.dispose()

    assert svg.count("<polygon") == 2  # r3 无顶点不画
    assert "北岭" in svg and "县城" in svg  # 区域名标签
    assert 'stroke-dasharray="6 4"' in svg  # 父区域虚线
    assert 'fill-opacity="0.06"' in svg and 'fill-opacity="0.1"' in svg  # 父淡子艳
    # 区域多边形垫在据点之前（绘制顺序）
    assert svg.index("<polygon") < svg.index("<circle")


def test_shape_generate_endpoint_explicit_and_llm(tmp_path, monkeypatch):
    """shape/generate 端点：显式参数直接校验返回；未给时 LLM 推断；都只产参数不含顶点。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1 import novel_sources as novel_sources_api
    from app.db.database import get_session
    from app.services.novel_source import world_map_shape

    engine, factory, session_local = _make_env(tmp_path, "endpoint.db")
    try:
        with factory() as session:
            document = WorldMapService(session).create_map(
                title="徐家村舆图", map_json=SHAPE_REGION_MAP
            )
            map_id = document.id

        class _FakeResponse:
            success = True
            content = "```json\n{\"nature\": \"河谷\", \"settlement\": \"散点村落\", \"structure\": \"轨道电梯\", \"scale\": \"小\", \"irregularity\": \"很碎\"}\n```"

        class _FakeAI:
            def is_loaded(self):
                return True

            async def chat(self, messages, **kwargs):
                assert "徐家村" in messages[1].content
                assert "福贵的房子" in messages[1].content
                assert "不要输出任何顶点" in messages[0].content
                return _FakeResponse()

        monkeypatch.setattr(world_map_shape, "get_ai_service", lambda: _FakeAI())

        app = FastAPI()
        app.include_router(novel_sources_api.router)

        def _override_session():
            with factory() as db:
                yield db

        app.dependency_overrides[get_session] = _override_session
        client = TestClient(app)

        # 显式参数：不调模型，越界值回退并记录
        response = client.post(
            f"/api/v1/world-maps/{map_id}/regions/r1/shape/generate",
            json={"params": {"nature": "森林", "scale": "巨大"}, "seed": 123},
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["source"] == "explicit"
        assert payload["params"]["nature"] == "森林"
        assert payload["params"]["scale"] == "中"  # 越界回退
        assert payload["fallbacks"] == ["scale"]
        assert payload["seed"] == 123
        assert payload["vertices"] == []  # 决策 D-1：不含顶点

        # LLM 推断：解析围栏 JSON，越界回退 + 记录
        response = client.post(
            f"/api/v1/world-maps/{map_id}/regions/r1/shape/generate", json={}
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["source"] == "llm"
        assert payload["params"]["nature"] == "河谷"
        assert payload["params"]["structure"] == ""  # 越界 structure → 无
        assert payload["seed"] == hash_seed("r1")  # 缺省按区域 id 稳定派生
        assert set(payload["fallbacks"]) == {"structure", "irregularity"}

        # 区域不存在 → 404
        missing = client.post(
            f"/api/v1/world-maps/{map_id}/regions/ghost/shape/generate", json={}
        )
        assert missing.status_code == 404
    finally:
        engine.dispose()


def test_agent_tools_region_shape(tmp_path, monkeypatch):
    """Agent 工具：词表只读；generate 写入参数（CAS 落历史），手绘区域默认拒绝。"""
    from app.services.agent.registry import ToolRegistry
    import app.services.agent.tools  # noqa: F401  触发注册
    from app.services.agent.tools import world_map_tools
    from app.services.novel_source import world_map_shape

    engine, factory, session_local = _make_env(tmp_path, "tools.db")
    world_map_tools.SessionLocal = session_local
    try:
        presets = world_map_tools.list_region_shape_presets()
        assert presets["success"] is True
        assert "河谷" in presets["nature"] and "沿河狭长" in presets["settlement"]
        assert presets["max_vertices"] == MAX_SHAPE_VERTICES

        tool = ToolRegistry.get_tool("generate_region_shape")
        assert tool is not None and tool.risk_level == "write"
        assert ToolRegistry.get_tool("list_region_shape_presets").risk_level == "read"

        with factory() as session:
            document = WorldMapService(session).create_map(
                title="徐家村舆图", map_json=SHAPE_REGION_MAP
            )
            map_id = document.id

        generated = asyncio.run(
            world_map_tools.generate_region_shape(
                map_id, "r1", params={"nature": "河谷", "settlement": "沿河狭长"}
            )
        )
        assert generated["success"] is True
        assert generated["params"]["nature"] == "河谷"
        assert generated["seed"] == hash_seed("r1")
        assert generated["revision"] == 2  # CAS 落库 +1

        detail = world_map_tools.get_world_map(map_id)
        region = next(r for r in detail["map"]["map_json"]["regions"] if r["id"] == "r1")
        assert region["shape"]["mode"] == "auto"
        assert region["shape"]["params"]["settlement"] == "沿河狭长"
        assert region["shape"]["vertices"] == []  # 不含顶点
        assert region["custom_note"] == "未知字段应原样保留"

        # 手绘区域：默认拒绝覆盖，overwrite=true 才放行
        with factory() as session:
            WorldMapService(session).update_map(
                map_id,
                map_json={
                    **SHAPE_REGION_MAP,
                    "regions": [
                        {
                            **SHAPE_REGION_MAP["regions"][0],
                            "shape": {"mode": "manual", "vertices": [[1, 1], [1, 9], [9, 9]]},
                        },
                        SHAPE_REGION_MAP["regions"][1],
                    ],
                },
                expected_revision=2,
            )
        refused = asyncio.run(
            world_map_tools.generate_region_shape(map_id, "r1", params={"nature": "山地"})
        )
        assert refused["success"] is False
        assert "manual" in refused["error"]

        overridden = asyncio.run(
            world_map_tools.generate_region_shape(
                map_id, "r1", params={"nature": "山地"}, overwrite=True
            )
        )
        assert overridden["success"] is True
        detail = world_map_tools.get_world_map(map_id)
        region = next(r for r in detail["map"]["map_json"]["regions"] if r["id"] == "r1")
        assert region["shape"]["params"]["nature"] == "山地"

        # LLM 推断路径（fake AI，裸 JSON；缺键按默认补齐——缺键不是越界，不记 fallback）
        class _FakeResponse:
            success = True
            content = "{\"nature\": \"海岸\", \"irregularity\": 0.2}"

        class _FakeAI:
            def is_loaded(self):
                return True

            async def chat(self, messages, **kwargs):
                return _FakeResponse()

        monkeypatch.setattr(world_map_shape, "get_ai_service", lambda: _FakeAI())
        inferred = asyncio.run(
            world_map_tools.generate_region_shape(map_id, "r2")
        )
        assert inferred["success"] is True
        assert inferred["source"] == "llm"
        assert inferred["params"]["nature"] == "海岸"
        assert inferred["params"]["settlement"] == "圆形寨子"  # 缺键回退默认
        assert inferred["fallbacks"] == []

        # 区域不存在
        ghost = asyncio.run(
            world_map_tools.generate_region_shape(map_id, "ghost", params={"nature": "山地"})
        )
        assert ghost["success"] is False
    finally:
        engine.dispose()


def test_map_export_carries_region_shape(tmp_path):
    """验收 7 前半：点位 JSON 导出随区域原样携带 shape（含顶点与语义参数）。"""
    from app.services.novel_source.world_map import build_map_export

    engine, factory, _session_local = _make_env(tmp_path, "export.db")
    try:
        with factory() as session:
            document = WorldMapService(session).create_map(
                title="导出测试",
                map_json={
                    "regions": [
                        {
                            "id": "r1",
                            "name": "徐家村",
                            "parent_id": None,
                            "shape": {
                                "mode": "manual",
                                "seed": 7,
                                "params": {"nature": "河谷", "scale": "小"},
                                "vertices": [[10, 10], [10, 40], [40, 40], [40, 10]],
                            },
                        }
                    ],
                    "nodes": [],
                    "routes": [],
                },
            )
            exported = build_map_export(document)
    finally:
        engine.dispose()

    region = exported["regions"][0]
    assert region["shape"]["mode"] == "manual"
    assert region["shape"]["params"]["nature"] == "河谷"
    assert len(region["shape"]["vertices"]) == 4
    assert region["parent_id"] is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('前置说明 {"nature": "山地"} 后置说明', {"nature": "山地"}),
        ("```json\n{\"settlement\": \"带状街区\"}\n```", {"settlement": "带状街区"}),
    ],
)
def test_extract_json_object_tolerates_fences_and_chatter(raw, expected):
    from app.services.novel_source.world_map_shape import _extract_json_object

    assert _extract_json_object(raw) == expected


def test_infer_requires_loaded_ai_service(monkeypatch):
    """AIService 未配置时给明确错误，而不是静默用默认参数。"""
    from app.services.novel_source import world_map_shape

    class _NotLoaded:
        def is_loaded(self):
            return False

    monkeypatch.setattr(world_map_shape, "get_ai_service", lambda: _NotLoaded())
    with pytest.raises(RuntimeError, match="AIService"):
        asyncio.run(
            world_map_shape.infer_shape_params(region={"id": "r1", "name": "北岭"}, members=[])
        )
