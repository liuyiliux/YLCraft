"""Free-form creative canvas persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class CanvasDocument(SQLModel, table=True):
    """A persisted free-form canvas document for /canvas."""

    __tablename__ = "canvas_documents"

    id: str = Field(primary_key=True, max_length=80)
    title: str = Field(index=True)
    description: str = Field(default="")
    project_id: Optional[str] = Field(default=None, foreign_key="creative_projects.id", index=True, max_length=80)
    document_json: dict = Field(default_factory=dict, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
