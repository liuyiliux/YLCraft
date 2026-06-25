"""Torrent engine interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.services.torrent.models import TorrentFileInfo, TorrentStatus


class TorrentEngine(ABC):
    @abstractmethod
    async def add_magnet(self, magnet: str, save_path: Path, start_paused: bool = True) -> str:
        """Add a magnet link and return the torrent hash if available."""

    @abstractmethod
    async def add_torrent_file(self, torrent_file: Path, save_path: Path, start_paused: bool = True) -> str:
        """Add a .torrent file and return the torrent hash if available."""

    @abstractmethod
    async def list_torrents(self) -> list[TorrentStatus]:
        """Return all visible torrents from the engine."""

    @abstractmethod
    async def list_files(self, torrent_hash: str) -> list[TorrentFileInfo]:
        """Return files for a torrent."""

    @abstractmethod
    async def select_files(self, torrent_hash: str, file_indexes: list[int]) -> None:
        """Set selected files to normal priority and other files to skipped."""

    @abstractmethod
    async def pause(self, torrent_hash: str) -> None:
        """Pause a torrent."""

    @abstractmethod
    async def resume(self, torrent_hash: str) -> None:
        """Resume a torrent."""

    @abstractmethod
    async def refresh_metadata(self, torrent_hash: str) -> None:
        """Ask the engine to reannounce and retry metadata discovery."""

    @abstractmethod
    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None:
        """Delete a torrent from the engine."""

    @abstractmethod
    async def close(self) -> None:
        """Release engine resources."""
