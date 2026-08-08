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
