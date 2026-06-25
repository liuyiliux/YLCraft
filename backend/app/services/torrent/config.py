"""Torrent configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import ensure_download_path


@dataclass
class TorrentConfig:
    engine: str
    qbittorrent_url: str
    qbittorrent_username: str
    qbittorrent_password: str
    download_dir: Path
    max_active: int
    max_upload_bytes: int
    listen_interfaces: str


def get_torrent_config() -> TorrentConfig:
    download_dir = Path(os.getenv("TORRENT_DOWNLOAD_DIR", "") or ensure_download_path("torrents"))
    download_dir.mkdir(parents=True, exist_ok=True)
    return TorrentConfig(
        engine=os.getenv("TORRENT_ENGINE", "qbittorrent").strip().lower() or "qbittorrent",
        qbittorrent_url=os.getenv("QBITTORRENT_URL", "http://127.0.0.1:8080").rstrip("/"),
        qbittorrent_username=os.getenv("QBITTORRENT_USERNAME", "admin"),
        qbittorrent_password=os.getenv("QBITTORRENT_PASSWORD", "adminadmin"),
        download_dir=download_dir,
        max_active=int(os.getenv("TORRENT_MAX_ACTIVE", "3") or "3"),
        max_upload_bytes=int(os.getenv("TORRENT_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)) or "0"),
        listen_interfaces=os.getenv(
            "TORRENT_LISTEN_INTERFACES",
            "0.0.0.0:6881-6999,[::]:6881-6999",
        ).strip() or "0.0.0.0:6881-6999,[::]:6881-6999",
    )


def assert_inside_download_dir(path: str | Path, root: str | Path | None = None) -> Path:
    root_path = Path(root) if root else get_torrent_config().download_dir
    root_resolved = root_path.resolve()
    resolved = Path(path).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path is outside torrent download directory: {resolved}")
    return resolved
