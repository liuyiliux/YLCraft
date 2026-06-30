from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1 import assets as assets_api
from app.api.v1 import torrents as torrents_api
from app.db.models.torrent import TorrentDownload
from app.services.torrent.config import TorrentConfig
from app.services.torrent.models import TorrentFileInfo, TorrentHealth, TorrentStatus
from app.services.torrent.service import TorrentService
import app.services.torrent.service as torrent_service_module


MAGNET = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=demo"


@pytest_asyncio.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'torrent-test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(TorrentDownload.__table__.create)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_import_assets_creates_file_level_torrent_assets(sqlite_session: AsyncSession, tmp_path: Path, monkeypatch):
    _FakeAssetHubFacade.created = []
    monkeypatch.setattr(torrent_service_module, "AssetHubFacade", _FakeAssetHubFacade)
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
    assert {item["source_url"] for item in _FakeAssetHubFacade.created} == {
        "torrent:0123456789abcdef0123456789abcdef01234567:0",
        "torrent:0123456789abcdef0123456789abcdef01234567:1",
    }
    assert all(item["source"] == "torrent" for item in _FakeAssetHubFacade.created)
    assert all(item["metadata"]["platform"] == "torrent" for item in _FakeAssetHubFacade.created)
    assert sorted(json.loads(record.asset_ids_json)) == sorted(asset.id for asset in imported)

    assert _FakeAssetHubFacade.created


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


@pytest.mark.asyncio
async def test_prioritize_streaming_delegates_to_engine(tmp_path: Path):
    engine = _FakeEngine()
    service = object.__new__(TorrentService)
    service.session = _FakeFlushSession()
    service.config = _torrent_config(tmp_path)
    service.engine = engine
    record = TorrentDownload(torrent_hash="hash-demo", status="metadata")

    result = await service.prioritize_streaming(record, 1)

    assert engine.prioritized == [("hash-demo", 1)]
    assert result.status == "downloading"


@pytest.mark.asyncio
async def test_boost_trackers_delegates_to_engine(tmp_path: Path):
    engine = _FakeEngine()
    service = object.__new__(TorrentService)
    service.session = _FakeFlushSession()
    service.config = _torrent_config(tmp_path)
    service.engine = engine
    record = TorrentDownload(torrent_hash="hash-demo", status="metadata")

    result = await service.boost_trackers(record)

    assert engine.boosted == ["hash-demo"]
    assert "公共 tracker" in result.error_message


