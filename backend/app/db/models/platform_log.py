"""Unified platform event log for cross-scene observability."""

from __future__ import annotations

import time
from typing import Optional

from sqlmodel import Field, SQLModel


class PlatformEventLog(SQLModel, table=True):
    """Structured, cross-scene event ledger for AI generation and key system events.

    Unlike the resumable task ledgers (project_task_records / video_generation_tasks
    / model3d_generation_tasks), this table is a read-only audit stream: one row per
    generation call outcome (success / failed / pending), including failure details
    that were previously invisible for image generation.
    """

    __tablename__ = "platform_event_logs"

    id: str = Field(primary_key=True, max_length=64)
    scene: str = Field(default="", index=True, max_length=32)
    task_type: str = Field(default="", index=True, max_length=80)
    task_id: Optional[str] = Field(default=None, index=True, max_length=128)
    level: str = Field(default="info", index=True, max_length=16)
    status: str = Field(default="success", index=True, max_length=32)
    provider: str = Field(default="", max_length=160)
    model: str = Field(default="", max_length=160)
    message: str = Field(default="")
    error: Optional[str] = Field(default=None)
    request_summary: str = Field(default="")
    response_summary: str = Field(default="")
    duration_ms: int = Field(default=0)
    project_id: Optional[str] = Field(default=None, index=True, max_length=64)
    # 业务资源关联 ID（如 character_id / asset_node_id）。
    # 角色等非项目场景没有 project_id，需要按 ref_id 精确过滤出某一条资源的事件流。
    ref_id: Optional[str] = Field(default=None, index=True, max_length=64)
    retry_payload_json: str = Field(default="{}")
    retry_of: Optional[str] = Field(default=None, index=True, max_length=64)
    retried_by: Optional[str] = Field(default=None, index=True, max_length=64)
    created_at: float = Field(default_factory=time.time, index=True)
