from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1 import assets as assets_api
from app.api.v1 import torrents as torrents_api
from app.db.models.asset import Asset
from app.db.models.torrent import TorrentDownload
from app.services.torrent.config import TorrentConfig
from app.services.torrent.models import TorrentFileInfo
from app.services.torrent.service import TorrentService


MAGNET = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=demo"


@pytest_asyncio.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'torrent-test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Asset.__table__.create)
        await conn.run_sync(TorrentDownload.__table__.create)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_import_assets_creates_file_level_torrent_assets(sqlite_session: AsyncSession, tmp_path: Path):
    root = tmp_path / "downloads"
    root.mkdir()
    (root / "episode-1.mp4").write_bytes(b"video-one")
    (root / "episode-2.mp4").write_bytes(b"video-two")
    record = TorrentDownload(
        engine="libtorrent",
        torrent_hash="0123456789abcdef0123456789abcdef01234567",
        name="Demo Torrent",
        source="magnet",
        source_uri=MAGNET,
        save_path=str(root),
        selected_files_json="[0, 1]",
        status="done",
    )
    sqlite_session.add(record)
    await sqlite_session.flush()
    await sqlite_session.refresh(record)

    service = _torrent_service(
        sqlite_session,
        root,
        [
            TorrentFileInfo(index=0, name="episode-1.mp4", size=9, progress=1, priority=1),
            TorrentFileInfo(index=1, name="episode-2.mp4", size=9, progress=1, priority=1),
        ],
    )

    imported = await service.import_assets(record)

    assert len(imported) == 2
    assert {asset.title for asset in imported} == {"episode-1", "episode-2"}
    assert {asset.source_url for asset in imported} == {
        "torrent:0123456789abcdef0123456789abcdef01234567:0",
        "torrent:0123456789abcdef0123456789abcdef01234567:1",
    }
    assert all(asset.platform == "torrent" for asset in imported)
    assert all(asset.source_type == "torrent" for asset in imported)
    assert all(asset.status == "READY" for asset in imported)
    assert sorted(json.loads(record.asset_ids_json)) == sorted(asset.id for asset in imported)

    result = await sqlite_session.execute(select(Asset).where(Asset.platform == "torrent"))
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_select_files_delegates_to_engine_and_resumes(tmp_path: Path):
    engine = _FakeEngine()
    service = object.__new__(TorrentService)
    service.session = _FakeFlushSession()
    service.config = _torrent_config(tmp_path)
    service.engine = engine
    record = TorrentDownload(torrent_hash="hash-demo", status="metadata")

    selected = await service.select_files(record, [2, 0, 2], start=True)

    assert engine.selected == [("hash-demo", [2, 0, 2])]
    assert engine.resumed == ["hash-demo"]
    assert json.loads(selected.selected_files_json) == [0, 2]
    assert selected.status == "downloading"


def test_torrent_api_lifecycle_and_file_stream(tmp_path: Path):
    service = _FakeTorrentService(tmp_path)
    app = FastAPI()
    app.include_router(torrents_api.router, prefix="/api/v1/torrents")

    async def override_torrent_service():
        return service

    app.dependency_overrides[torrents_api.get_torrent_service] = override_torrent_service

    with TestClient(app) as client:
        add_response = client.post("/api/v1/torrents/magnet", json={"magnet": MAGNET, "start_paused": True})
        assert add_response.status_code == 200
        task = add_response.json()["data"]
        download_id = task["id"]
        assert task["torrent_hash"] == service.record.torrent_hash
        assert task["status"] == "metadata"

        list_response = client.get("/api/v1/torrents")
        assert list_response.status_code == 200
        assert list_response.json()["data"][0]["id"] == download_id

        files_response = client.get(f"/api/v1/torrents/{download_id}/files")
        assert files_response.status_code == 200
        assert files_response.json()["data"][0]["is_video"] is True

        select_response = client.post(
            f"/api/v1/torrents/{download_id}/select-files",
            json={"file_indexes": [0], "start": True},
        )
        assert select_response.status_code == 200
        assert select_response.json()["data"]["selected_files"] == [0]
        assert select_response.json()["data"]["status"] == "downloading"

        pause_response = client.post(f"/api/v1/torrents/{download_id}/pause")
        assert pause_response.status_code == 200
        assert pause_response.json()["data"]["status"] == "paused"

        resume_response = client.post(f"/api/v1/torrents/{download_id}/resume")
        assert resume_response.status_code == 200
        assert resume_response.json()["data"]["status"] == "downloading"

        stream_response = client.get(
            f"/api/v1/torrents/{download_id}/files/0/stream",
            headers={"Range": "bytes=2-5"},
        )
        assert stream_response.status_code == 206
        assert stream_response.headers["content-range"] == "bytes 2-5/10"
        assert stream_response.content == b"2345"

        import_response = client.post(f"/api/v1/torrents/{download_id}/import-assets")
        assert import_response.status_code == 200
        assert import_response.json()["data"] == [{"id": "asset-demo", "title": "movie"}]

        delete_response = client.delete(f"/api/v1/torrents/{download_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["data"] == {"deleted": True}
        assert client.get(f"/api/v1/torrents/{download_id}").status_code == 404


def test_torrent_upload_endpoint_accepts_torrent_file(tmp_path: Path):
    service = _FakeTorrentService(tmp_path)
    app = FastAPI()
    app.include_router(torrents_api.router, prefix="/api/v1/torrents")

    async def override_torrent_service():
        return service

    app.dependency_overrides[torrents_api.get_torrent_service] = override_torrent_service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/torrents/upload",
            files={"file": ("demo.torrent", b"d4:infod6:lengthi10e4:name9:movie.mp4ee", "application/x-bittorrent")},
        )

    assert response.status_code == 200
    assert response.json()["data"]["source"] == "torrent_file"
    assert service.uploaded_name == "demo.torrent"


