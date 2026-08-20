"""Persisted 3D director previs scene documents."""

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
