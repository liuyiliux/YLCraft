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
from app.services.agent.skill_templates import ensure_builtin_skills

logger = logging.getLogger("ylcraft.agent.memory")


class MemoryManager:
    """三层记忆管理器（DeerFlow-inspired confidence scoring + token budget injection）"""

    # DeerFlow: facts with confidence < 0.7 are auto-filtered from context
    MIN_CONFIDENCE_FOR_CONTEXT = 0.7
    # DeerFlow: max token budget for memory context injection
    MAX_MEMORY_CONTEXT_TOKENS = 2000

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
        confidence: float = 1.0,
        source: Optional[str] = None,
        thread_id: Optional[str] = None,
        run_id: Optional[str] = None,
        message_ids: Optional[list[str]] = None,
    ) -> AgentMemory:
        """保存一条中期记忆（DeerFlow: 含置信度评分 + provenance 追踪）"""
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
            # Hermes: re-confirming bumps status to confirmed + boosts confidence
            existing.status = "confirmed"
            # DeerFlow pattern: re-confirming a fact boosts confidence
            existing.confidence = min(1.0, max(existing.confidence, confidence) + 0.1)
            existing.updated_at = datetime.utcnow()
            existing.access_count += 1
            if source:
                existing.source = source
            if thread_id:
                existing.thread_id = thread_id
            if run_id:
                existing.run_id = run_id
            if message_ids:
                existing_ids = json.loads(existing.message_ids or "[]")
                merged_ids = list(dict.fromkeys(existing_ids + message_ids))  # dedup, keep order
                existing.message_ids = json.dumps(merged_ids, ensure_ascii=False)
            await self.session.flush()
            return existing
        else:
            memory = AgentMemory(
                user_id=self.user_id,
                key=key,
                value=value_str,
                memory_type=memory_type,
                status="confirmed",  # Hermes: directly saved memories are confirmed
                importance=importance,
                confidence=confidence,
                source=source,
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
                message_ids=json.dumps(message_ids, ensure_ascii=False) if message_ids else None,
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

    async def get_all_memories(self, min_confidence: float | None = 0.0) -> list[dict]:
        """获取所有中期记忆（DeerFlow: 置信度分数过滤，低置信度不注入上下文）。

        Args:
            min_confidence: 最小置信度阈值，默认 0.0 获取全部记忆（用于管理界面）。
                            注入模型上下文时显式传入 MIN_CONFIDENCE_FOR_CONTEXT (0.7)。
        """
        threshold = 0.0 if min_confidence is None else min_confidence
        result = await self.session.execute(
            select(AgentMemory)
            .where(
                AgentMemory.user_id == self.user_id,
                AgentMemory.confidence >= threshold,
            )
            .order_by(AgentMemory.importance.desc(), AgentMemory.confidence.desc())
        )
        memories = result.scalars().all()
        return [
            {
                "key": m.key,
                "value": m.value,
                "type": m.memory_type,
                "importance": m.importance,
                "confidence": m.confidence,
                "source": m.source,
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
        await ensure_builtin_skills(self.session, self.user_id)
        query = select(AgentSkill).where(AgentSkill.user_id == self.user_id)
        if skill_type:
            query = query.where(AgentSkill.skill_type == skill_type)
        if min_usage is not None:
            query = query.where(AgentSkill.usage_count >= min_usage)
        query = query.order_by(AgentSkill.is_builtin.desc(), AgentSkill.usage_count.desc(), AgentSkill.name.asc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_skills_by_ids_or_names(self, ids_or_names: list[str]) -> list[AgentSkill]:
        """按数据库 ID 或稳定 Skill 名称解析 profile 默认 Skill。"""
        await ensure_builtin_skills(self.session, self.user_id)
        normalized = [str(item).strip() for item in ids_or_names if str(item or "").strip()]
        if not normalized:
            return []

        numeric_ids = [int(item) for item in normalized if item.isdigit()]
        names = [item for item in normalized if not item.isdigit()]
        query = select(AgentSkill).where(AgentSkill.user_id == self.user_id)
        if numeric_ids and names:
            from sqlalchemy import or_

            query = query.where(or_(AgentSkill.id.in_(numeric_ids), AgentSkill.name.in_(names)))
        elif numeric_ids:
            query = query.where(AgentSkill.id.in_(numeric_ids))
        else:
            query = query.where(AgentSkill.name.in_(names))

        result = await self.session.execute(query)
        skills = list(result.scalars().all())
        order = {value: index for index, value in enumerate(normalized)}
        return sorted(skills, key=lambda skill: min(order.get(str(skill.id), 999), order.get(skill.name, 999)))

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

    async def build_memory_context(self, default_skill_ids: Optional[list[str]] = None) -> str:
        """
        将 L2 + L3 记忆组装成文本，注入到 LLM 的 system prompt。

        这是 Hermes "记忆即上下文" 思想的核心实现，结合 DeerFlow 的：
        - 置信度过滤（< 0.7 不注入）
        - Token 预算控制（最多 MAX_MEMORY_CONTEXT_TOKENS 字符）
        - 按置信度降序排列（DeerFlow: 按 confidence 降序取前 2000 token）
        """
        from app.services.agent.context_compressor import estimate_tokens

        parts: list[str] = []
        total_est_tokens = 0

        # L2：中期记忆（置信度过滤 + token 预算）
        memories = await self.get_all_memories(min_confidence=self.MIN_CONFIDENCE_FOR_CONTEXT)
        if memories:
            header = "## 用户偏好和关键信息（中期记忆）"
            parts.append(header)
            total_est_tokens += estimate_tokens(header)
            for m in memories:
                line = f"- {m['key']}: {m['value']} [置信度:{m.get('confidence', 0):.0%}]"
                line_tokens = estimate_tokens(line)
                if total_est_tokens + line_tokens > self.MAX_MEMORY_CONTEXT_TOKENS:
                    parts.append(f"- ...（共 {len(memories)} 条，已截断至 token 预算）")
                    break
                parts.append(line)
                total_est_tokens += line_tokens

        # L3：技能索引。即使尚未高频使用，也要让智能体知道已有能力。
        # Profile 明确声明的默认 Skill 必须稳定出现在索引前部，避免新增内置
        # Skill 后仅因 token 截断就丢失关键能力（例如 reference_match）。
        skills = await self.list_skills()
        selected_skills = await self.get_skills_by_ids_or_names(default_skill_ids or [])
        selected_names = {skill.name for skill in selected_skills}
        # These foundational capabilities are part of the default agent contract
        # and should remain discoverable even for profiles without explicit defaults.
        priority_names = selected_names | {"reference_match"}
        priority_skills = [skill for skill in skills if skill.name in priority_names]
        if priority_skills:
            skills = [
                *[skill for skill in selected_skills if skill in skills],
                *[skill for skill in priority_skills if skill.name not in selected_names],
                *[skill for skill in skills if skill.name not in priority_names],
            ]
        if skills:
            header = "\n## 可用 Skill 索引（长期记忆）"
            parts.append(header)
            total_est_tokens += estimate_tokens(header)
            for s in skills[:24]:
                marker = "内置" if s.is_builtin else "自定义"
                line = f"- {s.name}（{marker}/{s.skill_type}）：{s.description}"
                if total_est_tokens + estimate_tokens(line) > self.MAX_MEMORY_CONTEXT_TOKENS:
                    break
                parts.append(line)
                total_est_tokens += estimate_tokens(line)

        if selected_skills:
            header = "\n## 默认 Skill 工作方法"
            parts.append(header)
            for s in selected_skills[:8]:
                part = f"\n### {s.name}\n{s.description}\n{s.content}"
                if total_est_tokens + estimate_tokens(part) > self.MAX_MEMORY_CONTEXT_TOKENS * 2:
                    break
                parts.append(part)

        return "\n".join(parts) if parts else ""

    async def build_readable_memory_view(self) -> dict[str, str]:
        """Render database-backed memory into Hermes-style editable Markdown views."""
        memories = await self.get_all_memories(min_confidence=0.0)
        skills = await self.list_skills()

        user_lines = [
            "# USER.md",
            "",
            "用户偏好、沟通方式和稳定选择。数据库仍是真实来源；本文件是可读视图。",
            "",
        ]
        memory_lines = [
            "# MEMORY.md",
            "",
            "项目事实、规则、长期上下文和可复用知识。数据库仍是真实来源；本文件是可读视图。",
            "",
        ]
        skill_lines = [
            "# SKILLS.md",
            "",
            "Agent 可调用的长期工作方法和内置流程。",
            "",
        ]

        preference_count = 0
        memory_count = 0
        for item in memories:
            line = (
                f"- `{item['key']}` ({item.get('type') or 'fact'}, "
                f"importance={item.get('importance')}, confidence={item.get('confidence', 0):.0%})\n"
                f"  {item.get('value') or ''}"
            )
            if item.get("type") == "preference":
                user_lines.append(line)
                preference_count += 1
            else:
                memory_lines.append(line)
                memory_count += 1

        if preference_count == 0:
            user_lines.append("- 暂无用户偏好记忆。")
        if memory_count == 0:
            memory_lines.append("- 暂无项目/事实记忆。")

        if skills:
            for skill in skills:
                marker = "builtin" if skill.is_builtin else "custom"
                skill_lines.append(f"## {skill.name}")
                skill_lines.append("")
                skill_lines.append(f"- type: `{skill.skill_type}`")
                skill_lines.append(f"- source: `{marker}`")
                skill_lines.append(f"- usage: `{skill.usage_count}` / success `{skill.success_count}`")
                skill_lines.append("")
                skill_lines.append(skill.description or "")
                if skill.content:
                    skill_lines.append("")
                    skill_lines.append(skill.content)
                skill_lines.append("")
        else:
            skill_lines.append("- 暂无技能。")

        user_md = "\n".join(user_lines).strip() + "\n"
        memory_md = "\n".join(memory_lines).strip() + "\n"
        skills_md = "\n".join(skill_lines).strip() + "\n"
        return {
            "user_md": user_md,
            "memory_md": memory_md,
            "skills_md": skills_md,
            "combined_md": "\n\n---\n\n".join([user_md.strip(), memory_md.strip(), skills_md.strip()]) + "\n",
        }
