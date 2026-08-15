from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from app.api.v1 import assets as assets_api
from app.db.models.asset_hub import AssetNode, AssetType


class _FakeService:
    def __init__(self, session=None, legacy_asset=None):
        self.session = session or SimpleNamespace()
        self.legacy_asset = legacy_asset

    async def get_by_id(self, asset_id: str):
        if self.legacy_asset and self.legacy_asset.id == asset_id:
            return self.legacy_asset
        return None

    async def list_assets(self, **_kwargs):
        return ([self.legacy_asset] if self.legacy_asset else []), 1 if self.legacy_asset else 0


def _assets_test_client(service):
    app = FastAPI()
    app.include_router(assets_api.router, prefix="/api/v1/assets")

    async def override_asset_service():
        return service

    app.dependency_overrides[assets_api.get_asset_session] = override_asset_service
    return TestClient(app)


@pytest.mark.asyncio
async def test_asset_hub_card_supports_downloaded_text_assets(monkeypatch, tmp_path):
    text_file = tmp_path / "novel.txt"
    text_file.write_text("content", encoding="utf-8")
    now = datetime.utcnow()
    node = SimpleNamespace(
        id="hub-node-1",
        name="测试小说",
        asset_type=AssetType.TEXT,
        metadata_json={
            "source": "novel_download",
            "source_url": "https://example.test/book",
            "author": "作者",
        },
        tags_json=["novel"],
        thumbnail_url="",
        created_at=now,
        updated_at=now,
    )
    version = SimpleNamespace(
        id="hub-version-1",
        version_number=1,
        prompt_used="",
        model_used="",
        params_json={},
        lineage_json={"source": "novel_download"},
        created_at=now,
    )
    rep = SimpleNamespace(
        id="hub-rep-1",
        file_path=str(text_file),
        mime_type="text/plain",
        file_size=text_file.stat().st_size,
        width=None,
        height=None,
        duration=None,
    )

    class FakeVersionService:
        def __init__(self, _session):
            pass

        async def get_latest_version(self, _node_id):
            return version

    class FakeRepresentationService:
        def __init__(self, _session):
            pass

        async def get_primary(self, _version_id):
            return rep

    monkeypatch.setattr(assets_api, "AssetVersionService", FakeVersionService)
    monkeypatch.setattr(assets_api, "AssetRepresentationService", FakeRepresentationService)

    card = await assets_api._asset_hub_card(_FakeService(), node, include_metadata=True)

    assert card["type"] == "text"
    assert card["source_type"] == "novel_download"
    assert card["source_url"] == "https://example.test/book"
    assert card["author"] == "作者"
    assert card["file_path"] == str(text_file)


