"""
YLCraft — Agent 数据库模型

三层记忆架构：
1. AgentSession   — 短期记忆（每次对话的上下文）
2. AgentMemory    — 中期记忆（跨会话的关键信息）
3. AgentSkill     — 长期记忆（沉淀的技能/工具）
"""

from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, Column, Text, ForeignKey
from typing import Optional, List


# =============================================================================
# Agent 会话表 — 短期记忆
# =============================================================================

class AgentSessionBase(SQLModel):
    user_id: str = Field(default="default", max_length=64)
    title: str = Field(default="", max_length=200)
    messages: str = Field(sa_column=Column(Text))   # JSON 字符串
    context: str = Field(default="{}", sa_column=Column(Text))  # JSON 字符串


class AgentSession(AgentSessionBase, table=True):
    __tablename__ = "agent_sessions"

    id: str = Field(primary_key=True, max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_archived: bool = Field(default=False)

    # 关系定义（使用类型注解）
    memories: List["AgentMemory"] = Relationship(back_populates="session")
    skills: List["AgentSkill"] = Relationship(back_populates="session")


class AgentSessionCreate(AgentSessionBase):
    pass


class AgentSessionRead(AgentSessionBase):
    id: str
    created_at: datetime
    updated_at: datetime
    is_archived: bool


# =============================================================================
# Agent 记忆表 — 中期记忆（跨会话沉淀）
# =============================================================================

class AgentThreadBase(SQLModel):
    user_id: str = Field(default="default", max_length=64, index=True)
    title: str = Field(default="", max_length=200)
    status: str = Field(default="active", max_length=32, index=True)
    active_profile_id: str = Field(default="", max_length=64, index=True)
    metadata_json: str = Field(default="{}", sa_column=Column(Text))


class AgentThread(AgentThreadBase, table=True):
    __tablename__ = "agent_threads"

    id: str = Field(primary_key=True, max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    archived_at: Optional[datetime] = Field(default=None)


class AgentMessageBase(SQLModel):
    thread_id: str = Field(max_length=64, foreign_key="agent_threads.id", index=True)
    run_id: str = Field(default="", max_length=64, index=True)
    role: str = Field(max_length=32, index=True)
    content: str = Field(default="", sa_column=Column(Text))
    content_json: str = Field(default="{}", sa_column=Column(Text))
    tool_call_id: str = Field(default="", max_length=120, index=True)
    metadata_json: str = Field(default="{}", sa_column=Column(Text))


class AgentMessage(AgentMessageBase, table=True):
    __tablename__ = "agent_messages"

    id: int = Field(primary_key=True, default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class AgentContextSnapshotBase(SQLModel):
    thread_id: str = Field(max_length=64, foreign_key="agent_threads.id", index=True)
    run_id: str = Field(default="", max_length=64, index=True)
    kind: str = Field(default="planning", max_length=64, index=True)
    context_json: str = Field(default="{}", sa_column=Column(Text))
    summary: str = Field(default="", sa_column=Column(Text))
    token_estimate: int = Field(default=0)


class AgentContextSnapshot(AgentContextSnapshotBase, table=True):
    __tablename__ = "agent_context_snapshots"

    id: int = Field(primary_key=True, default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class AgentMemoryBase(SQLModel):
    user_id: str = Field(default="default", max_length=64)
    key: str = Field(max_length=100)
    value: str = Field(sa_column=Column(Text))
    memory_type: str = Field(max_length=50)   # preference / project_context / fact
    status: str = Field(default="pending", max_length=32)  # Hermes: pending / confirmed / rejected
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)  # DeerFlow-inspired: fact confidence score
    # Provenance tracking (memory provenance)
    thread_id: Optional[str] = Field(default=None, max_length=64, index=True)
    run_id: Optional[str] = Field(default=None, max_length=64, index=True)
    message_ids: Optional[str] = Field(default=None, sa_column=Column(Text))  # JSON array of message IDs that contributed


class AgentMemory(AgentMemoryBase, table=True):
    __tablename__ = "agent_memories"

    id: int = Field(primary_key=True, default=None)
    session_id: Optional[str] = Field(default=None, foreign_key="agent_sessions.id", max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    access_count: int = Field(default=0)
    source: Optional[str] = Field(default=None, max_length=100)  # DeerFlow: fact provenance tracking

    # 关系定义（使用类型注解）
    session: Optional["AgentSession"] = Relationship(back_populates="memories")


class AgentMemoryCreate(AgentMemoryBase):
    pass


class AgentMemoryRead(AgentMemoryBase):
    id: int
    created_at: datetime
    updated_at: datetime
    access_count: int


# =============================================================================
# Agent 技能表 — 长期记忆（自动创建的 Skill，Hermes 核心思想）
# =============================================================================

class AgentSkillBase(SQLModel):
    user_id: str = Field(default="default", max_length=64)
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    skill_type: str = Field(default="tool", max_length=50)  # tool / workflow / prompt
    content: str = Field(sa_column=Column(Text))
    version: int = Field(default=1)
    is_builtin: bool = Field(default=False)


class AgentSkill(AgentSkillBase, table=True):
    __tablename__ = "agent_skills"

    id: int = Field(primary_key=True, default=None)
    session_id: Optional[str] = Field(default=None, foreign_key="agent_sessions.id", max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    usage_count: int = Field(default=0)
    success_count: int = Field(default=0)

    # 关系定义（使用类型注解）
    session: Optional["AgentSession"] = Relationship(back_populates="skills")


class AgentSkillCreate(AgentSkillBase):
    pass


class AgentSkillRead(AgentSkillBase):
    id: int
    created_at: datetime
    updated_at: datetime
    usage_count: int
    success_count: int


class AgentSkillDraftBase(SQLModel):
    user_id: str = Field(default="default", max_length=64, index=True)
    name: str = Field(default="", max_length=100, index=True)
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=500)
    skill_type: str = Field(default="workflow", max_length=50)
    content: str = Field(default="", sa_column=Column(Text))
    metadata_json: str = Field(default="{}", sa_column=Column(Text))
    source_type: str = Field(default="manual", max_length=50, index=True)
    source_url: str = Field(default="", max_length=1000)
    source_run_id: str = Field(default="", max_length=64, index=True)
    source_step_ids_json: str = Field(default="[]", sa_column=Column(Text))
    status: str = Field(default="pending", max_length=32, index=True)
    target_path: str = Field(default="", max_length=1000)
    checksum: str = Field(default="", max_length=128)
    diagnostics_json: str = Field(default="[]", sa_column=Column(Text))


class AgentSkillDraft(AgentSkillDraftBase, table=True):
    __tablename__ = "agent_skill_drafts"

    id: int = Field(primary_key=True, default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = Field(default=None)


class AgentSkillDraftCreate(AgentSkillDraftBase):
    pass


class AgentSkillDraftRead(AgentSkillDraftBase):
    id: int
    created_at: datetime
    updated_at: datetime
    reviewed_at: Optional[datetime]


# =============================================================================
# Agent 工具调用日志
# =============================================================================

class AgentToolCallBase(SQLModel):
    session_id: str = Field(max_length=64)
    tool_name: str = Field(max_length=100)
    tool_args: str = Field(sa_column=Column(Text))
    result: Optional[str] = Field(default=None, sa_column=Column(Text))
    success: bool = Field(default=True)
    duration_ms: int = Field(default=0)


class AgentToolCall(AgentToolCallBase, table=True):
    __tablename__ = "agent_tool_calls"

    id: int = Field(primary_key=True, default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Agent 运行记录：可回放、可继续、可定位失败的执行态
# =============================================================================

class AgentRunBase(SQLModel):
    user_id: str = Field(default="default", max_length=64, index=True)
    session_id: str = Field(default="", max_length=64, index=True)
    profile_id: str = Field(default="", max_length=64, index=True)
    parent_run_id: Optional[str] = Field(default=None, max_length=64, index=True)
    status: str = Field(default="running", max_length=32, index=True)
    objective: str = Field(default="", sa_column=Column(Text))
    context_json: str = Field(default="{}", sa_column=Column(Text))
    result_json: str = Field(default="{}", sa_column=Column(Text))
    error: str = Field(default="", sa_column=Column(Text))


class AgentRun(AgentRunBase, table=True):
    __tablename__ = "agent_runs"

    id: str = Field(primary_key=True, max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = Field(default=None)


class AgentRunStepBase(SQLModel):
    run_id: str = Field(max_length=64, foreign_key="agent_runs.id", index=True)
    session_id: str = Field(default="", max_length=64, index=True)
    profile_id: str = Field(default="", max_length=64, index=True)
    step_type: str = Field(max_length=50, index=True)
    status: str = Field(default="completed", max_length=32, index=True)
    order_index: int = Field(default=0, index=True)
    tool_name: str = Field(default="", max_length=120, index=True)
    summary: str = Field(default="", sa_column=Column(Text))
    input_json: str = Field(default="{}", sa_column=Column(Text))
    output_json: str = Field(default="{}", sa_column=Column(Text))
    linked_objects_json: str = Field(default="[]", sa_column=Column(Text))
    error: str = Field(default="", sa_column=Column(Text))
    duration_ms: int = Field(default=0)


class AgentRunStep(AgentRunStepBase, table=True):
    __tablename__ = "agent_run_steps"

    id: int = Field(primary_key=True, default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Agent 记忆快照：每次 run 实际注入模型的 frozen context
# =============================================================================

class AgentMemorySnapshotBase(SQLModel):
    user_id: str = Field(default="default", max_length=64, index=True)
    run_id: str = Field(max_length=64, foreign_key="agent_runs.id", index=True)
    session_id: str = Field(default="", max_length=64, index=True)
    profile_id: str = Field(default="", max_length=64, index=True)
    memory_context: str = Field(default="", sa_column=Column(Text))
    context_summary: str = Field(default="", sa_column=Column(Text))
    tool_index_text: str = Field(default="", sa_column=Column(Text))
    snapshot_json: str = Field(default="{}", sa_column=Column(Text))


class AgentMemorySnapshot(AgentMemorySnapshotBase, table=True):
    __tablename__ = "agent_memory_snapshots"

    id: int = Field(primary_key=True, default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# 导出（让 init_db 能发现）
# =============================================================================

class AgentProfileBase(SQLModel):
    user_id: str = Field(default="default", max_length=64, index=True)
    name: str = Field(default="", max_length=100, index=True)
    description: str = Field(default="", max_length=500)
    avatar: str = Field(default="🤖", max_length=32)
    role_type: str = Field(default="assistant", max_length=64, index=True)
    system_prompt: str = Field(default="", sa_column=Column(Text))
    allowed_tools_json: str = Field(default="[]", sa_column=Column(Text))
    default_context_json: str = Field(default="{}", sa_column=Column(Text))
    default_project_id: str = Field(default="", max_length=64, index=True)
    default_workflow: str = Field(default="", max_length=120)
    default_skill_ids_json: str = Field(default="[]", sa_column=Column(Text))
    provider: str = Field(default="", max_length=120)
    model: str = Field(default="", max_length=160)
    max_steps: int = Field(default=8, ge=1, le=20)
    is_default: bool = Field(default=False, index=True)
    is_builtin: bool = Field(default=False, index=True)


class AgentProfile(AgentProfileBase, table=True):
    __tablename__ = "agent_profiles"

    id: str = Field(primary_key=True, max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentProfileCreate(AgentProfileBase):
    pass


class AgentProfileRead(AgentProfileBase):
    id: str
    created_at: datetime
    updated_at: datetime


AgentSession, AgentThread, AgentMessage, AgentContextSnapshot, AgentMemory, AgentSkill, AgentSkillDraft, AgentToolCall, AgentRun, AgentRunStep, AgentMemorySnapshot, AgentProfile
