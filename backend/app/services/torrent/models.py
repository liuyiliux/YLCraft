"""Shared models for torrent services."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".flv",
    ".wmv",
    ".ts",
    ".m2ts",
}


@dataclass
class TorrentFileInfo:
    index: int
    name: str
    size: int = 0
    progress: float = 0.0
    priority: int = 0

    @property
    def is_video(self) -> bool:
        return Path(self.name).suffix.lower() in VIDEO_EXTENSIONS


@dataclass
class TorrentStatus:
    torrent_hash: str
    name: str = ""
    state: str = ""
    progress: float = 0.0
    download_speed: int = 0
    upload_speed: int = 0
    downloaded_bytes: int = 0
    total_size: int = 0
    save_path: str = ""
    error: str = ""

    @property
    def normalized_status(self) -> str:
        state = (self.state or "").lower()
        if state in {"pauseddl", "pausedup", "paused", "stalleddl"}:
            return "paused" if state.startswith("paused") else "downloading"
        if state in {"uploading", "stalledup", "forcedup", "queuedup"}:
            return "done"
        if state in {"error", "missingfiles"}:
            return "failed"
        if state in {"metadl", "checkingdl", "checkingresume"}:
            return "metadata"
        return "downloading"


@dataclass
class TorrentHealth:
    torrent_hash: str = ""
    state: str = ""
    normalized_status: str = ""
    has_metadata: bool = False
    progress: float = 0.0
    download_speed: int = 0
    upload_speed: int = 0
    peers: int = 0
    seeds: int = 0
    connections: int = 0
    dht_nodes: int = 0
    tracker_count: int = 0
    tracker_failures: int = 0
    is_listening: bool = False
    listen_port: int = 0
    has_incoming_connections: bool = False
    selected_file_count: int = 0
    selected_video_count: int = 0
    target_file_index: int | None = None
    target_file_name: str = ""
    target_file_size: int = 0
    target_file_progress: float = 0.0
    target_file_available: bool = False
    ready_to_stream: bool = False
    reason: str = ""
    hints: list[str] = field(default_factory=list)