def test_imported_torrent_asset_stream_supports_range(tmp_path: Path):
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"0123456789")
    asset = Asset(
        id="asset-demo",
        type="VIDEO",
        title="movie",
        platform="torrent",
        source_type="torrent",
        source_url="torrent:hash:0",
        file_path=str(video),
        file_size=10,
        mime_type="video/mp4",
        status="READY",
    )
    app = FastAPI()
    app.include_router(assets_api.router, prefix="/api/v1/assets")

    async def override_asset_service():
        return _FakeAssetService(asset)

    app.dependency_overrides[assets_api.get_asset_service] = override_asset_service

    with TestClient(app) as client:
        response = client.get("/api/v1/assets/asset-demo/stream", headers={"Range": "bytes=3-6"})

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 3-6/10"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == b"3456"


def _torrent_config(root: Path) -> TorrentConfig:
    return TorrentConfig(
        engine="libtorrent",
        qbittorrent_url="http://127.0.0.1:8080",
        qbittorrent_username="admin",
        qbittorrent_password="adminadmin",
        download_dir=root,
        max_active=3,
        max_upload_bytes=2 * 1024 * 1024,
        listen_interfaces="0.0.0.0:6883-6999,[::]:6883-6999",
        metadata_cache_urls=[],
        metadata_cache_timeout=5,
        metadata_cache_max_bytes=4 * 1024 * 1024,
    )


def _torrent_service(session: AsyncSession, root: Path, files: list[TorrentFileInfo]) -> TorrentService:
    service = object.__new__(TorrentService)
    service.session = session
    service.config = _torrent_config(root)
    service.engine = None

    async def list_files(_record):
        return files

    service.list_files = list_files
    return service


class _FakeTorrentService:
    def __init__(self, root: Path):
        self.root = root
        self.video = root / "movie.mp4"
        self.video.write_bytes(b"0123456789")
        self.record = TorrentDownload(
            engine="libtorrent",
            torrent_hash="0123456789abcdef0123456789abcdef01234567",
            name="demo",
            source="magnet",
            source_uri=MAGNET,
            save_path=str(root),
            status="metadata",
        )
        self.files = [TorrentFileInfo(index=0, name="movie.mp4", size=10, progress=1, priority=1)]
        self.uploaded_name = ""

    async def list_records(self):
        return [] if self.record.status == "deleted" else [self.record]

    async def add_magnet(self, magnet: str, start_paused: bool = True):
        self.record.source_uri = magnet
        self.record.status = "metadata"
        return self.record

    async def add_torrent_file(self, _torrent_path: Path, original_name: str, start_paused: bool = True):
        self.uploaded_name = original_name
        self.record.name = Path(original_name).stem
        self.record.source = "torrent_file"
        self.record.source_uri = str(_torrent_path)
        self.record.status = "metadata"
        return self.record

    async def get_record(self, download_id: str):
        if self.record.status == "deleted" or download_id != self.record.id:
            return None
        return self.record

    async def list_files(self, _record):
        return self.files

    async def select_files(self, record, file_indexes: list[int], start: bool = True):
        record.selected_files_json = json.dumps(sorted({int(index) for index in file_indexes}))
        if start:
            record.status = "downloading"
        return record

    async def pause(self, record):
        record.status = "paused"
        return record

    async def resume(self, record):
        record.status = "downloading"
        return record

    async def import_assets(self, _record):
        return [Asset(id="asset-demo", title="movie", type="VIDEO", status="READY")]

    async def get_file_for_stream(self, _record, file_index: int):
        return self.files[file_index], self.video

    async def delete(self, record, delete_files: bool = False):
        record.status = "deleted"


class _FakeAssetService:
    def __init__(self, asset: Asset):
        self.asset = asset

    async def get_by_id(self, asset_id: str):
        return self.asset if asset_id == self.asset.id else None


class _FakeFlushSession:
    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


class _FakeEngine:
    def __init__(self):
        self.selected: list[tuple[str, list[int]]] = []
        self.resumed: list[str] = []

    async def select_files(self, torrent_hash: str, file_indexes: list[int]):
        self.selected.append((torrent_hash, file_indexes))

    async def resume(self, torrent_hash: str):
        self.resumed.append(torrent_hash)
