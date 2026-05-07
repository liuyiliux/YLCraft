"""
YLCraft — Agent 记忆管理器（三层记忆，参考 Hermes 思想）

L1 短期记忆：会话内 messages + context（SessionManager 管理）
L2 中期记忆：AgentMemory 表（跨会话，重要性排序，LRU 淘汰）
L3 长期记忆：AgentSkill 表（自动从复杂任务中沉淀为 Skill）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentMemory, AgentSkill

logger = logging.getLogger("ylcraft.agent.memory")


class MemoryManager:
    """三层记忆管理器"""

    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id

    # -----------------------------------------------------------------
    # L2 中期记忆（跨会话持久化关键信息）
    # -----------------------------------------------------------------

    async def save_memory(
        self,
        key: str,
        value: any,
        memory_type: str = "fact",
        importance: int = 5,
        session_id: Optional[str] = None,
    ) -> AgentMemory:
        """保存一条中期记忆"""
        # 检查是否已存在
        result = await self.session.execute(
            select(AgentMemory).where(
                AgentMemory.user_id == self.user_id,
                AgentMemory.key == key,
            )
        )
        existing = result.scalar_one_or_none()

        value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value

        if existing:
            existing.value = value_str
            existing.memory_type = memory_type
            existing.importance = importance
            existing.updated_at = datetime.utcnow()
            existing.access_count += 1
            await self.session.flush()
            return existing
        else:
            memory = AgentMemory(
                user_id=self.user_id,
                key=key,
                value=value_str,
                memory_type=memory_type,
                importance=importance,
                session_id=session_id,
            )
            self.session.add(memory)
            await self.session.flush()
            await self.session.refresh(memory)
            return memory

    async def get_memory(self, key: str) -> Optional[any]:
        """读取一条中期记忆"""
        result = await self.session.execute(
            select(AgentMemory).where(
                AgentMemory.user_id == self.user_id,
                AgentMemory.key == key,
            )
        )
        memory = result.scalar_one_or_none()
        if memory:
            memory.access_count += 1
            await self.session.flush()
            try:
                return json.loads(memory.value)
            except (json.JSONDecodeError, TypeError):
                return memory.value
        return None

    async def search_memories(self, query: str, limit: int = 10) -> list[AgentMemory]:
        """搜索中期记忆（简单关键词匹配）"""
        result = await self.session.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == self.user_id)
            .order_by(AgentMemory.importance.desc(), AgentMemory.access_count.desc())
            .limit(limit)
        )
        all_memories = result.scalars().all()
        # 简单过滤：key 或 value 包含 query
        return [
            m for m in all_memories
            if query.lower() in m.key.lower() or query.lower() in m.value.lower()
        ][:limit]

    async def get_all_memories(self) -> list[dict]:
        """获取所有中期记忆（组装成 LLM 可用的 system prompt 片段）"""
        result = await self.session.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == self.user_id)
            .order_by(AgentMemory.importance.desc())
        )
        memories = result.scalars().all()
        return [
            {
                "key": m.key,
                "value": m.value,
                "type": m.memory_type,
                "importance": m.importance,
            }
            for m in memories
        ]

    async def delete_memory(self, key: str) -> bool:
        """删除一条中期记忆"""
        result = await self.session.execute(
            select(AgentMemory).where(
                AgentMemory.user_id == self.user_id,
                AgentMemory.key == key,
            )
        )
        memory = result.scalar_one_or_none()
        if memory:
            await self.session.delete(memory)
            return True
        return False

    # -----------------------------------------------------------------
    # L3 长期记忆（自动沉淀的技能，Hermes 核心思想）
    # -----------------------------------------------------------------

    async def create_skill(
        self,
        name: str,
        description: str,
        content: str,
        skill_type: str = "tool",
        session_id: Optional[str] = None,
        is_builtin: bool = False,
    ) -> AgentSkill:
        """创建一条长期技能记忆（由 Agent 自动调用，沉淀复杂任务）"""
        skill = AgentSkill(
            user_id=self.user_id,
            name=name,
            description=description,
            skill_type=skill_type,
            content=content,
            session_id=session_id,
            is_builtin=is_builtin,
        )
        self.session.add(skill)
        await self.session.flush()
        await self.session.refresh(skill)
        logger.info(f"[Memory] Created skill: {name} (type={skill_type})")
        return skill

    async def find_skill(self, name: str) -> Optional[AgentSkill]:
        """查找技能"""
        result = await self.session.execute(
            select(AgentSkill).where(
                AgentSkill.user_id == self.user_id,
                AgentSkill.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_skills(self, skill_type: Optional[str] = None, min_usage: Optional[int] = None) -> list[AgentSkill]:
        """列出所有技能（按使用次数排序）"""
        query = select(AgentSkill).where(AgentSkill.user_id == self.user_id)
        if skill_type:
            query = query.where(AgentSkill.skill_type == skill_type)
        if min_usage is not None:
            query = query.where(AgentSkill.usage_count >= min_usage)
        query = query.order_by(AgentSkill.usage_count.desc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def increment_skill_usage(self, skill_id: int, success: bool = True) -> None:
        """增加技能使用次数（用于热度排序和可靠性评分）"""
        result = await self.session.execute(
            select(AgentSkill).where(AgentSkill.id == skill_id)
        )
        skill = result.scalar_one_or_none()
        if skill:
            skill.usage_count += 1
            if success:
                skill.success_count += 1
            await self.session.flush()

    # -----------------------------------------------------------------
    # 组装记忆上下文（供 AgentService 调用 LLM 时使用）
    # -----------------------------------------------------------------

    async def build_memory_context(self) -> str:
        """
        将 L2 + L3 记忆组装成文本，注入到 LLM 的 system prompt。
        这是 Hermes "记忆即上下文" 思想的核心实现。
        """
        parts = []

        # L2：中期记忆
        memories = await self.get_all_memories()
        if memories:
            parts.append("## 用户偏好和关键信息（中期记忆）")
            for m in memories:
                parts.append(f"- {m['key']}: {m['value']}")

        # L3：高频技能（使用次数 > 3 的）
        skills = await self.list_skills()
        active_skills = [s for s in skills if s.usage_count > 3]
        if active_skills:
            parts.append("\n## 已掌握的技能（长期记忆）")
            for s in active_skills[:10]:  # 最多 10 条
                parts.append(f"- {s.name}: {s.description}")

        return "\n".join(parts) if parts else ""