@pytest.mark.asyncio
async def test_soft_delete_asset_hub_node_marks_legacy_asset_deleted(monkeypatch):
    node = SimpleNamespace(
        id="hub-node-1",
        metadata_json={"legacy_asset_id": "legacy-1"},
        updated_at=datetime.utcnow(),
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False

        async def get(self, model, asset_id):
            if model is AssetNode and asset_id == node.id:
                return node
            return None

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.committed = True

    async def fake_primary(_service, asset_id):
        assert asset_id == node.id
        return node, SimpleNamespace(id="version"), SimpleNamespace(file_path="")

    session = FakeSession()
    monkeypatch.setattr(assets_api, "_get_asset_hub_primary", fake_primary)

    deleted = await assets_api._soft_delete_asset_hub_node(
        session,
        node.id,
        mode="soft",
    )

    assert deleted is True
    assert session.committed is True
    assert node.metadata_json["status"] == "DELETED"
    assert node.metadata_json["deleted_at"]


def test_assets_api_serves_asset_hub_list_detail_thumbnail_and_download(monkeypatch, tmp_path):
    hub_file = tmp_path / "hub-image.png"
    hub_file.write_bytes(b"png-bytes")
    hub_card = {
        "id": "hub-node-1",
        "type": "image",
        "title": "Hub Image",
        "platform": "asset_hub",
        "author": "Asset Hub",
        "status": "READY",
        "source_type": "ai_generated",
        "source_url": "/api/v1/assets/download?path=hub-image.png",
        "cover_url": str(hub_file),
        "thumbnail_url": str(hub_file),
        "tags": ["ai-generated"],
        "created_at": "2026-06-30 10:00:00",
        "updated_at": "2026-06-30 10:00:00",
        "downloaded_at": "2026-06-30 10:00:00",
        "duration": 0,
        "width": 1,
        "height": 1,
        "file_size": len(b"png-bytes"),
        "resolution": "1x1",
        "metadata": {"asset_hub": True},
    }
    rep = SimpleNamespace(file_path=str(hub_file), mime_type="image/png")

    async def fake_list_hub_cards(*_args, **_kwargs):
        return [hub_card]

    async def fake_hub_card(_service, asset_id, include_metadata=True):
        return hub_card if asset_id == "hub-node-1" else None

    async def fake_hub_primary(_service, asset_id):
        if asset_id == "hub-node-1":
            return SimpleNamespace(thumbnail_url=str(hub_file)), SimpleNamespace(id="version"), rep
        return None

    async def fake_fetch_image(image_source: str, platform: str = ""):
        assert image_source == str(hub_file)
        return Response(content=b"thumb", media_type="image/png")

    monkeypatch.setattr(assets_api, "_list_asset_hub_cards", fake_list_hub_cards)
    monkeypatch.setattr(assets_api, "_get_asset_hub_card", fake_hub_card)
    monkeypatch.setattr(assets_api, "_get_asset_hub_primary", fake_hub_primary)
    monkeypatch.setattr(assets_api, "_resolve_asset_file_path", lambda value: Path(value))
    monkeypatch.setattr(assets_api, "_fetch_image", fake_fetch_image)

    with _assets_test_client(_FakeService()) as client:
        list_response = client.get("/api/v1/assets")
        detail_response = client.get("/api/v1/assets/hub-node-1")
        thumbnail_response = client.get("/api/v1/assets/hub-node-1/thumbnail")
        download_response = client.get("/api/v1/assets/hub-node-1/download")

    assert list_response.status_code == 200
    assert list_response.json()["data"][0]["id"] == "hub-node-1"
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["metadata"]["asset_hub"] is True
    assert thumbnail_response.status_code == 200
    assert thumbnail_response.content == b"thumb"
    assert download_response.status_code == 200
    assert download_response.content == b"png-bytes"


def test_list_model_sidecar_files_lists_obj_mtl_and_texture(tmp_path):
    (tmp_path / "model.obj").write_bytes(b"obj")
    (tmp_path / "material.mtl").write_bytes(b"mtl")
    (tmp_path / "tex.png").write_bytes(b"png")

    files = assets_api._list_model_sidecar_files(str(tmp_path / "model.obj"), "asset-1")
    assert {f["name"] for f in files} == {"model.obj", "material.mtl", "tex.png"}
    assert {f["url"] for f in files} == {
        "/api/v1/assets/asset-1/files/model.obj",
        "/api/v1/assets/asset-1/files/material.mtl",
        "/api/v1/assets/asset-1/files/tex.png",
    }


def test_list_model_sidecar_files_empty_for_single_file(tmp_path):
    (tmp_path / "model.glb").write_bytes(b"glb")
    assert assets_api._list_model_sidecar_files(str(tmp_path / "model.glb"), "asset-1") == []


def test_assets_api_serves_model_sidecar_files(monkeypatch, tmp_path):
    obj = tmp_path / "model.obj"
    obj.write_bytes(b"obj-bytes")
    (tmp_path / "material.mtl").write_bytes(b"mtl-bytes")
    rep = SimpleNamespace(file_path=str(obj), mime_type="text/plain")

    async def fake_hub_primary(_service, asset_id):
        if asset_id == "hub-model-1":
            return SimpleNamespace(), SimpleNamespace(id="version"), rep
        return None

    monkeypatch.setattr(assets_api, "_get_asset_hub_primary", fake_hub_primary)
    monkeypatch.setattr(assets_api, "_resolve_asset_file_path", lambda value: Path(value))

    with _assets_test_client(_FakeService()) as client:
        ok = client.get("/api/v1/assets/hub-model-1/files/material.mtl")
        missing = client.get("/api/v1/assets/hub-model-1/files/nope.mtl")

    assert ok.status_code == 200
    assert ok.content == b"mtl-bytes"
    assert missing.status_code == 404


def test_assets_api_upload_model3d_zip(monkeypatch, tmp_path):
    import io
    import zipfile

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as archive:
        archive.writestr("model.obj", b"obj-bytes")
        archive.writestr("material.mtl", b"mtl-bytes")
        archive.writestr("tex.png", b"png-bytes")
    zip_bytes = zip_buf.getvalue()

    captured: dict = {}

    class FakeFacade:
        def __init__(self, session):
            self.session = session

        async def create_imported_file(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(node_id="uploaded-model-1")

    monkeypatch.setattr(assets_api, "AssetHubFacade", FakeFacade)
    monkeypatch.setattr(assets_api, "_model3d_upload_dir", lambda: tmp_path)

    with _assets_test_client(_FakeService()) as client:
        resp = client.post(
            "/api/v1/assets/upload-model3d",
            files={"file": ("model.zip", zip_bytes, "application/zip")},
            data={"title": "Test Model"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["asset_id"] == "uploaded-model-1"
    assert captured["file_path"].endswith("model.obj")
    assert captured["asset_type"] == AssetType.THREE_D_MODEL
    assert captured["title"] == "Test Model"


def test_assets_api_upload_model3d_rejects_missing_model(monkeypatch, tmp_path):
    import io
    import zipfile

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as archive:
        archive.writestr("notes.txt", b"no model here")
    zip_bytes = zip_buf.getvalue()

    monkeypatch.setattr(assets_api, "_model3d_upload_dir", lambda: tmp_path)

    with _assets_test_client(_FakeService()) as client:
        resp = client.post(
            "/api/v1/assets/upload-model3d",
            files={"file": ("bad.zip", zip_bytes, "application/zip")},
        )

    assert resp.status_code == 400


def test_assets_api_upload_generic_image(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeFacade:
        def __init__(self, session):
            self.session = session

        async def create_imported_file(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(node_id="uploaded-img-1")

    monkeypatch.setattr(assets_api, "AssetHubFacade", FakeFacade)
    monkeypatch.setattr(assets_api, "_upload_assets_dir", lambda: tmp_path)

    with _assets_test_client(_FakeService()) as client:
        resp = client.post(
            "/api/v1/assets/upload",
            files={"file": ("photo.png", b"png-bytes", "image/png")},
            data={"title": "My Photo"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["asset_id"] == "uploaded-img-1"
    assert captured["asset_type"] == AssetType.IMAGE
    assert captured["title"] == "My Photo"


def test_assets_api_upload_video_sets_first_frame_thumbnail(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeFacade:
        def __init__(self, session):
            self.session = session

        async def create_imported_file(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(node_id="uploaded-vid-1")

    monkeypatch.setattr(assets_api, "AssetHubFacade", FakeFacade)
    monkeypatch.setattr(assets_api, "_upload_assets_dir", lambda: tmp_path)

    async def fake_thumb(video_path):
        return str(tmp_path / "thumb.jpg")

    monkeypatch.setattr(assets_api, "_video_thumbnail_file", fake_thumb)

    with _assets_test_client(_FakeService()) as client:
        resp = client.post(
            "/api/v1/assets/upload",
            files={"file": ("clip.mp4", b"video-bytes", "video/mp4")},
        )

    assert resp.status_code == 200
    assert captured["asset_type"] == AssetType.VIDEO
    assert captured["thumbnail_url"] == str(tmp_path / "thumb.jpg")


def test_delete_asset_file_if_exists_skips_missing_and_deletes_existing(monkeypatch, tmp_path):
    monkeypatch.setattr(assets_api, "_asset_file_allowed_roots", lambda: [tmp_path])

    # 文件已不存在时不抛错（回归：之前会 404「文件不存在」导致删不掉）
    missing = tmp_path / "already-gone.glb"
    assets_api._delete_asset_file_if_exists(str(missing))

    # 文件存在时正常删除
    existing = tmp_path / "model.glb"
    existing.write_bytes(b"glb")
    assets_api._delete_asset_file_if_exists(str(existing))
    assert not existing.exists()


def test_assets_api_no_longer_serves_legacy_fallback_assets():
    with _assets_test_client(_FakeService()) as client:
        detail_response = client.get("/api/v1/assets/legacy-1")
        download_response = client.get("/api/v1/assets/legacy-1/download")

    assert detail_response.status_code == 404
    assert download_response.status_code == 404


@pytest.mark.asyncio
async def test_project_asset_context_reads_all_asset_hub_metadata_layers():
    card = {
        "metadata": {
            "node_metadata": {"project_id": "project-node", "content_type": "novel_body"},
            "lineage": {"project_title": "不应覆盖节点项目", "role": "text"},
            "ai_params": {"chapter_number": 3, "content_version": 2},
        }
    }

    assert assets_api._project_asset_context(card) == {
        "project_id": "project-node",
        "project_title": "不应覆盖节点项目",
        "asset_role": "text",
        "source_stage": "novel_body",
        "content_id": "",
        "content_version": 2,
        "chapter_number": 3,
    }


def test_assets_api_passes_project_filters_to_asset_hub(monkeypatch):
    captured = {}

    async def fake_list_hub_cards(*_args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(assets_api, "_list_asset_hub_cards", fake_list_hub_cards)

    with _assets_test_client(_FakeService()) as client:
        response = client.get(
            "/api/v1/assets?project_id=project-1&asset_role=text&source_stage=novel_body"
        )

    assert response.status_code == 200
    assert captured["project_id"] == "project-1"
    assert captured["asset_role"] == "text"
    assert captured["source_stage"] == "novel_body"


def test_project_text_asset_defaults_to_text_role_when_link_is_not_loaded():
    context = assets_api._project_asset_context({
        "type": "text",
        "metadata": {
            "node_metadata": {"project_id": "project-1", "content_type": "script"},
        },
    })

    assert context["asset_role"] == "text"
    assert context["source_stage"] == "script"
