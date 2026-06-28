"""
YLCraft — 创作项目闭环模型

用于承载小说、短剧、漫画等连续创作项目。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class CreativeProjectStatus(str, Enum):
    DRAFT = "draft"
    OUTLINING = "outlining"
    PLANNING = "planning"
    SCRIPTING = "scripting"
    STORYBOARDING = "storyboarding"
    READY = "ready"
    ARCHIVED = "archived"
    FAILED = "failed"


class CreativeProject(SQLModel, table=True):
    """创作项目主表。"""

    __tablename__ = "creative_projects"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    title: str = Field(default="", index=True)
    project_type: str = Field(default="short_drama", index=True)
    source_type: str = Field(default="original_idea", index=True)
    source_ref_json: str = Field(default="{}")

    status: str = Field(default=CreativeProjectStatus.DRAFT.value, index=True)
    current_stage: str = Field(default="outline", index=True)

    outline_json: str = Field(default="{}")
    chapter_plan_json: str = Field(default="{}")
    settings_json: str = Field(default="{}")
    metadata_json: str = Field(default="{}")

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class ProjectContent(SQLModel, table=True):
    """项目阶段内容，支持版本化保存。"""

    __tablename__ = "project_contents"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    content_type: str = Field(index=True)

    chapter_number: int | None = Field(default=None, index=True)
    episode_number: int | None = Field(default=None, index=True)
    title: str = Field(default="", index=True)

    data_json: str = Field(default="{}")
    text_content: str = Field(default="")
    source_content_id: str | None = Field(default=None, index=True)

    version: int = Field(default=1, index=True)
    is_locked: bool = Field(default=False, index=True)

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)


class ProjectAssetLink(SQLModel, table=True):
    """项目内容与素材库资产的关系。"""

    __tablename__ = "project_asset_links"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    asset_id: str = Field(index=True)
    content_id: str | None = Field(default=None, foreign_key="project_contents.id", index=True)

    role: str = Field(default="reference", index=True)
    relation: str = Field(default="references", index=True)
    metadata_json: str = Field(default="{}")

    created_at: datetime = Field(default_factory=datetime.now, index=True)


class ProjectGenerationLog(SQLModel, table=True):
    """项目阶段生成日志。

    支持多种场景（scene 字段）：
    - creative_project: 创作项目阶段生成（默认，向后兼容）
    - character_portrait: 角色立绘生成
    - 其他 AI 生成场景可继续扩展

    当 scene != "creative_project" 时，project_id 可为空，
    改用 ref_id 关联具体资源（如 character_id）。
    """

    __tablename__ = "project_generation_logs"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str | None = Field(default=None, foreign_key="creative_projects.id", index=True)
    content_id: str | None = Field(default=None, foreign_key="project_contents.id", index=True)

    # 新增：场景标记 + 通用关联 ID（character_id / asset_node_id 等）
    scene: str = Field(default="creative_project", index=True)
    ref_id: str | None = Field(default=None, index=True)

    stage: str = Field(default="", index=True)
    provider: str = Field(default="", index=True)
    model: str = Field(default="", index=True)
    status: str = Field(default="success", index=True)

    prompt: str = Field(default="")
    request_json: str = Field(default="{}")
    raw_response: str = Field(default="")
    normalized_json: str = Field(default="{}")
    validation_error: str = Field(default="")

    created_at: datetime = Field(default_factory=datetime.now, index=True)

