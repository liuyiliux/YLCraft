from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.api.v1 import previs as previs_api
from app.db.models.creative_project import CreativeProject, ProjectAssetLink, ProjectContent
from app.db.models.previs import PrevisSceneDocument


@pytest.fixture()
def previs_session_factory(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'previs.db'}")
    PrevisSceneDocument.__table__.create(engine)
    factory = sessionmaker(class_=Session, autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(previs_api, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture()
def previs_client(previs_session_factory):
    app = FastAPI()
    app.include_router(previs_api.router, prefix="/api/v1/previs")
    return TestClient(app)


def _create_payload(**overrides) -> dict:
    payload = {
        "project_id": "project-1",
        "storyboard_content_id": "content-1",
        "panel_number": 1,
        "title": "第 1 镜预演",
        "scene": {
            "fps": 24,
            "durationFrames": 0,
            "activeCameraId": "cam-1",
            "nodes": [{"id": "node-1", "kind": "asset_model", "name": "角色", "assetId": "asset-1"}],
            "cameras": [{"id": "cam-1", "name": "机位 1", "fov": 50}],
            "keyframes": [],
            "settings": {},
        },
    }
    payload.update(overrides)
    return payload


def test_previs_scene_create_and_round_trip(previs_client):
    create_response = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["project_id"] == "project-1"
    assert created["storyboard_content_id"] == "content-1"
    assert created["panel_number"] == 1
    assert created["revision"] == 1
    assert created["scene"]["nodes"][0]["id"] == "node-1"

    get_response = previs_client.get(f"/api/v1/previs/scenes/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["revision"] == 1


def test_previs_scene_rejects_duplicate_panel(previs_client):
    first = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert first.status_code == 200

    duplicate = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_previs_scene_save_requires_matching_revision(previs_client):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    save_response = previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": "更新后", "scene": created["scene"]},
    )
    assert save_response.status_code == 200
    assert save_response.json()["data"]["revision"] == 2

    stale_response = previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": "过期保存", "scene": created["scene"]},
    )
    assert stale_response.status_code == 409
    detail = stale_response.json()["detail"]
    assert detail["current_revision"] == 2
    assert detail["expected_revision"] == 1


def test_previs_scene_list_filters_by_panel(previs_client):
    previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    previs_client.post(
        "/api/v1/previs/scenes",
        json=_create_payload(panel_number=2, title="第 2 镜预演"),
    )

    all_response = previs_client.get("/api/v1/previs/scenes?project_id=project-1")
    assert all_response.status_code == 200
    assert all_response.json()["total"] == 2

    filtered = previs_client.get(
        "/api/v1/previs/scenes?project_id=project-1&storyboard_content_id=content-1&panel_number=2"
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["data"][0]["panel_number"] == 2


def test_previs_scene_delete(previs_client):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    delete_response = previs_client.delete(f"/api/v1/previs/scenes/{scene_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_id"] == scene_id
    assert previs_client.get(f"/api/v1/previs/scenes/{scene_id}").status_code == 404


def test_previs_scene_rejects_non_object_scene(previs_client):
    response = previs_client.post(
        "/api/v1/previs/scenes",
        json=_create_payload(scene="not-an-object"),
    )
    assert response.status_code == 422


def test_previs_standalone_scene_create_and_round_trip(previs_client):
    # 独立场景：不绑定项目分镜，纯思路摆位，用于生图参考
    response = previs_client.post(
        "/api/v1/previs/scenes",
        json={"title": "独立思路场景", "scene": {"fps": 24, "nodes": [], "cameras": []}},
    )
    assert response.status_code == 200
    created = response.json()["data"]
    assert created["project_id"] == ""
    assert created["storyboard_content_id"] == ""
    assert created["panel_number"] is None
    assert created["revision"] == 1

    get_response = previs_client.get(f"/api/v1/previs/scenes/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["title"] == "独立思路场景"


def test_previs_standalone_scene_list_and_binding_filter(previs_client):
    standalone = previs_client.post("/api/v1/previs/scenes", json={"title": "独立场景"}).json()["data"]
    previs_client.post("/api/v1/previs/scenes", json=_create_payload())

    all_response = previs_client.get("/api/v1/previs/scenes")
    assert all_response.status_code == 200
    assert any(item["id"] == standalone["id"] for item in all_response.json()["data"])

    # 按项目过滤时不返回独立场景（独立场景 project_id 为空）
    filtered = previs_client.get("/api/v1/previs/scenes?project_id=project-1")
    assert all(item["project_id"] == "project-1" for item in filtered.json()["data"])


# ---------------------------------------------------------------------------
# 截图回流：Asset Hub 入库 + 分镜关联 + **服务端派生**溯源
# ---------------------------------------------------------------------------

#: 1x1 PNG（最小合法图片）。断言的是"内容被原样落盘"，不需要真实画面。
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
)


class _FakeCreateResult:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id


class _FakeAssetHubFacade:
    """记录 create_imported_file 的入参；`fail=True` 时模拟上传失败。"""

    fail = False
    last_call: dict = {}

    def __init__(self, session) -> None:
        self.session = session

    async def create_imported_file(self, **kwargs):
        type(self).last_call = kwargs
        if type(self).fail:
            raise RuntimeError("asset hub unavailable")
        return _FakeCreateResult("asset-captured-1")


class _FakeAsyncSession:
    """只实现端点用到的那三个成员：get / add / commit。"""

    def __init__(self, project, content) -> None:
        self._project = project
        self._content = content
        self.added: list = []
        self.committed = False

    async def get(self, model, ident):
        if model is CreativeProject:
            return self._project
        if model is ProjectContent:
            return self._content
        return None

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture()
def capture_env(previs_session_factory, monkeypatch, tmp_path):
    """把 Asset Hub、异步会话与截图目录都换成可控替身（不碰真实存储）。"""
    state = {"project": object(), "content": ProjectContent(project_id="project-1", content_type="storyboard"), "session": None}

    @contextlib.asynccontextmanager
    async def _session():
        session = _FakeAsyncSession(state["project"], state["content"])
        state["session"] = session
        yield session

    monkeypatch.setattr(previs_api, "get_async_session", _session)
    monkeypatch.setattr(previs_api, "AssetHubFacade", _FakeAssetHubFacade)
    monkeypatch.setattr(previs_api, "_capture_dir", lambda: tmp_path / "previs-captures")
    _FakeAssetHubFacade.fail = False
    _FakeAssetHubFacade.last_call = {}
    return state


def _capture(client, scene_id: str, *, filename="previs-capture.png", camera_id="cam-1", payload=PNG_1PX):
    return client.post(
        f"/api/v1/previs/scenes/{scene_id}/capture",
        files={"file": (filename, payload, "image/png")},
        data={"camera_id": camera_id, "frame": "0"},
    )


def test_previs_capture_rejects_scene_without_storyboard_panel(previs_client, capture_env):
    """独立场景没有分镜面板可关联：明确拒绝，而不是建一个悬空关联。"""
    standalone = previs_client.post(
        "/api/v1/previs/scenes",
        json={"title": "独立场景", "scene": {"nodes": [], "cameras": []}},
    ).json()["data"]

    response = _capture(previs_client, standalone["id"])
    assert response.status_code == 400
    assert "未绑定项目分镜面板" in response.json()["detail"]
    assert capture_env["session"] is None  # 未触碰 Asset Hub


def test_previs_capture_rejects_unknown_camera(previs_client, capture_env):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]

    response = _capture(previs_client, created["id"], camera_id="cam-does-not-exist")
    assert response.status_code == 400
    assert "不存在机位" in response.json()["detail"]


def test_previs_capture_rejects_unsupported_format(previs_client, capture_env):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]

    response = _capture(previs_client, created["id"], filename="notes.txt")
    assert response.status_code == 400
    assert "格式不受支持" in response.json()["detail"]


