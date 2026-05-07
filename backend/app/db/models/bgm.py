"""
YLCraft — BGM 配乐数据模型

定义 BGM 曲目的数据库模型，支持内置 BGM 库和用户自定义上传。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class BGMTrack(SQLModel, table=True):
    """BGM 曲目表"""
    __tablename__ = "bgm_tracks"

    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )

    # 基本信息
    name: str = Field(default="", index=True)           # 曲目名称
    artist: str = Field(default="")                      # 艺术家
    description: str = Field(default="")                 # 描述

    # 文件信息
    file_path: str = Field(default="")                   # 音频文件路径（本地）
    file_size: int = Field(default=0)                    # 文件大小（字节）
    duration: float = Field(default=0.0)                 # 时长（秒）
    mime_type: str = Field(default="audio/mpeg")         # MIME 类型

    # 分类信息
    genre: str = Field(default="", index=True)           # 风格：upbeat/calm/epic/ambient/cinematic/jazz
    mood: str = Field(default="", index=True)            # 情绪：happy/sad/energetic/relaxed/intense/neutral
    bpm: int = Field(default=0)                          # 节拍速度（BPM）
    tags: str = Field(default="")                        # 标签，逗号分隔

    # 状态
    is_builtin: bool = Field(default=True)               # 是否内置（内置不可删除）
    is_favorite: bool = Field(default=False)             # 是否收藏

    # 来源
    source_url: str = Field(default="")                  # 来源 URL（内置时记录授权信息）
    license: str = Field(default="")                     # 版权信息（如 CC0, YouTube Audio Library）

    # 时间
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
