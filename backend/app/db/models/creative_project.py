"""
YLCraft — 创作项目闭环模型

用于承载小说、短剧、漫画等连续创作项目。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Index
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


class ProjectPublishRecord(SQLModel, table=True):
    """创作项目 → 番茄小说 发布映射记录。

    一条记录对应一次「将某章 novel_body 正文推送到番茄某章节」的操作。
    关键用途：
      - 记录 章节(content_id) ↔ 番茄 item_id / latest_version 的映射，防止重复覆盖。
      - 前端展示每章的发布状态（草稿/已发布/失败）与远程版本号。
    约定：番茄的建书 / 建卷 / 建章节不在 YLCraft 内完成，item_id 由用户在
    番茄 Web 端新建章节后填入。
    """

    __tablename__ = "project_publish_records"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    content_id: str | None = Field(default=None, foreign_key="project_contents.id", index=True)

    conn_id: str = Field(default="", description="使用的 PlatformConnection ID")
    book_id: str = Field(default="", index=True)
    item_id: str = Field(default="", index=True)
    volume_id: str = Field(default="")
    volume_name: str = Field(default="")

    chapter_number: int | None = Field(default=None, index=True)
    action: str = Field(default="draft", description="draft=保存番茄草稿（当前唯一支持动作）")
    remote_version: int | None = Field(default=None, description="番茄返回的 latest_version")
    post_url: str = Field(default="", description="远程章节 URL（若可获取）")

    status: str = Field(default="pending", index=True, description="pending/success/failed")
    error_message: str = Field(default="")

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)


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


class ContinuityCandidateStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    IGNORED = "ignored"
    MERGED = "merged"
    SUPERSEDED = "superseded"


class ContinuityCandidateSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CONFLICT = "conflict"


class ContinuityEntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    EVENT = "event"
    TIMELINE = "timeline"
    RELATIONSHIP = "relationship"
    FORESHADOW = "foreshadow"
    WORLD_RULE = "world_rule"
    OTHER = "other"


class ContinuitySuggestedAction(str, Enum):
    CREATE_FACT = "create_fact"
    UPDATE_FACT = "update_fact"
    RESOLVE_CONFLICT = "resolve_conflict"
    REWRITE_EXCERPT = "rewrite_excerpt"
    IGNORE = "ignore"


class ContinuityFactTargetType(str, Enum):
    PROJECT_BIBLE = "project_bible"
    WORLD_ASSET = "world_asset"


class ProjectContinuityCandidate(SQLModel, table=True):
    """Writer Room / 审稿提取的连续性事实候选。

    候选是带来源（source_content_id, source_generation_log_id）的提案，
    而不是已接受的事实；用户 accept / merge 后才进入
    project_bible / world_asset，并进入下一轮 context pack。

    去重维度：`project_id` + `source_kind` + `source_fingerprint`
    （fingerprint 是 project_id + content_id + kind + excerpt_hash 的源感知哈希）。
    """

    __tablename__ = "project_continuity_candidates"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    source_content_id: str | None = Field(
        default=None, foreign_key="project_contents.id", index=True
    )
    source_generation_log_id: str | None = Field(
        default=None, foreign_key="project_generation_logs.id", index=True
    )

    # 来源标记，用于审计和 dedupe
    source_kind: str = Field(default="prose_review", index=True)
    source_fingerprint: str = Field(default="", index=True)

    # 候选事实字段（对齐 design.md contract）
    entity_type: str = Field(default=ContinuityEntityType.OTHER.value, index=True)
    entity_name: str = Field(default="")
    claim: str = Field(default="")
    evidence_excerpt: str = Field(default="")  # 有界证据摘要，原文保留在 source_content_id
    evidence_anchor_json: str = Field(default="{}")

    severity: str = Field(default=ContinuityCandidateSeverity.INFO.value, index=True)
    suggested_action: str = Field(
        default=ContinuitySuggestedAction.CREATE_FACT.value, index=True
    )
    target_fact_type: str = Field(
        default=ContinuityFactTargetType.WORLD_ASSET.value, index=True
    )

    # 决策状态
    status: str = Field(
        default=ContinuityCandidateStatus.PENDING.value, index=True
    )
    resolved_fact_id: str | None = Field(default=None, index=True)
    resolution_note: str = Field(default="")
    resolved_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Narrative runtime
#
# These tables are derived, project-local narrative state.  They never replace
# approved `novel_body` prose, locked project facts or pending continuity
# candidates.  Every record points back to the exact approved content version
# from which it was produced so a later promotion can supersede, not erase, it.
# ---------------------------------------------------------------------------


class NarrativeSnapshotStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class NarrativeEvidenceStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"
    SUPERSEDED = "superseded"


class ForeshadowingStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    ADVANCED = "advanced"
    RESOLVED = "resolved"
    OVERDUE = "overdue"
    IGNORED = "ignored"
    SUPERSEDED = "superseded"


class NarrativeRunMode(str, Enum):
    MANUAL = "manual"
    BATCH = "batch"
    GUARDED_AUTOPILOT = "guarded_autopilot"


class NarrativeRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProjectNarrativeRun(SQLModel, table=True):
    """Durable manual/batch/autopilot execution record for one project."""

    __tablename__ = "project_narrative_runs"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    mode: str = Field(default=NarrativeRunMode.MANUAL.value, index=True)
    status: str = Field(default=NarrativeRunStatus.PENDING.value, index=True)
    pipeline_version: str = Field(default="v1", index=True)

    target_chapters_json: str = Field(default="[]")
    input_json: str = Field(default="{}")
    trace_json: str = Field(default="[]")
    context_snapshot_ids_json: str = Field(default="[]")

    current_cursor: int = Field(default=0)
    retry_count: int = Field(default=0)
    token_usage: int = Field(default=0)
    cost_amount: float = Field(default=0.0)
    error_message: str = Field(default="")

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)


class ProjectNarrativeContextSnapshot(SQLModel, table=True):
    """The exact bounded context assembled before a creative generation call.

    This is intentionally separate from :class:`ProjectNarrativeSnapshot`:
    the latter is state extracted *from* approved prose, while this record is
    the auditable input assembled *for* a generation.  It must only contain
    canonical or explicitly allowed sources.
    """

    __tablename__ = "project_narrative_context_snapshots"
    __table_args__ = (
        Index("ix_pncs_project_chapter_created", "project_id", "chapter_number", "created_at"),
        Index("ix_pncs_project_fingerprint", "project_id", "fingerprint"),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    chapter_number: int = Field(index=True)
    stage: str = Field(default="", index=True)
    source_content_id: str | None = Field(default=None, foreign_key="project_contents.id", index=True)
    narrative_run_id: str | None = Field(
        default=None, foreign_key="project_narrative_runs.id", index=True
    )

    context_text: str = Field(default="")
    layers_json: str = Field(default="[]")
    included_sources_json: str = Field(default="[]")
    excluded_sources_json: str = Field(default="{}")
    budget_json: str = Field(default="{}")
    applied_skill_ids_json: str = Field(default="[]")
    overflow_json: str = Field(default="[]")
    fingerprint: str = Field(default="", index=True)

    created_at: datetime = Field(default_factory=datetime.now, index=True)


class ProjectNarrativeSnapshot(SQLModel, table=True):
    """Bounded narrative state extracted from one approved prose version."""

    __tablename__ = "project_narrative_snapshots"
    __table_args__ = (
        Index(
            "ux_pns_source_pipeline",
            "source_content_id",
            "source_fingerprint",
            "pipeline_version",
            unique=True,
        ),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    source_content_id: str = Field(foreign_key="project_contents.id", index=True)
    source_version: int = Field(default=1, index=True)
    chapter_number: int = Field(index=True)
    run_id: str | None = Field(default=None, foreign_key="project_narrative_runs.id", index=True)
    pipeline_version: str = Field(default="v1", index=True)
    source_fingerprint: str = Field(default="", index=True)
    status: str = Field(default=NarrativeSnapshotStatus.SUCCESS.value, index=True)

    summary: str = Field(default="")
    character_state_json: str = Field(default="[]")
    timeline_delta_json: str = Field(default="[]")
    location_delta_json: str = Field(default="[]")
    open_questions_json: str = Field(default="[]")
    diagnostics_json: str = Field(default="{}")
    context_fingerprint: str = Field(default="", index=True)

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)


class ProjectStoryEvent(SQLModel, table=True):
    """A source-backed event for the project narrative graph and context pack."""

    __tablename__ = "project_story_events"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    snapshot_id: str | None = Field(default=None, foreign_key="project_narrative_snapshots.id", index=True)
    source_content_id: str = Field(foreign_key="project_contents.id", index=True)
    source_version: int = Field(default=1, index=True)
    chapter_number: int = Field(index=True)
    run_id: str | None = Field(default=None, foreign_key="project_narrative_runs.id", index=True)
    source_fingerprint: str = Field(default="", index=True)
    status: str = Field(default=NarrativeEvidenceStatus.PENDING_REVIEW.value, index=True)

    event_type: str = Field(default="event", index=True)
    title: str = Field(default="")
    description: str = Field(default="")
    participants_json: str = Field(default="[]")
    location: str = Field(default="", index=True)
    timeline_order: int | None = Field(default=None, index=True)
    evidence_anchor_json: str = Field(default="{}")

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)


class ProjectForeshadowing(SQLModel, table=True):
    """A reviewable foreshadowing ledger record with source evidence."""

    __tablename__ = "project_foreshadowing"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    snapshot_id: str | None = Field(default=None, foreign_key="project_narrative_snapshots.id", index=True)
    source_content_id: str = Field(foreign_key="project_contents.id", index=True)
    source_version: int = Field(default=1, index=True)
    chapter_number: int = Field(index=True)
    run_id: str | None = Field(default=None, foreign_key="project_narrative_runs.id", index=True)
    source_fingerprint: str = Field(default="", index=True)

    kind: str = Field(default="clue", index=True)
    statement: str = Field(default="")
    planted_chapter: int = Field(index=True)
    expected_window_json: str = Field(default="{}")
    status: str = Field(default=ForeshadowingStatus.PENDING_REVIEW.value, index=True)
    evidence_anchor_json: str = Field(default="{}")
    resolution_note: str = Field(default="")

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)


class ProjectStyleMeasurement(SQLModel, table=True):
    """Measured style evidence; a baseline is chosen later by the user."""

    __tablename__ = "project_style_measurements"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    source_content_id: str = Field(foreign_key="project_contents.id", index=True)
    source_version: int = Field(default=1, index=True)
    chapter_number: int = Field(index=True)
    run_id: str | None = Field(default=None, foreign_key="project_narrative_runs.id", index=True)
    source_fingerprint: str = Field(default="", index=True)
    status: str = Field(default=NarrativeSnapshotStatus.SUCCESS.value, index=True)

    measurement_json: str = Field(default="{}")
    style_fingerprint: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)
