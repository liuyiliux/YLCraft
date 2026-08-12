"""qBittorrent Web API adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import unquote

import httpx

from app.services.torrent.config import TorrentConfig
from app.services.torrent.engine import TorrentEngine
from app.services.torrent.models import PUBLIC_TRACKERS, TorrentFileInfo, TorrentHealth, TorrentStatus


class QBittorrentEngine(TorrentEngine):
    def __init__(self, config: TorrentConfig):
        self.config = config
        self._client = httpx.AsyncClient(base_url=config.qbittorrent_url, timeout=30.0)
        self._logged_in = False

    async def _login(self) -> None:
        if self._logged_in:
            return
        if not self.config.qbittorrent_password:
            raise RuntimeError(
                "qBittorrent credentials are not configured. "
                "Set QBITTORRENT_USERNAME and QBITTORRENT_PASSWORD in backend/.env."
            )
        login_path = "/api/v2/auth/login"
        try:
            response = await self._client.post(
                login_path,
                data={"username": self.config.qbittorrent_username, "password": self.config.qbittorrent_password},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise RuntimeError(
                    "qBittorrent Web API not found. "
                    f"Current QBITTORRENT_URL is {self.config.qbittorrent_url}; "
                    "make sure qBittorrent Web UI is enabled and this URL points to its Web UI port."
                ) from exc
            raise
        except httpx.RequestError as exc:
            raise RuntimeError(
                "Cannot connect to qBittorrent Web UI. "
                f"Current QBITTORRENT_URL is {self.config.qbittorrent_url}; "
                "make sure qBittorrent is running and Web UI is enabled."
            ) from exc
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

    async def prioritize_streaming(self, torrent_hash: str, file_index: int) -> None:
        await self._login()
        await self._set_priority(torrent_hash, [str(int(file_index))], 7)
        await self.resume(torrent_hash)

    async def get_health(self, torrent_hash: str) -> TorrentHealth | None:
        await self._login()
        response = await self._client.get("/api/v2/torrents/info", params={"hashes": torrent_hash})
        response.raise_for_status()
        items = response.json()
        item = items[0] if items else None
        if not item:
            return TorrentHealth(
                torrent_hash=(torrent_hash or "").lower(),
                reason="任务尚未出现在 qBittorrent Web API 中，可能需要刷新任务列表。",
            )
        trackers, tracker_failures = await self._tracker_stats(torrent_hash)
        state = item.get("state") or ""
        return TorrentHealth(
            torrent_hash=(item.get("hash") or torrent_hash or "").lower(),
            state=state,
            normalized_status=_status_from_qbit(item).normalized_status,
            has_metadata=state.lower() not in {"metadl", "checkingresume"} and int(item.get("size") or 0) > 0,
            progress=float(item.get("progress") or 0),
            download_speed=int(item.get("dlspeed") or 0),
            upload_speed=int(item.get("upspeed") or 0),
            peers=int(item.get("num_leechs") or item.get("num_leechers") or 0),
            seeds=int(item.get("num_seeds") or 0),
            connections=int(item.get("num_connections") or 0),
            tracker_count=trackers,
            tracker_failures=tracker_failures,
        )

    async def _set_priority(self, torrent_hash: str, ids: list[str], priority: int) -> None:
        response = await self._client.post(
            "/api/v2/torrents/filePrio",
            data={"hash": torrent_hash, "id": "|".join(ids), "priority": str(priority)},
        )
        response.raise_for_status()

    async def _tracker_stats(self, torrent_hash: str) -> tuple[int, int]:
        try:
            items = await self._tracker_items(torrent_hash)
        except Exception:
            return 0, 0
        trackers = 0
        failures = 0
        for item in items:
            url = str(item.get("url") or "")
            if not url or url.startswith("**"):
                continue
            trackers += 1
            if int(item.get("status") or 0) == 4:
                failures += 1
        return trackers, failures

    async def _tracker_urls(self, torrent_hash: str) -> set[str]:
        try:
            items = await self._tracker_items(torrent_hash)
        except Exception:
            return set()
        return {
            str(item.get("url") or "").strip()
            for item in items
            if str(item.get("url") or "").strip() and not str(item.get("url") or "").startswith("**")
        }

    async def _tracker_items(self, torrent_hash: str) -> list[dict]:
        response = await self._client.get("/api/v2/torrents/trackers", params={"hash": torrent_hash})
        response.raise_for_status()
        items = response.json()
        return items if isinstance(items, list) else []

    async def pause(self, torrent_hash: str) -> None:
        await self._login()
        response = await self._client.post("/api/v2/torrents/pause", data={"hashes": torrent_hash})
        response.raise_for_status()

    async def resume(self, torrent_hash: str) -> None:
        await self._login()
        response = await self._client.post("/api/v2/torrents/resume", data={"hashes": torrent_hash})
        response.raise_for_status()

    async def refresh_metadata(self, torrent_hash: str) -> None:
        await self._login()
        await self.resume(torrent_hash)
        response = await self._client.post("/api/v2/torrents/reannounce", data={"hashes": torrent_hash})
        response.raise_for_status()

    async def boost_trackers(self, torrent_hash: str) -> None:
        await self._login()
        existing = await self._tracker_urls(torrent_hash)
        missing = [tracker for tracker in PUBLIC_TRACKERS if tracker not in existing]
        if missing:
            response = await self._client.post(
                "/api/v2/torrents/addTrackers",
                data={"hash": torrent_hash, "urls": "\n".join(missing)},
            )
            response.raise_for_status()
        await self.refresh_metadata(torrent_hash)

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
