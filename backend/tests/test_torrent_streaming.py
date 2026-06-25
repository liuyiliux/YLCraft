from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api.v1.torrents import _range_file_response
from app.services.torrent.config import TorrentConfig
from app.services.torrent.models import TorrentFileInfo
from app.services.torrent.service import TorrentService


def _request(range_header: str | None = None) -> Request:
    headers = []
    if range_header:
        headers.append((b"range", range_header.encode("latin-1")))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


async def _response_body(response) -> bytes:
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    return body


@pytest.mark.asyncio
async def test_range_file_response_supports_suffix_ranges(tmp_path: Path):
    file_path = tmp_path / "movie.mp4"
    file_path.write_bytes(b"0123456789")

    response = _range_file_response(_request("bytes=-4"), file_path, "video/mp4")

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 6-9/10"
    assert response.headers["accept-ranges"] == "bytes"
    assert await _response_body(response) == b"6789"


def test_range_file_response_rejects_invalid_ranges(tmp_path: Path):
    file_path = tmp_path / "movie.mp4"
    file_path.write_bytes(b"0123456789")

    response = _range_file_response(_request("bytes=99-100"), file_path, "video/mp4")

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"
    assert response.headers["accept-ranges"] == "bytes"


@pytest.mark.asyncio
async def test_get_file_for_stream_uses_qbittorrent_incomplete_suffix(tmp_path: Path):
    root = tmp_path / "torrents"
    root.mkdir()
    incomplete = root / "movie.mp4.!qB"
    incomplete.write_bytes(b"partial")
    service = _torrent_service(root, [TorrentFileInfo(index=0, name="movie.mp4", size=100, progress=0.5, priority=1)])

    item, path = await service.get_file_for_stream(SimpleNamespace(save_path=str(root)), 0)

    assert item.name == "movie.mp4"
    assert path == incomplete.resolve()


@pytest.mark.asyncio
async def test_get_file_for_stream_rejects_paths_outside_download_dir(tmp_path: Path):
    root = tmp_path / "torrents"
    root.mkdir()
    service = _torrent_service(root, [TorrentFileInfo(index=0, name="../outside.mp4", size=100, progress=1, priority=1)])

    with pytest.raises(ValueError, match="outside torrent download directory"):
        await service.get_file_for_stream(SimpleNamespace(save_path=str(root)), 0)


def _torrent_service(root: Path, files: list[TorrentFileInfo]) -> TorrentService:
    service = object.__new__(TorrentService)
    service.config = TorrentConfig(
        engine="qbittorrent",
        qbittorrent_url="http://127.0.0.1:8080",
        qbittorrent_username="admin",
        qbittorrent_password="adminadmin",
        download_dir=root,
        max_active=3,
        max_upload_bytes=2 * 1024 * 1024,
    )

    async def list_files(_record):
        return files

    service.list_files = list_files
    return service
