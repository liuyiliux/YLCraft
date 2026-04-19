"""
YLCraft — 素材资产数据模型

使用 SQLModel（Pydantic v2）定义素材资产库的数据库模型。
支持：视频、图片、音频、文档四种素材类型。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field


class AssetType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"


class AssetStatus(str, Enum):
    PARSED = "parsed"
    DOWNLOADING = "downloading"
    READY = "ready"
    PROCESSING = "processing"
    ERROR = "error"


class Asset(SQLModel, table=True):
    """素材资产主表"""
    __tablename__ = "assets"

    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )

    asset_type: AssetType = Field(default=AssetType.VIDEO, index=True)
    title: str = Field(default="", index=True)
    description: str = Field(default="")

    file_path: str = Field(default="")
    file_size: int = Field(default=0)
    mime_type: str = Field(default="")
    duration: int = Field(default=0)
    width: int = Field(default=0)
    height: int = Field(default=0)

    source_url: str = Field(default="", unique=True, index=True)
    platform: str = Field(default="", index=True)
    author: str = Field(default="")
    author_url: str = Field(default="")

    thumbnail_path: str = Field(default="")

    status: AssetStatus = Field(default=AssetStatus.PARSED, index=True)
    error_message: str = Field(default="")

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    downloaded_at: Optional[datetime] = Field(default=None)

    use_count: int = Field(default=0)
    last_used_at: Optional[datetime] = Field(default=None)

    tags: str = Field(default="[]")
    metadata_json: str = Field(default="{}")

    class Config:
        use_enum_values = True


class AssetCollection(SQLModel, table=True):
    """资产收藏集"""
    __tablename__ = "asset_collections"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    name: str = Field(default="", index=True)
    description: str = Field(default="")
    cover_asset_id: str = Field(default="")
    collection_type: str = Field(default="manual")
    smart_rules: str = Field(default="{}")
    asset_ids: str = Field(default="[]")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class AssetTag(SQLModel, table=True):
    """资产标签表"""
    __tablename__ = "asset_tags"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    name: str = Field(unique=True, index=True)
    color: str = Field(default="#1890ff")
    asset_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
