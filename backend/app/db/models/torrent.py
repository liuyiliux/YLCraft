"""Torrent download records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return uuid.uuid4().hex


class TorrentDownload(SQLModel, table=True):
    """Persistent mapping between YLCraft and the torrent engine."""

    __tablename__ = "torrent_downloads"

    id: str = Field(default_factory=_uuid, primary_key=True)
    engine: str = Field(default="qbittorrent", index=True)
    torrent_hash: str = Field(default="", index=True)
    name: str = Field(default="")
    source: str = Field(default="", description="magnet / torrent_file")
    source_uri: str = Field(default="", description="magnet URI or uploaded torrent path")
    save_path: str = Field(default="")

    status: str = Field(default="metadata", index=True)
    progress: int = Field(default=0)
    download_speed: int = Field(default=0, sa_column=Column(BigInteger, default=0, nullable=False))
    upload_speed: int = Field(default=0, sa_column=Column(BigInteger, default=0, nullable=False))
    downloaded_bytes: int = Field(default=0, sa_column=Column(BigInteger, default=0, nullable=False))
    total_size: int = Field(default=0, sa_column=Column(BigInteger, default=0, nullable=False))

    selected_files_json: str = Field(default="[]")
    asset_ids_json: str = Field(default="[]")
    error_message: str = Field(default="")

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