@pytest.mark.asyncio
async def test_torrent_health_explains_stalled_local_preview(tmp_path: Path):
    engine = _FakeEngine()
    service = object.__new__(TorrentService)
    service.session = _FakeFlushSession()
    service.config = _torrent_config(tmp_path)
    service.engine = engine
    record = TorrentDownload(
        torrent_hash="hash-demo",
        status="downloading",
        selected_files_json="[0]",
        save_path=str(tmp_path),
    )

    health = await service.get_health(record, file_index=0)

    assert health.target_file_name == "movie.mp4"
    assert health.ready_to_stream is False
    assert "还没有连到可下载的 peer" in health.reason
    assert any("YLCraft 本地模式" in hint for hint in health.hints)


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

        health_response = client.get(f"/api/v1/torrents/{download_id}/health?file_index=0")
        assert health_response.status_code == 200
        assert health_response.json()["data"]["ready_to_stream"] is True
        assert health_response.json()["data"]["target_file_name"] == "movie.mp4"

        select_response = client.post(
            f"/api/v1/torrents/{download_id}/select-files",
            json={"file_indexes": [0], "start": True},
        )
        assert select_response.status_code == 200
        assert select_response.json()["data"]["selected_files"] == [0]
        assert select_response.json()["data"]["status"] == "downloading"

        prioritize_response = client.post(f"/api/v1/torrents/{download_id}/files/0/prioritize-streaming")
        assert prioritize_response.status_code == 200
        assert service.prioritized == [0]

        boost_response = client.post(f"/api/v1/torrents/{download_id}/boost-trackers")
        assert boost_response.status_code == 200
        assert service.boosted == [download_id]

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
    storage_dir = Path(__file__).resolve().parents[1] / "storage" / "test_assets"
    storage_dir.mkdir(parents=True, exist_ok=True)
    video = storage_dir / "torrent-stream-range.mp4"
    video.write_bytes(b"0123456789")
    app = FastAPI()
    app.include_router(assets_api.router, prefix="/api/v1/assets")

    async def override_asset_session():
        return SimpleNamespace()

    async def fake_hub_primary(_session, asset_id):
        if asset_id != "asset-demo":
            return None
        return (
            SimpleNamespace(id="asset-demo", asset_type="video", metadata_json={}),
            SimpleNamespace(id="version-demo", params_json={}, lineage_json={}),
            SimpleNamespace(file_path=str(video), mime_type="video/mp4"),
        )

    app.dependency_overrides[assets_api.get_asset_session] = override_asset_session
    original_primary = assets_api._get_asset_hub_primary
    assets_api._get_asset_hub_primary = fake_hub_primary

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/assets/asset-demo/stream", headers={"Range": "bytes=3-6"})
    finally:
        assets_api._get_asset_hub_primary = original_primary
        video.unlink(missing_ok=True)

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
        self.prioritized: list[int] = []
        self.boosted: list[str] = []

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

    async def prioritize_streaming(self, record, file_index: int):
        self.prioritized.append(int(file_index))
        record.status = "downloading"
        return record

    async def boost_trackers(self, record):
        self.boosted.append(record.id)
        record.error_message = "已补充公共 tracker 并重新公告，正在等待 peer 响应"
        return record

    async def get_health(self, _record, file_index: int | None = None):
        target = self.files[0]
        return TorrentHealth(
            torrent_hash=self.record.torrent_hash,
            state=self.record.status,
            normalized_status=self.record.status,
            has_metadata=True,
            peers=1,
            seeds=1,
            connections=1,
            selected_file_count=1,
            selected_video_count=1,
            target_file_index=target.index if file_index is not None else None,
            target_file_name=target.name,
            target_file_size=target.size,
            target_file_progress=target.progress,
            target_file_available=True,
            ready_to_stream=True,
            reason="本机已经拿到当前视频的可读取片段，可以尝试在线播放。",
        )

    async def pause(self, record):
        record.status = "paused"
        return record

    async def resume(self, record):
        record.status = "downloading"
        return record

    async def import_assets(self, _record):
        return [SimpleNamespace(id="asset-demo", title="movie", type="VIDEO", status="READY")]

    async def get_file_for_stream(self, _record, file_index: int):
        return self.files[file_index], self.video

    async def delete(self, record, delete_files: bool = False):
        record.status = "deleted"


class _FakeAssetHubFacade:
    created = []

    def __init__(self, _session):
        pass

    async def create_imported_file(self, **kwargs):
        self.created.append(kwargs)
        node_id = f"hub-{len(self.created)}"
        return type(
            "AssetHubResult",
            (),
            {
                "node_id": node_id,
                "version_id": f"version-{node_id}",
                "representation_id": f"rep-{node_id}",
            },
        )()


class _FakeFlushSession:
    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


class _FakeEngine:
    def __init__(self):
        self.selected: list[tuple[str, list[int]]] = []
        self.resumed: list[str] = []
        self.prioritized: list[tuple[str, int]] = []
        self.boosted: list[str] = []
        self.files = [TorrentFileInfo(index=0, name="movie.mp4", size=100, progress=0, priority=1)]

    async def select_files(self, torrent_hash: str, file_indexes: list[int]):
        self.selected.append((torrent_hash, file_indexes))

    async def resume(self, torrent_hash: str):
        self.resumed.append(torrent_hash)

    async def prioritize_streaming(self, torrent_hash: str, file_index: int):
        self.prioritized.append((torrent_hash, int(file_index)))

    async def boost_trackers(self, torrent_hash: str):
        self.boosted.append(torrent_hash)

    async def list_torrents(self):
        return [TorrentStatus(torrent_hash="hash-demo", state="downloading")]

    async def list_files(self, _torrent_hash: str):
        return self.files

    async def get_health(self, torrent_hash: str):
        return TorrentHealth(
            torrent_hash=torrent_hash,
            state="downloading",
            normalized_status="downloading",
            has_metadata=True,
            download_speed=0,
            peers=0,
            seeds=0,
            connections=0,
        )
