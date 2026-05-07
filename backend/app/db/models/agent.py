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

class AgentMemoryBase(SQLModel):
    user_id: str = Field(default="default", max_length=64)
    key: str = Field(max_length=100)
    value: str = Field(sa_column=Column(Text))
    memory_type: str = Field(max_length=50)   # preference / project_context / fact
    importance: int = Field(default=5, ge=1, le=10)


class AgentMemory(AgentMemoryBase, table=True):
    __tablename__ = "agent_memories"

    id: int = Field(primary_key=True, default=None)
    session_id: Optional[str] = Field(default=None, foreign_key="agent_sessions.id", max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    access_count: int = Field(default=0)

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
# 导出（让 init_db 能发现）
# =============================================================================

AgentSession, AgentMemory, AgentSkill, AgentToolCall
