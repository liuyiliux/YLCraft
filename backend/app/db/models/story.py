"""
YLCraft — Story 数据模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlmodel import SQLModel, Field


class StoryStatus(str, Enum):
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class StoryStyle(str, Enum):
    SHORT_DRAMA = "short_drama"   # 都市短剧
    MANGA = "manga"               # 二次元漫剧


class Story(SQLModel, table=True):
    """故事项目主表"""
    __tablename__ = "stories"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    title: str = Field(default="", index=True)
    topic: str = Field(default="", description="用户输入的主题/提示词")
    style: str = Field(default=StoryStyle.SHORT_DRAMA.value)

    # LLM 生成的内容
    plot_outline: str = Field(default="", description="故事大纲")
    style_hint: str = Field(default="", description="视觉风格描述，用于AI生图")
    music_hint: str = Field(default="", description="配乐建议")

    # JSON 存储
    characters_json: str = Field(default="[]")
    scenes_json: str = Field(default="[]")

    status: str = Field(default=StoryStatus.GENERATING.value)

    # 统计
    scene_count: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class StoryCharacterPortrait(SQLModel, table=True):
    """故事角色肖像（多视图）"""
    __tablename__ = "story_character_portraits"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    story_id: str = Field(index=True)
    character_name: str = Field(default="", index=True)
    character_id: str = Field(default="", description="关联到角色库的角色ID（可选）")

    # JSON 存储多视图 URL 列表
    portrait_urls: str = Field(default="[]", description="多视图图片 URLs（JSON 数组）")
    selected_url: str = Field(default="", description="用户选中的主立绘 URL")

    prompt_used: str = Field(default="", description="生成时使用的 prompt")
    seed: str = Field(default="", description="生成时使用的 seed，用于一致性")

    created_at: datetime = Field(default_factory=datetime.now)