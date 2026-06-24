"""qBittorrent Web API adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import unquote

import httpx

from app.services.torrent.config import TorrentConfig
from app.services.torrent.engine import TorrentEngine
from app.services.torrent.models import TorrentFileInfo, TorrentStatus


class QBittorrentEngine(TorrentEngine):
    def __init__(self, config: TorrentConfig):
        self.config = config
        self._client = httpx.AsyncClient(base_url=config.qbittorrent_url, timeout=30.0)
        self._logged_in = False

    async def _login(self) -> None:
        if self._logged_in:
            return
        response = await self._client.post(
            "/api/v2/auth/login",
            data={"username": self.config.qbittorrent_username, "password": self.config.qbittorrent_password},
        )
        response.raise_for_status()
        if response.text.strip().lower() != "ok.":
            raise RuntimeError("qBittorrent login failed")
        self._logged_in = True

    async def add_magnet(self, magnet: str, save_path: Path, start_paused: bool = True) -> str:
        await self._login()
        response = await self._client.post(
            "/api/v2/torrents/add",
            data={
                "urls": magnet,
                "savepath": str(save_path),
                "paused": "true" if start_paused else "false",
            },
        )
        response.raise_for_status()
        if "Ok" not in response.text:
            raise RuntimeError(response.text or "qBittorrent rejected magnet")
        return _hash_from_magnet(magnet)

    async def add_torrent_file(self, torrent_file: Path, save_path: Path, start_paused: bool = True) -> str:
        await self._login()
        with torrent_file.open("rb") as f:
            response = await self._client.post(
                "/api/v2/torrents/add",
                data={"savepath": str(save_path), "paused": "true" if start_paused else "false"},
                files={"torrents": (torrent_file.name, f, "application/x-bittorrent")},
            )
        response.raise_for_status()
        if "Ok" not in response.text:
            raise RuntimeError(response.text or "qBittorrent rejected torrent file")
        return ""

    async def list_torrents(self) -> list[TorrentStatus]:
        await self._login()
        response = await self._client.get("/api/v2/torrents/info")
        response.raise_for_status()
        return [_status_from_qbit(item) for item in response.json()]

    async def list_files(self, torrent_hash: str) -> list[TorrentFileInfo]:
        await self._login()
        response = await self._client.get("/api/v2/torrents/files", params={"hash": torrent_hash})
        response.raise_for_status()
        return [
            TorrentFileInfo(
                index=int(item.get("index", index)),
                name=item.get("name") or "",
                size=int(item.get("size") or 0),
                progress=float(item.get("progress") or 0),
                priority=int(item.get("priority") or 0),
            )
            for index, item in enumerate(response.json())
        ]

    async def select_files(self, torrent_hash: str, file_indexes: list[int]) -> None:
        await self._login()
        files = await self.list_files(torrent_hash)
        selected = {int(i) for i in file_indexes}
        skip_ids = [str(f.index) for f in files if f.index not in selected]
        select_ids = [str(f.index) for f in files if f.index in selected]
        if skip_ids:
            await self._set_priority(torrent_hash, skip_ids, 0)
        if select_ids:
            await self._set_priority(torrent_hash, select_ids, 1)

    async def _set_priority(self, torrent_hash: str, ids: list[str], priority: int) -> None:
        response = await self._client.post(
            "/api/v2/torrents/filePrio",
            data={"hash": torrent_hash, "id": "|".join(ids), "priority": str(priority)},
        )
        response.raise_for_status()

    async def pause(self, torrent_hash: str) -> None:
        await self._login()
        response = await self._client.post("/api/v2/torrents/pause", data={"hashes": torrent_hash})
        response.raise_for_status()

    async def resume(self, torrent_hash: str) -> None:
        await self._login()
        response = await self._client.post("/api/v2/torrents/resume", data={"hashes": torrent_hash})
        response.raise_for_status()

    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None:
        await self._login()
        response = await self._client.post(
            "/api/v2/torrents/delete",
            data={"hashes": torrent_hash, "deleteFiles": "true" if delete_files else "false"},
        )
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()


def _hash_from_magnet(magnet: str) -> str:
    marker = "btih:"
    if marker not in magnet.lower():
        return ""
    start = magnet.lower().index(marker) + len(marker)
    value = magnet[start:].split("&", 1)[0]
    return unquote(value).lower()


def _status_from_qbit(item: dict) -> TorrentStatus:
    return TorrentStatus(
        torrent_hash=(item.get("hash") or "").lower(),
        name=item.get("name") or "",
        state=item.get("state") or "",
        progress=float(item.get("progress") or 0),
        download_speed=int(item.get("dlspeed") or 0),
        upload_speed=int(item.get("upspeed") or 0),
        downloaded_bytes=int(item.get("downloaded") or 0),
        total_size=int(item.get("size") or 0),
        save_path=item.get("save_path") or "",
        error=item.get("error") or "",
    )

