"""Torrent configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import ensure_download_path


DEFAULT_METADATA_CACHE_URLS = (
    "https://itorrents.org/torrent/{hash}.torrent",
    "https://torrage.info/torrent.php?h={hash}",
    "https://btcache.me/torrent/{hash}",
    "https://watercache.nanobytes.org/get/{hash}/{hash}.torrent",
)


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
    metadata_cache_urls: list[str]
    metadata_cache_timeout: float
    metadata_cache_max_bytes: int


def get_torrent_config() -> TorrentConfig:
    download_dir = Path(os.getenv("TORRENT_DOWNLOAD_DIR", "") or ensure_download_path("torrents"))
    download_dir.mkdir(parents=True, exist_ok=True)
    return TorrentConfig(
        engine=os.getenv("TORRENT_ENGINE", "qbittorrent").strip().lower() or "qbittorrent",
        qbittorrent_url=os.getenv("QBITTORRENT_URL", "http://127.0.0.1:8080").rstrip("/"),
        qbittorrent_username=os.getenv("QBITTORRENT_USERNAME", "admin"),
        qbittorrent_password=os.getenv("QBITTORRENT_PASSWORD", ""),
        download_dir=download_dir,
        max_active=int(os.getenv("TORRENT_MAX_ACTIVE", "3") or "3"),
        max_upload_bytes=int(os.getenv("TORRENT_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)) or "0"),
        listen_interfaces=os.getenv(
            "TORRENT_LISTEN_INTERFACES",
            "0.0.0.0:6883-6999,[::]:6883-6999",
        ).strip() or "0.0.0.0:6883-6999,[::]:6883-6999",
        metadata_cache_urls=_metadata_cache_urls_from_env(os.getenv("TORRENT_METADATA_CACHE_URLS")),
        metadata_cache_timeout=float(os.getenv("TORRENT_METADATA_CACHE_TIMEOUT", "5") or "5"),
        metadata_cache_max_bytes=int(os.getenv("TORRENT_METADATA_CACHE_MAX_BYTES", str(4 * 1024 * 1024)) or "0"),
    )


def assert_inside_download_dir(path: str | Path, root: str | Path | None = None) -> Path:
    root_path = Path(root) if root else get_torrent_config().download_dir
    root_resolved = root_path.resolve()
    resolved = Path(path).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path is outside torrent download directory: {resolved}")
    return resolved


def _metadata_cache_urls_from_env(value: str | None) -> list[str]:
    if value is None:
        return list(DEFAULT_METADATA_CACHE_URLS)
    value = value.strip()
    if not value or value.lower() in {"0", "false", "off", "none", "disabled"}:
        return []
    normalized = value.replace("\n", ",").replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]
