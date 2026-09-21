"""Persisted 3D director previs scene documents and reusable motion assets."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class PrevisSceneDocument(SQLModel, table=True):
    """A 3D previs scene; may be linked to one project storyboard panel or standalone.

    Standalone scenes leave `project_id` / `storyboard_content_id` / `panel_number`
    all NULL so users can block out an idea without a project yet.
    """

    __tablename__ = "previs_scene_documents"
    __table_args__ = (
        Index(
            "ix_previs_scene_documents_storyboard_panel",
            "project_id",
            "storyboard_content_id",
            "panel_number",
        ),
    )

    id: str = Field(primary_key=True, max_length=80)
    project_id: Optional[str] = Field(default=None, foreign_key="creative_projects.id", index=True, max_length=80)
    storyboard_content_id: Optional[str] = Field(default=None, foreign_key="project_contents.id", index=True, max_length=80)
    panel_number: Optional[int] = Field(default=None, index=True)
    title: str = Field(default="3D 预演", max_length=160)
    scene_json: dict = Field(default_factory=dict, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    revision: int = Field(default=1, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class PrevisMotionAsset(SQLModel, table=True):
    """A reusable pose or motion that a previs scene object can reference.

    **刻意不进素材库**：动作是"驱动参数"而不是素材——脱离载体它没有任何可看的表现，
    素材库的缩略图、向量检索与血缘对它都是无效成本。场景只保存动作标识（引用），
    动作本体在这里更新后所有引用自动生效。

    `carrier` 决定驱动谁：

    - `params`：人形参数载体的 16 个关节通道（程序化人形用，`skeleton` 标记参数集版本）；
    - `transform`：位置/旋转/缩放曲线，**不需要骨骼**，因此任何对象都能用（非人形的兜底）；
    - `bone`：骨骼型动作，`file_path` 指向动作文件，`skeleton` 记录它适用的骨架规格。

    `origin` 必填、`license` 可空：许可为空时接口把它标为"未核实"而不是假装已获授权，
    这样既不会因为"程序化生成的动作没有外部来源"而阻塞入库，也不会有含糊的合规表述。
    """

    __tablename__ = "previs_motion_assets"

    id: str = Field(primary_key=True, max_length=80)
    #: 稳定标识（kebab-case）。种子数据按它做幂等 upsert，因此不要改已发布条目的 slug。
    slug: str = Field(index=True, unique=True, max_length=80)
    name: str = Field(default="", max_length=120)
    carrier: str = Field(default="params", index=True, max_length=20)
    #: 兼容规格：params 为参数集版本，bone 为骨架规格（mixamo / vrm / 具体模型骨架）
    skeleton: Optional[str] = Field(default=None, index=True, max_length=60)
    category: str = Field(default="", index=True, max_length=40)
    tags_json: list = Field(default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    duration_seconds: float = Field(default=0.0)
    fps: int = Field(default=24)
    frame_count: int = Field(default=0)
    loopable: bool = Field(default=False)
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    file_path: Optional[str] = Field(default=None, max_length=500)
    origin: str = Field(default="", max_length=200)
    license: Optional[str] = Field(default=None, max_length=200)
    license_url: Optional[str] = Field(default=None, max_length=500)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
