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
from app.services.torrent.models import VIDEO_EXTENSIONS, TorrentFileInfo, TorrentHealth, TorrentStatus
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

    async def prioritize_streaming(self, record: TorrentDownload, file_index: int) -> TorrentDownload:
        if not record.torrent_hash:
            await self.sync_record(record)
        if not record.torrent_hash:
            raise ValueError("Torrent metadata is not ready yet")
        await self.engine.prioritize_streaming(record.torrent_hash, int(file_index))
        record.status = "downloading"
        record.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(record)
        return await self.sync_record(record)

    async def get_health(self, record: TorrentDownload, file_index: int | None = None) -> TorrentHealth:
        if not record.torrent_hash:
            await self.sync_record(record)
        health = None
        if record.torrent_hash:
            health = await self.engine.get_health(record.torrent_hash)
        if health is None:
            health = TorrentHealth(
                torrent_hash=record.torrent_hash,
                state=record.status,
                normalized_status=record.status,
                has_metadata=record.status != "metadata",
                progress=max(0, min(1, (record.progress or 0) / 100)),
                download_speed=record.download_speed,
                upload_speed=record.upload_speed,
            )
        await self._enrich_health(record, health, file_index)
        return health

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

    async def boost_trackers(self, record: TorrentDownload) -> TorrentDownload:
        if not record.torrent_hash:
            await self.sync_record(record)
        if not record.torrent_hash:
            raise ValueError("Torrent metadata is not ready yet")
        await self.engine.boost_trackers(record.torrent_hash)
        hint = "已补充公共 tracker 并重新公告，正在等待 peer 响应"
        record.error_message = hint
        if record.status == "paused":
            record.status = "downloading"
        record.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(record)
        record = await self.sync_record(record)
        if not record.error_message:
            record.error_message = hint
            record.updated_at = datetime.now()
            await self.session.flush()
            await self.session.refresh(record)
        return record

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

    async def _enrich_health(
        self,
        record: TorrentDownload,
        health: TorrentHealth,
        file_index: int | None,
    ) -> None:
        files: list[TorrentFileInfo] = []
        if record.torrent_hash and health.has_metadata:
            try:
                files = await self.list_files(record)
            except Exception:
                files = []
        selected = set(_safe_json_ints(record.selected_files_json))
        videos = [item for item in files if item.is_video]
        selected_videos = [item for item in videos if item.index in selected]
        target = _target_file(files, selected_videos, videos, file_index)

        health.selected_file_count = len(selected)
        health.selected_video_count = len(selected_videos)
        if target:
            health.target_file_index = int(target.index)
            health.target_file_name = target.name
            health.target_file_size = int(target.size or 0)
            health.target_file_progress = max(0, min(1, float(target.progress or 0)))
            path = _resolve_local_torrent_file(record, target, self.config.download_dir)
            health.target_file_available = bool(path and path.is_file() and path.stat().st_size > 0)
            health.ready_to_stream = target.is_video and health.target_file_available and health.target_file_progress > 0
        health.reason = _describe_health(record, health, target)
        health.hints = _health_hints(health, target)

    async def _create_or_update_asset(self, record: TorrentDownload, item: TorrentFileInfo, path: Path) -> Asset:
        source_url = _torrent_asset_source_url(record, item)
        candidate_source_urls = [source_url]
        legacy_source_url = record.source_uri if record.source == "magnet" else ""
        if legacy_source_url and legacy_source_url != source_url and int(item.index) == 0:
            candidate_source_urls.append(legacy_source_url)
        result = await self.session.execute(select(Asset).where(Asset.source_url.in_(candidate_source_urls)))
        asset = next(iter(result.scalars().all()), None)
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
            asset.source_url = source_url
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


def _safe_json_ints(value: str) -> list[int]:
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    result: list[int] = []
    for item in parsed:
        try:
            result.append(int(item))
        except Exception:
            continue
    return result


