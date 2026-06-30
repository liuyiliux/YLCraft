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


def test_assets_api_no_longer_serves_legacy_fallback_assets():
    with _assets_test_client(_FakeService()) as client:
        detail_response = client.get("/api/v1/assets/legacy-1")
        download_response = client.get("/api/v1/assets/legacy-1/download")

    assert detail_response.status_code == 404
    assert download_response.status_code == 404
