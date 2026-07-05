"""
YLCraft — Agent 会话管理器（短期记忆）

每个会话是一个对话上下文，包含：
- messages: list[dict]  （OpenAI 格式消息）
- context: dict            （当前上下文，如当前选中的素材/视频）
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentSession, AgentSessionCreate

logger = logging.getLogger("ylcraft.agent.session")


class SessionManager:
    """管理 Agent 对话会话（短期记忆）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(self, user_id: str = "default", title: str = "", session_id: str | None = None) -> AgentSession:
        """创建新会话"""
        session_id = session_id or str(uuid.uuid4())
        if not title:
            title = f"对话 {datetime.utcnow().strftime('%m-%d %H:%M')}"

        db_session = AgentSession(
            id=session_id,
            user_id=user_id,
            title=title,
            messages="[]",
            context="{}",
        )
        self.session.add(db_session)
        await self.session.flush()
        await self.session.refresh(db_session)
        logger.info(f"[Session] Created: {session_id} - {title}")
        return db_session

    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        """获取会话"""
        result = await self.session.execute(
            select(AgentSession).where(AgentSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def append_message(self, session_id: str, message: dict) -> bool:
        """追加一条消息到会话"""
        db_session = await self.get_session(session_id)
        if not db_session:
            return False

        messages = json.loads(db_session.messages or "[]")
        messages.append(message)
        db_session.messages = json.dumps(messages, ensure_ascii=False)
        db_session.updated_at = datetime.utcnow()
        await self.session.flush()
        return True

    async def get_messages(self, session_id: str) -> list[dict]:
        """获取会话的所有消息"""
        db_session = await self.get_session(session_id)
        if not db_session:
            return []
        return json.loads(db_session.messages or "[]")

    async def update_context(self, session_id: str, context: dict) -> bool:
        """更新会话上下文（如"当前选中的素材"）"""
        db_session = await self.get_session(session_id)
        if not db_session:
            return False

        db_session.context = json.dumps(context, ensure_ascii=False)
        db_session.updated_at = datetime.utcnow()
        await self.session.flush()
        return True

    async def list_sessions(self, user_id: str = "default", limit: int = 50) -> list[AgentSession]:
        """列出用户的所有会话"""
        result = await self.session.execute(
            select(AgentSession)
            .where(AgentSession.user_id == user_id, AgentSession.is_archived == False)
            .order_by(AgentSession.updated_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def archive_session(self, session_id: str) -> bool:
        """归档会话（软删除）"""
        db_session = await self.get_session(session_id)
        if not db_session:
            return False
        db_session.is_archived = True
        await self.session.flush()
        return True

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（软删除，等同于归档）"""
        return await self.archive_session(session_id)
