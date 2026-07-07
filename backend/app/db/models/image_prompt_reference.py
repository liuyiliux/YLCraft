"""Image prompt reference library persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ImagePromptSource(SQLModel, table=True):
    """A configured external source for image prompt examples."""

    __tablename__ = "image_prompt_sources"

    id: str = Field(primary_key=True, max_length=120)
    name: str = Field(index=True)
    repo_url: str = Field(default="")
    raw_base_url: str = Field(default="")
    raw_path: str = Field(default="README.md")
    parser: str = Field(default="markdown_sections", index=True)
    category: str = Field(default="", index=True)
    enabled: bool = Field(default=True, index=True)
    sync_status: str = Field(default="idle", index=True)
    last_synced_at: datetime | None = Field(default=None, index=True)
    error: str = Field(default="")
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class ImagePromptReference(SQLModel, table=True):
    """A normalized image prompt example synced from an external source."""

    __tablename__ = "image_prompt_references"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_image_prompt_references_source_external"),
    )

    id: str = Field(primary_key=True, max_length=160)
    source_id: str = Field(foreign_key="image_prompt_sources.id", index=True, max_length=120)
    external_id: str = Field(index=True, max_length=160)
    title: str = Field(index=True)
    prompt: str
    negative_prompt: str = Field(default="")
    cover_url: str = Field(default="")
    preview_markdown: str = Field(default="")
    tags_json: list[str] = Field(default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    category: str = Field(default="", index=True)
    source_url: str = Field(default="")
    model_hint: str = Field(default="")
    needs_reference_image: bool = Field(default=False, index=True)
    language: str = Field(default="", index=True)
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
