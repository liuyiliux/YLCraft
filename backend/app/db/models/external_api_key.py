"""
YLCraft — 平台级外部 Agent API 密钥

外部智能体调用 YLCraft 能力（素材上传、生图/生视频/3D、文本等）时使用。
区别于数据库里的供应商密钥（ApiKey / AIConnector.api_key）；本表只保存
key 的哈希与元数据，不存明文，用于识别调用方、控制作用域与速率。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class ExternalApiKey(SQLModel, table=True):
    __tablename__ = "external_api_keys"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    name: str = Field(default="", max_length=80, index=True)
    key_hash: str = Field(index=True, max_length=128)
    key_prefix: str = Field(default="", max_length=16)
    scope: str = Field(default="read", max_length=16, index=True)
    rate_limit_per_min: int = Field(default=60)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = Field(default=None)
    use_count: int = Field(default=0)
