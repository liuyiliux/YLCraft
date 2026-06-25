"""Torrent orchestration service."""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ffmpeg_path
from app.db.models.asset import Asset
from app.db.models.torrent import TorrentDownload
from app.services.torrent.config import assert_inside_download_dir, get_torrent_config
from app.services.torrent.models import VIDEO_EXTENSIONS, TorrentFileInfo, TorrentStatus
from app.services.torrent.qbittorrent import QBittorrentEngine


class TorrentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.config = get_torrent_config()
        self.engine = _create_engine(self.config)

    async def close(self) -> None:
        await self.engine.close()

    async def add_magnet(self, magnet: str, start_paused: bool = True) -> TorrentDownload:
        if not magnet.lower().startswith("magnet:?") or "btih:" not in magnet.lower():
            raise ValueError("Invalid magnet link")
        await self._assert_active_limit()
        torrent_hash = await self.engine.add_magnet(magnet, self.config.download_dir, start_paused=start_paused)
        record = TorrentDownload(
            engine=self.config.engine,
            torrent_hash=torrent_hash,
            source="magnet",
            source_uri=magnet,
            save_path=str(self.config.download_dir),
            status="metadata",
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        if torrent_hash:
            await self.sync_record(record)
        return record

    async def add_torrent_file(self, torrent_file: Path, original_name: str, start_paused: bool = True) -> TorrentDownload:
        if torrent_file.suffix.lower() != ".torrent":
            raise ValueError("Only .torrent files are supported")
        await self._assert_active_limit()
        stored = self.config.download_dir / "_torrents" / f"{uuid.uuid4().hex}_{Path(original_name).name}"
        stored.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(torrent_file, stored)
        torrent_hash = await self.engine.add_torrent_file(stored, self.config.download_dir, start_paused=start_paused)
        record = TorrentDownload(
            engine=self.config.engine,
            torrent_hash=torrent_hash,
            name=Path(original_name).stem,
            source="torrent_file",
            source_uri=str(stored),
            save_path=str(self.config.download_dir),
            status="metadata",
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        await self.sync_record(record)
        return record

    async def get_record(self, download_id: str) -> TorrentDownload | None:
        result = await self.session.execute(select(TorrentDownload).where(TorrentDownload.id == download_id))
        record = result.scalar_one_or_none()
        if record and record.status != "deleted":
            await self.sync_record(record)
        return record

    async def list_records(self) -> list[TorrentDownload]:
        result = await self.session.execute(
            select(TorrentDownload)
            .where(TorrentDownload.status != "deleted")
            .order_by(TorrentDownload.created_at.desc())
        )
        records = list(result.scalars().all())
        for record in records[:20]:
            await self.sync_record(record)
        return records

    async def sync_record(self, record: TorrentDownload) -> TorrentDownload:
        if record.status == "deleted":
            return record
        if not record.torrent_hash:
            matched = await self._match_hash(record)
            if matched:
                record.torrent_hash = matched.torrent_hash
        await self._ensure_record_loaded(record)
        if record.torrent_hash:
            status = await self._get_engine_status(record.torrent_hash)
            if status:
                self._apply_status(record, status)
        record.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def list_files(self, record: TorrentDownload) -> list[TorrentFileInfo]:
        if not record.torrent_hash:
            await self.sync_record(record)
        if not record.torrent_hash:
            return []
        return await self.engine.list_files(record.torrent_hash)

    async def get_file_for_stream(self, record: TorrentDownload, file_index: int) -> tuple[TorrentFileInfo, Path]:
        files = await self.list_files(record)
        item = next((file for file in files if int(file.index) == int(file_index)), None)
        if not item:
            raise ValueError("Torrent file not found")
        if not item.is_video:
            raise ValueError("Only video files can be streamed")

        base_dir = Path(record.save_path or self.config.download_dir)
        path = assert_inside_download_dir(base_dir / item.name, self.config.download_dir)
        if not path.is_file():
            qbittorrent_incomplete = path.with_name(f"{path.name}.!qB")
            if qbittorrent_incomplete.is_file():
                path = qbittorrent_incomplete
        if not path.is_file():
            raise FileNotFoundError("Video file is not available locally yet")
        return item, path

    async def select_files(self, record: TorrentDownload, file_indexes: list[int], start: bool = True) -> TorrentDownload:
        if not record.torrent_hash:
            await self.sync_record(record)
        if not record.torrent_hash:
            raise ValueError("Torrent metadata is not ready yet")
        await self.engine.select_files(record.torrent_hash, file_indexes)
        record.selected_files_json = json.dumps(sorted({int(i) for i in file_indexes}))
        if start:
            await self.engine.resume(record.torrent_hash)
            record.status = "downloading"
        record.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def pause(self, record: TorrentDownload) -> TorrentDownload:
        if record.torrent_hash:
            await self.engine.pause(record.torrent_hash)
        record.status = "paused"
        record.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def resume(self, record: TorrentDownload) -> TorrentDownload:
        if record.torrent_hash:
            await self.engine.resume(record.torrent_hash)
        record.status = "downloading"
        record.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def refresh_metadata(self, record: TorrentDownload) -> TorrentDownload:
        if not record.torrent_hash:
            await self.sync_record(record)
        if not record.torrent_hash:
            raise ValueError("Torrent metadata is not ready yet")
        await self.engine.refresh_metadata(record.torrent_hash)
        record.status = "metadata"
        record.error_message = "已重新公告，正在重新获取种子元数据"
        record.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(record)
        return await self.sync_record(record)

    async def delete(self, record: TorrentDownload, delete_files: bool = False) -> None:
        if record.torrent_hash:
            await self.engine.delete(record.torrent_hash, delete_files=delete_files)
        record.status = "deleted"
        record.updated_at = datetime.now()
        await self.session.flush()

    async def import_assets(self, record: TorrentDownload) -> list[Asset]:
        files = await self.list_files(record)
        selected = set(json.loads(record.selected_files_json or "[]"))
        imported: list[Asset] = []
        for item in files:
            if selected and item.index not in selected:
                continue
            if Path(item.name).suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            path = assert_inside_download_dir(Path(record.save_path or self.config.download_dir) / item.name, self.config.download_dir)
            if not path.is_file():
                continue
            asset = await self._create_or_update_asset(record, item, path)
            imported.append(asset)
        record.asset_ids_json = json.dumps([a.id for a in imported], ensure_ascii=False)
        record.updated_at = datetime.now()
        await self.session.flush()
        return imported

    async def _create_or_update_asset(self, record: TorrentDownload, item: TorrentFileInfo, path: Path) -> Asset:
        source_url = record.source_uri if record.source == "magnet" else f"torrent:{record.torrent_hash}:{item.index}"
        result = await self.session.execute(select(Asset).where(Asset.source_url == source_url))
        asset = result.scalar_one_or_none()
        probe = _probe_video(path)
        metadata = {
            "torrent_hash": record.torrent_hash,
            "torrent_name": record.name,
            "download_id": record.id,
            "file_index": item.index,
            "original_file_name": item.name,
        }
        if asset is None:
            asset = Asset(
                type="VIDEO",
                title=Path(item.name).stem,
                platform="torrent",
                source_type="torrent",
                source_url=source_url,
                file_path=str(path),
                file_size=path.stat().st_size,
                mime_type=mimetypes.guess_type(path.name)[0] or "video/mp4",
                duration=probe.get("duration", 0),
                width=probe.get("width", 0),
                height=probe.get("height", 0),
                status="READY",
                tags=json.dumps(["torrent"], ensure_ascii=False),
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            )
            self.session.add(asset)
        else:
            asset.file_path = str(path)
            asset.file_size = path.stat().st_size
            asset.mime_type = mimetypes.guess_type(path.name)[0] or asset.mime_type or "video/mp4"
            asset.duration = probe.get("duration", asset.duration)
            asset.width = probe.get("width", asset.width)
            asset.height = probe.get("height", asset.height)
            asset.status = "READY"
            asset.metadata_json = json.dumps(metadata, ensure_ascii=False)
            asset.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(asset)
        return asset

    async def _assert_active_limit(self) -> None:
        result = await self.session.execute(
            select(TorrentDownload).where(TorrentDownload.status.in_(["metadata", "downloading", "paused"]))
        )
        active = [r for r in result.scalars().all() if r.status != "deleted"]
        if len(active) >= self.config.max_active:
            raise RuntimeError(f"Active torrent task limit reached: {self.config.max_active}")

    async def _get_engine_status(self, torrent_hash: str) -> TorrentStatus | None:
        torrents = await self.engine.list_torrents()
        target = (torrent_hash or "").lower()
        return next((t for t in torrents if (t.torrent_hash or "").lower() == target), None)

    async def _ensure_record_loaded(self, record: TorrentDownload) -> None:
        if self.config.engine != "libtorrent" or record.engine != "libtorrent" or not record.source_uri:
            return
        if record.torrent_hash and await self._get_engine_status(record.torrent_hash):
            return

        save_path = Path(record.save_path or self.config.download_dir)
        start_paused = record.status not in {"metadata", "downloading"}
        try:
            torrent_hash = ""
            if record.source == "magnet":
                torrent_hash = await self.engine.add_magnet(record.source_uri, save_path, start_paused=start_paused)
            elif record.source == "torrent_file":
                torrent_path = Path(record.source_uri)
                if torrent_path.is_file():
                    torrent_hash = await self.engine.add_torrent_file(torrent_path, save_path, start_paused=start_paused)
            if torrent_hash and not record.torrent_hash:
                record.torrent_hash = torrent_hash
        except Exception as exc:
            record.error_message = str(exc)

    async def _match_hash(self, record: TorrentDownload) -> TorrentStatus | None:
        torrents = await self.engine.list_torrents()
        if record.source == "magnet" and "btih:" in record.source_uri.lower():
            marker = "btih:"
            value = record.source_uri.lower().split(marker, 1)[1].split("&", 1)[0]
            return next((t for t in torrents if t.torrent_hash == value), None)
        if record.name:
            return next((t for t in torrents if t.name == record.name), None)
        return None

    @staticmethod
    def _apply_status(record: TorrentDownload, status: TorrentStatus) -> None:
        record.name = status.name or record.name
        record.save_path = status.save_path or record.save_path
        record.status = status.normalized_status
        record.progress = max(0, min(100, int(status.progress * 100)))
        record.download_speed = status.download_speed
        record.upload_speed = status.upload_speed
        record.downloaded_bytes = status.downloaded_bytes
        record.total_size = status.total_size
        record.error_message = status.error or ""


def _probe_video(path: Path) -> dict:
    ffprobe = get_ffmpeg_path().with_name("ffprobe.exe")
    if not ffprobe.exists():
        ffprobe = Path("ffprobe")
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20)
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        return {
            "width": int(stream.get("width") or 0),
            "height": int(stream.get("height") or 0),
            "duration": int(float(fmt.get("duration") or 0)),
        }
    except Exception:
        return {}


def _create_engine(config):
    if config.engine == "qbittorrent":
        return QBittorrentEngine(config)
    if config.engine == "libtorrent":
        from app.services.torrent.libtorrent_engine import LibtorrentEngine

        return LibtorrentEngine(config)
    raise RuntimeError(f"Unsupported torrent engine: {config.engine}")