def _target_file(
    files: list[TorrentFileInfo],
    selected_videos: list[TorrentFileInfo],
    videos: list[TorrentFileInfo],
    file_index: int | None,
) -> TorrentFileInfo | None:
    if file_index is not None:
        return next((item for item in files if int(item.index) == int(file_index)), None)
    if selected_videos:
        return selected_videos[0]
    if videos:
        return videos[0]
    return None


def _resolve_local_torrent_file(
    record: TorrentDownload,
    item: TorrentFileInfo,
    download_root: Path,
) -> Path | None:
    try:
        base_dir = Path(record.save_path or download_root)
        path = assert_inside_download_dir(base_dir / item.name, download_root)
    except Exception:
        return None
    if path.is_file():
        return path
    qbittorrent_incomplete = path.with_name(f"{path.name}.!qB")
    if qbittorrent_incomplete.is_file():
        return qbittorrent_incomplete
    return path


def _describe_health(
    record: TorrentDownload,
    health: TorrentHealth,
    target: TorrentFileInfo | None,
) -> str:
    if record.status == "metadata" or not health.has_metadata:
        return "正在获取种子元数据，还不能选择文件或在线播放。"
    if not target:
        return "已获取种子元数据，但没有发现可在线播放的视频文件。"
    if not target.is_video:
        return "当前目标文件不是视频文件，不能在线播放。"
    if health.selected_file_count <= 0:
        return "已获取文件列表，选择视频文件并开始下载后才能边下边播。"
    if health.ready_to_stream:
        return "本机已经拿到当前视频的可读取片段，可以尝试在线播放。"
    if health.target_file_progress <= 0 and health.download_speed <= 0:
        if health.connections <= 0 and health.peers <= 0 and health.seeds <= 0:
            return "当前还没有连到可下载的 peer，本机暂时拿不到视频片段。"
        return "已经连到部分 peer，但当前视频还没有收到可播放片段。"
    if health.download_speed > 0:
        return "下载已经有速度，正在等待当前视频的头部或尾部片段就绪。"
    return "任务正在等待更多片段，片段到达后即可尝试在线播放。"


def _health_hints(health: TorrentHealth, target: TorrentFileInfo | None) -> list[str]:
    hints: list[str] = []
    if not health.has_metadata:
        if health.dht_nodes <= 0:
            hints.append("DHT 节点为 0 时，通常需要检查本机网络、防火墙或 UDP 端口。")
        if health.tracker_count > 0 and health.tracker_failures >= health.tracker_count:
            hints.append("当前 tracker 多数不可用，可以稍后重试元数据或补充 tracker。")
        hints.append("磁力链接必须先从 DHT、tracker 或 peer 拿到元数据，云盘能识别不代表本机一定能拿到。")
        return hints[:3]
    if target and target.is_video and health.target_file_progress <= 0:
        hints.append("边下边播需要本机先下载到当前视频的部分片段；长期 0 B/s 多半是资源健康度不足。")
    if health.dht_nodes <= 0:
        hints.append("DHT 节点为 0 会降低发现 peer 的概率，可以检查网络、防火墙或监听端口。")
    if health.tracker_count > 0 and health.tracker_failures >= health.tracker_count:
        hints.append("tracker 全部失败时只能依赖 DHT/已有 peer，获取速度可能很慢。")
    if health.peers <= 0 and health.seeds <= 0:
        hints.append("如果迅雷或夸克能秒播，常见原因是它们命中了云端缓存；YLCraft 本地模式不会使用这类缓存。")
    return hints[:3]


def _torrent_asset_source_url(record: TorrentDownload, item: TorrentFileInfo) -> str:
    if record.torrent_hash:
        return f"torrent:{record.torrent_hash}:{int(item.index)}"
    if record.source_uri:
        return f"{record.source_uri}#file={int(item.index)}"
    return f"torrent:{record.id}:{int(item.index)}"


def _create_engine(config):
    if config.engine == "qbittorrent":
        return QBittorrentEngine(config)
    if config.engine == "libtorrent":
        from app.services.torrent.libtorrent_engine import LibtorrentEngine

        return LibtorrentEngine(config)
    raise RuntimeError(f"Unsupported torrent engine: {config.engine}")
