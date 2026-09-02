"""
YLCraft — 小说源资产与世界提取模型

承载「来源快照 → 章节 → 文本块 → 提取运行 → 世界候选」的统一链路。

设计约束（见 openspec/changes/novel-source-world-project/specs/novel-world-project/design.md）：

- 来源快照只读：TXT 导入和书架章节导入都归一到同一份快照契约，原文件与校验和保留。
- 章节和文本块保存相对于整篇正文的稳定字符偏移，证据锚点必须能定位回具体位置。
- 提取运行按域推进，单个域失败不影响其他域。
- 候选是待确认层：只有 accept 之后才写入项目事实（world_asset / Character）。
- 增量扩展只追加新证据和新设定，不重建整套世界；运行记录 checkpoint 游标。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


class SourceKind(str, Enum):
    """来源类型。"""

    TXT = "txt"
    BOOKSHELF = "bookshelf"


class SourceStatus(str, Enum):
    """来源完本状态。连载来源允许追加快照修订，完本来源默认稳定。"""

    COMPLETED = "completed"
    SERIAL = "serial"
    UNKNOWN = "unknown"


class DerivationKind(str, Enum):
    """完本来源的派生模式。派生项目复用原作正典作为只读参考层。"""

    ADAPTATION = "adaptation"
    CONTINUATION = "continuation"
    FAN_WORK = "fan_work"


DERIVATION_LABELS = {
    DerivationKind.ADAPTATION.value: "改编",
    DerivationKind.CONTINUATION.value: "续写",
    DerivationKind.FAN_WORK.value: "同人",
}


class SnapshotIndexingStatus(str, Enum):
    """文本块与向量索引状态。向量索引失败时降级为精确/顺序检索。"""

    PENDING = "pending"
    INDEXED = "indexed"
    SKIPPED = "skipped"
    FAILED = "failed"


class ExtractionRunKind(str, Enum):
    """运行种类：从原文提取 vs 无原文的 AI 生成。

    两者共用同一张运行表与游标/诊断机制（Decision D-3），只在语义上隔离：
    生成运行不产出证据，候选统一标记 ``ai_draft``。
    """

    EXTRACT = "extract"
    GENERATE = "generate"


class ExtractionRunMode(str, Enum):
    FULL = "full"
    DELTA = "delta"


class ExtractionRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DomainDetectionState(str, Enum):
    """AI 对单个世界模块的检测结论。

    刻意不使用整体题材开关（如「都市/玄幻」）：每个模块独立判断，
    用户或 Agent 可以单独接受、修改或关闭。
    """

    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    UNCERTAIN = "uncertain"
    USER_REQUESTED = "user_requested"


class DomainRunState(str, Enum):
    """模块在一次提取运行中的执行状态。"""

    DISABLED = "disabled"
    NOT_APPLICABLE = "not_applicable"
    ENABLED = "enabled"
    EXTRACTING = "extracting"
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class CandidateStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    IGNORED = "ignored"
    MERGED = "merged"


class CandidateOrigin(str, Enum):
    """字段来源：原文直接陈述 vs 模型推断 vs 无原文的 AI 创作。

    与角色库的字段来源语义保持一致，推断内容必须显式标记并进入候选。
    ``ai_draft`` 来自生成链路（没有原文可引用）：**不得为其伪造证据锚点**，
    UI 需与「原文可考」（``original``）明确区分。
    """

    ORIGINAL = "original"
    AI_INFERRED = "ai_inferred"
    AI_DRAFT = "ai_draft"


class NovelSourceSnapshot(SQLModel, table=True):
    """一份只读来源快照。

    TXT 导入或书架章节导入的产物。同一来源的后续同步通过
    ``parent_snapshot_id`` + ``revision`` 追加修订，而不是覆盖原快照；
    原作设定始终只读。
    """

    __tablename__ = "novel_source_snapshots"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    title: str = Field(default="", index=True)
    author: str = Field(default="")

    source_kind: str = Field(default=SourceKind.TXT.value, index=True)
    source_status: str = Field(default=SourceStatus.UNKNOWN.value, index=True)

    project_id: str | None = Field(
        default=None, foreign_key="creative_projects.id", index=True
    )
    source_asset_id: str | None = Field(default=None, index=True)

    original_file_path: str = Field(default="")
    checksum: str = Field(default="", index=True)
    encoding: str = Field(default="utf-8")

    revision: int = Field(default=1)
    parent_snapshot_id: str | None = Field(default=None, index=True)

    chapter_count: int = Field(default=0)
    char_count: int = Field(default=0)
    # 连载来源的处理进度游标：已导入的最后一章序号。
    last_chapter_ordinal: int = Field(default=0)
    indexing_status: str = Field(default=SnapshotIndexingStatus.PENDING.value, index=True)

    metadata_json: str = Field(default="{}")

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class NovelSourceChapter(SQLModel, table=True):
    """快照内的章节，保存相对整篇正文的稳定字符区间。"""

    __tablename__ = "novel_source_chapters"
    __table_args__ = (
        Index("ix_novel_source_chapters_snapshot_ordinal", "snapshot_id", "ordinal"),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    snapshot_id: str = Field(foreign_key="novel_source_snapshots.id", index=True)

    ordinal: int = Field(index=True)
    title: str = Field(default="", index=True)

    start_offset: int = Field(default=0)
    end_offset: int = Field(default=0)
    char_count: int = Field(default=0)

    # 书架来源对应的 NovelChapter 记录，TXT 来源为空。
    source_chapter_id: str | None = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=datetime.now, index=True)


class NovelTextChunk(SQLModel, table=True):
    """提取与检索的最小文本单元。

    向量索引只是召回加速器，不是正典写入者；每条证据都必须能指回
    具体 chunk 及字符偏移。
    """

    __tablename__ = "novel_text_chunks"
    __table_args__ = (
        Index("ix_novel_text_chunks_snapshot_ordinal", "snapshot_id", "ordinal"),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    snapshot_id: str = Field(foreign_key="novel_source_snapshots.id", index=True)
    chapter_id: str | None = Field(
        default=None, foreign_key="novel_source_chapters.id", index=True
    )

    ordinal: int = Field(index=True)
    start_offset: int = Field(default=0)
    end_offset: int = Field(default=0)

    content: str = Field(default="")
    content_hash: str = Field(default="", index=True)
    metadata_json: str = Field(default="{}")

    # 向量是可选的召回加速层，不参与证据正典判断。按块记录模型和维度，
    # 避免把不同 embedding provider 强行塞进固定维度的资产向量表。
    embedding_json: str = Field(default="")
    embedding_model: str = Field(default="", index=True)
    embedding_status: str = Field(default="pending", index=True)

    created_at: datetime = Field(default_factory=datetime.now, index=True)


class WorldExtractionRun(SQLModel, table=True):
    """一次世界提取运行。

    按域记录检测结果、状态、进度和诊断，任一域失败只让整体变
    ``partial``，不回滚其他域已产生的候选。
    """

    __tablename__ = "world_extraction_runs"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    snapshot_id: str = Field(foreign_key="novel_source_snapshots.id", index=True)
    project_id: str | None = Field(
        default=None, foreign_key="creative_projects.id", index=True
    )

    # extract=从原文提取（有证据）；generate=无原文的 AI 生成（候选标记 ai_draft）
    kind: str = Field(default=ExtractionRunKind.EXTRACT.value, index=True)
    mode: str = Field(default=ExtractionRunMode.FULL.value, index=True)
    status: str = Field(default=ExtractionRunStatus.PENDING.value, index=True)
    pipeline_version: str = Field(default="v1", index=True)

    # 每域：{domain, detection, run_state, reason, signals, estimated_cost, items, error}
    domains_json: str = Field(default="[]")
    # 增量游标：{last_chunk_ordinal, last_chapter_ordinal}
    checkpoint_json: str = Field(default="{}")
    trace_json: str = Field(default="[]")
    diagnostics_json: str = Field(default="{}")

    provider: str = Field(default="")
    model: str = Field(default="")
    token_usage: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class WorldFactCandidate(SQLModel, table=True):
    """待确认的世界事实候选。

    只有歧义、冲突或推断内容才需要进入候选；直接陈述的高置信事实以
    ``origin=original`` 记录并仍需确认后才写入项目事实。
    """

    __tablename__ = "world_fact_candidates"
    __table_args__ = (
        Index("ix_world_fact_candidates_snapshot_domain", "snapshot_id", "domain"),
        Index("ix_world_fact_candidates_run_status", "run_id", "status"),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    run_id: str = Field(foreign_key="world_extraction_runs.id", index=True)
    snapshot_id: str = Field(foreign_key="novel_source_snapshots.id", index=True)
    project_id: str | None = Field(
        default=None, foreign_key="creative_projects.id", index=True
    )

    domain: str = Field(index=True)
    entity_name: str = Field(default="", index=True)
    normalized_key: str = Field(default="", index=True)
    # 去重维度：snapshot + domain + 规范化名。
    fingerprint: str = Field(default="", index=True)

    payload_json: str = Field(default="{}")
    evidence_json: str = Field(default="[]")
    confidence: float = Field(default=0.0)
    origin: str = Field(default=CandidateOrigin.AI_INFERRED.value, index=True)

    status: str = Field(default=CandidateStatus.PENDING.value, index=True)
    # 最近一次产出或更新该候选的运行；增量提取追加证据时回写，
    # 便于审阅界面把「本次运行产生或更新」的候选一起列出来。
    last_run_id: str | None = Field(default=None, index=True)
    target_entity_type: str = Field(default="")
    target_entity_id: str | None = Field(default=None, index=True)
    review_note: str = Field(default="")
    resolved_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class WorldMapDocument(SQLModel, table=True):
    """结构化世界地图文档。

    地图是可独立编辑的结构化空间关系，不并入通用的 ``world_asset`` 事实卡：
    区域（region）、据点（node）、路线（route）分别承载层级、位置与连通关系，
    ``map_json`` 保存其结构化数据，``revision`` 用于并发保护（CAS）。
    """

    __tablename__ = "world_map_documents"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str | None = Field(
        default=None, foreign_key="creative_projects.id", index=True
    )
    snapshot_id: str | None = Field(
        default=None, foreign_key="novel_source_snapshots.id", index=True
    )

    title: str = Field(default="世界地图", index=True)
    map_json: str = Field(default="{}")
    revision: int = Field(default=1)

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)


class WorldEntity(SQLModel, table=True):
    """独立世界实体层：把已确认候选物化为类型化实体，供关系图谱与结构化查询。

    与通用 ``world_asset`` 事实卡并存：事实卡仍是锁定正典的权威载体，本表是
    同一事实的稳定实体身份 + 可建立类型化关系的结构化索引。角色域复用
    ``Character``/``CharacterStoryLink``/``CharacterRelationship``，不在本表重复。
    """

    __tablename__ = "world_entities"
    __table_args__ = (
        Index("ix_world_entities_project_type", "project_id", "entity_type"),
        Index(
            "ux_world_entities_project_type_key",
            "project_id",
            "entity_type",
            "normalized_key",
            unique=True,
        ),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    snapshot_id: str | None = Field(
        default=None, foreign_key="novel_source_snapshots.id", index=True
    )

    domain: str = Field(index=True)
    entity_type: str = Field(index=True)
    name: str = Field(default="", index=True)
    normalized_key: str = Field(default="", index=True)
    summary: str = Field(default="")

    attributes_json: str = Field(default="{}")
    evidence_json: str = Field(default="[]")

    # source_canon=原作正典（派生项目中的只读层）；project=本项目设定。
    fact_layer: str = Field(default="project", index=True)
    source_candidate_id: str | None = Field(default=None, index=True)
    is_locked: bool = Field(default=True, index=True)

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)


class WorldEntityRelation(SQLModel, table=True):
    """世界实体之间的类型化关系（复杂实体间，不涉及角色）。

    从候选 payload 的显式关系字段（势力敌对/地盘、事件发生地、物种栖息地等）
    物化而来，也可由真人/Agent 直接增删。不承载事实权威，仅用于关系图谱与检索；
    涉及角色的关系由 ``CharacterRelationship`` 承载。
    """

    __tablename__ = "world_entity_relations"
    __table_args__ = (
        Index("ix_world_entity_relations_project", "project_id"),
        Index("ix_world_entity_relations_source", "source_entity_id"),
        Index("ix_world_entity_relations_target", "target_entity_id"),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)
    source_entity_id: str = Field(foreign_key="world_entities.id", index=True)
    target_entity_id: str = Field(foreign_key="world_entities.id", index=True)
    relation_type: str = Field(default="", index=True)
    note: str = Field(default="")
    evidence_json: str = Field(default="[]")
    is_directed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class DomainDefinitionSource(str, Enum):
    """世界模块定义的来源。

    ``builtin_override`` 覆盖内置域；``custom`` 用户新建；``ai_suggested`` 由 AI 在
    生成/补充时建议，默认不启用，需用户确认后转为 ``custom``。
    """

    BUILTIN_OVERRIDE = "builtin_override"
    CUSTOM = "custom"
    AI_SUGGESTED = "ai_suggested"


class WorldDomainDefinition(SQLModel, table=True):
    """项目级世界模块定义：覆盖内置域，或新增自定义域。

    内置域（``contracts.DOMAIN_SPECS``）提供稳定默认值；每个项目在此基础上可以：

    - 覆盖 ``label`` / ``prompt_hint``（留空表示沿用内置）
    - 在内置属性之外**追加**字段（内置字段不可删除，只能扩展，保证既有数据可解析）
    - 禁用某个内置域（``is_enabled=False``）
    - 新增自定义域（赛博朋克的「义体改造」、修仙的「灵脉品级」等）

    自定义域的实体仍写入 ``world_entities``，``entity_type`` 取本表值（空则用 domain_key），
    因此新增域不需要任何新表。
    """

    __tablename__ = "world_domain_definitions"
    __table_args__ = (
        UniqueConstraint("project_id", "domain_key", name="ux_world_domain_definitions_project_key"),
        Index("ix_world_domain_definitions_project_source", "project_id", "source"),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    project_id: str = Field(foreign_key="creative_projects.id", index=True)

    domain_key: str = Field(index=True)
    label: str = Field(default="")  # 覆盖内置展示名；空表示沿用
    entity_type: str = Field(default="")  # 自定义域的实体类型；空表示用 domain_key
    # 相对内置属性**追加**的字段；内置字段不可删除，只能扩展。
    extra_attributes_json: str = Field(default="[]")
    prompt_hint: str = Field(default="")  # 覆盖内置提取提示；空表示沿用
    is_enabled: bool = Field(default=True, index=True)
    source: str = Field(default=DomainDefinitionSource.CUSTOM.value, index=True)

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)


class WorldBuildingTemplate(SQLModel, table=True):
    """项目级世界构建模板：层次策略 + 每档提示词，全部可编辑。

    层次（layers）由项目决定：叫「世界/大陆/国家/城市」还是别的、有几层、
    甚至完全不分层都由数据决定，**不写死枚举**。内置模板（``is_builtin``）
    作为种子提供起点，项目可复制后修改；``project_id`` 为空即内置模板。
    """

    __tablename__ = "world_building_templates"
    __table_args__ = (
        Index("ix_world_building_templates_project_default", "project_id", "is_default"),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    # 空表示内置种子模板，非空为项目私有模板。
    project_id: str | None = Field(
        default=None, foreign_key="creative_projects.id", index=True
    )

    name: str = Field(default="")
    # 层次策略，如 ["世界", "大陆", "国家", "地区", "地点"]
    layers_json: str = Field(default="[]")
    # 每档提示词：{draft_world, expand_domain, expand_entity}
    prompts_json: str = Field(default="{}")

    is_default: bool = Field(default=False, index=True)  # 项目默认使用的模板
    is_builtin: bool = Field(default=False, index=True)  # 内置种子模板（只读语义）

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)