def test_previs_capture_creates_asset_and_link_with_server_derived_provenance(previs_client, capture_env):
    """溯源必须由服务端从场景派生，而不是采信客户端。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    # 先保存一次把 revision 推到 2 —— 若端点采信硬编码值，这里就会露馅
    saved = previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": created["title"], "scene": created["scene"]},
    )
    assert saved.json()["data"]["revision"] == 2

    response = _capture(previs_client, scene_id)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["asset_id"] == "asset-captured-1"
    assert data["linked"] is True
    assert data["link_error"] is None
    assert data["role"] == "storyboard_reference"
    assert data["content_id"] == "content-1"

    provenance = data["provenance"]
    assert provenance["source"] == "previs_capture"
    assert provenance["previs_scene_id"] == scene_id
    assert provenance["camera_id"] == "cam-1"
    assert provenance["scene_revision"] == 2              # 来自行上的 revision
    assert provenance["source_asset_ids"] == ["asset-1"]  # 来自场景节点的 assetId
    assert provenance["panel_number"] == 1

    # Asset Hub 收到的元数据与 lineage 都带同一份溯源
    call = _FakeAssetHubFacade.last_call
    assert call["asset_type"] == "image"
    assert call["source"] == "previs_capture"
    assert call["metadata"]["scene_revision"] == 2
    assert call["lineage"]["project_id"] == "project-1"
    # 文件确实落盘且内容与上传一致
    written = Path(call["file_path"])
    assert written.exists() and written.read_bytes() == PNG_1PX

    # 关联记录：role/relation/content 正确，metadata 是同一份溯源
    links = [item for item in capture_env["session"].added if isinstance(item, ProjectAssetLink)]
    assert len(links) == 1
    link = links[0]
    assert (link.role, link.relation) == ("storyboard_reference", "derived_from")
    assert link.project_id == "project-1"
    assert link.content_id == "content-1"
    assert json.loads(link.metadata_json)["previs_scene_id"] == scene_id
    assert capture_env["session"].committed is True


def test_previs_capture_reports_partial_failure_without_fake_success(previs_client, capture_env):
    """上传成功但关联失败：返回 linked=false + 可重试信息，且不留半成品关联。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    capture_env["project"] = None  # 项目不存在 → 关联阶段抛错（此时资产已入库）

    response = _capture(previs_client, created["id"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["asset_id"] == "asset-captured-1"  # 资产确实已入库
    assert data["linked"] is False
    assert data["link_error"]
    assert data["retry_hint"]
    assert "asset-captured-1" in data["retry_hint"]  # 重试需要它
    assert [item for item in capture_env["session"].added if isinstance(item, ProjectAssetLink)] == []


def test_previs_capture_upload_failure_creates_nothing(previs_client, capture_env):
    """上传失败：既不产生资产也不产生关联，直接报错。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    _FakeAssetHubFacade.fail = True

    response = _capture(previs_client, created["id"])
    assert response.status_code == 503
    assert "截图入库失败" in response.json()["detail"]
    assert capture_env["session"].added == []


def test_previs_capture_missing_scene_returns_404(previs_client, capture_env):
    response = _capture(previs_client, "no-such-scene")
    assert response.status_code == 404
