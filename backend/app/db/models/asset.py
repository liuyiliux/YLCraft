"""
YLCraft — 素材资产数据模型（优化版 v2）

使用方案 B：单表 + JSON metadata
- 通用字段放在主表
- 类型特定字段放在 metadata JSON 中
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column
from sqlmodel import SQLModel, Field


class Asset(SQLModel, table=True):
    """素材资产表（优化版 v2 — 单表 + JSON metadata）"""
    __tablename__ = "assets"

    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )

    type: str = Field(index=True)  # 'video' | 'image' | 'audio' | 'document'
    platform: str = Field(default="", index=True)
    title: str = Field(default="", index=True)
    author: str = Field(default="")
    cover_url: str = Field(default="")

    duration: int = Field(default=0)
    width: int = Field(default=0)
    height: int = Field(default=0)

    file_path: str = Field(default="")
    file_size: int = Field(default=0, sa_column=Column(BigInteger, default=0, nullable=False))
    mime_type: str = Field(default="")

    status: str = Field(default="parsed", index=True)
    progress: int = Field(default=0)

    # 来源类型（用于过滤）：upload / parse / ai_generated / import
    source_type: str = Field(default="", index=True)

    # 核心：存储所有类型特定的字段（JSON 字符串）
    metadata_json: str = Field(default="{}")

    # JSON 数组：["tag1", "tag2"]
    tags: str = Field(default="[]")

    # 原始来源 URL（唯一，用于去重）
    source_url: str = Field(default="", unique=True, index=True)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deleted_at: datetime | None = Field(default=None, index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None or self.status == "DELETED"

    class Config:
        use_enum_values = True


# 保留旧表名兼容（已备份为 assets_backup）
# class AssetBackup(SQLModel, table=False):
#     __tablename__ = "assets_backup"



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
    deleted_at: datetime | None = Field(default=None, index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None or self.status == "DELETED"

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
