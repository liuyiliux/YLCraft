"""Persistent records for resumable creative-project tasks."""

from __future__ import annotations

import time
from typing import Optional

from sqlmodel import Field, SQLModel


class ProjectTaskRecord(SQLModel, table=True):
    """Durable index for project-scoped async image tasks.

    The in-memory queue remains the execution cache. This table only keeps the
    task context needed to resume polling after an API process restart.
    """

    __tablename__ = "project_task_records"

    task_id: str = Field(primary_key=True, max_length=64)
    task_type: str = Field(default="", index=True, max_length=80)
    status: str = Field(default="pending", index=True, max_length=32)
    payload_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    error: Optional[str] = Field(default=None)
    progress: int = Field(default=0)
    progress_message: str = Field(default="")
    created_at: float = Field(default_factory=time.time, index=True)
    started_at: Optional[float] = Field(default=None)
    completed_at: Optional[float] = Field(default=None)
    max_retries: int = Field(default=0)
    events_json: str = Field(default="[]")
    updated_at: float = Field(default_factory=time.time, index=True)


class VideoGenerationTask(SQLModel, table=True):
    """Durable task ledger for the standalone AI video workspace.

    Provider task ids are not enough to restore a video job: the prompt,
    selected model, source assets and optional project lineage are also needed
    to import a completed file into Asset Hub after a page or API restart.
    """

    __tablename__ = "video_generation_tasks"

    task_id: str = Field(primary_key=True, max_length=128)
    provider: str = Field(default="", index=True, max_length=120)
    model: str = Field(default="", max_length=160)
    status: str = Field(default="pending", index=True, max_length=32)
    prompt: str = Field(default="")
    request_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    asset_id: Optional[str] = Field(default=None, index=True, max_length=64)
    project_id: Optional[str] = Field(default=None, index=True, max_length=64)
    content_id: Optional[str] = Field(default=None, index=True, max_length=64)
    error: Optional[str] = Field(default=None)
    progress: int = Field(default=0)
    progress_message: str = Field(default="")
    created_at: float = Field(default_factory=time.time, index=True)
    completed_at: Optional[float] = Field(default=None)
    updated_at: float = Field(default_factory=time.time, index=True)


class Model3DGenerationTask(SQLModel, table=True):
    """Durable provider task and Asset Hub import state for image-to-3D."""

    __tablename__ = "model3d_generation_tasks"

    task_id: str = Field(primary_key=True, max_length=128)
    provider: str = Field(default="", index=True, max_length=120)
    model: str = Field(default="", max_length=160)
    status: str = Field(default="pending", index=True, max_length=32)
    prompt: str = Field(default="")
    request_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    asset_id: Optional[str] = Field(default=None, index=True, max_length=64)
    error: Optional[str] = Field(default=None)
    progress: int = Field(default=0)
    progress_message: str = Field(default="")
    created_at: float = Field(default_factory=time.time, index=True)
    completed_at: Optional[float] = Field(default=None)
    updated_at: float = Field(default_factory=time.time, index=True)
