"""Thread manager for the Agent runtime.

AgentThread is the durable root object. AgentSession remains as a legacy facade
while the runtime migrates toward DeerFlow/Hermes-style thread ledgers.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentContextSnapshot, AgentMemory, AgentMemorySnapshot, AgentMessage, AgentRun, AgentSession, AgentThread


def _safe_json_loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback


class ThreadManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_thread(
        self,
        *,
        user_id: str = "default",
        title: str = "",
        active_profile_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentThread:
        thread = AgentThread(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title or f"Thread {datetime.utcnow().strftime('%m-%d %H:%M')}",
            active_profile_id=active_profile_id or "",
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, default=str),
        )
        self.session.add(thread)
        await self.session.flush()
        return thread

    async def get_thread(self, thread_id: str, *, migrate_legacy: bool = True) -> AgentThread | None:
        if not thread_id:
            return None
        thread = await self.session.get(AgentThread, thread_id)
        if thread or not migrate_legacy:
            return thread
        legacy = await self.session.get(AgentSession, thread_id)
        if not legacy:
            return None
        return await self._migrate_legacy_session(legacy)

    async def list_threads(self, user_id: str = "default", limit: int = 50) -> list[AgentThread]:
        result = await self.session.execute(
            select(AgentThread)
            .where(AgentThread.user_id == user_id, AgentThread.status != "archived")
            .order_by(AgentThread.updated_at.desc())
            .limit(limit)
        )
        threads = list(result.scalars().all())
        if threads:
            return threads

        legacy_result = await self.session.execute(
            select(AgentSession)
            .where(AgentSession.user_id == user_id, AgentSession.is_archived == False)
            .order_by(AgentSession.updated_at.desc())
            .limit(limit)
        )
        migrated: list[AgentThread] = []
        for legacy in legacy_result.scalars().all():
            migrated.append(await self._migrate_legacy_session(legacy))
        return migrated

    async def update_title(self, thread_id: str, title: str) -> bool:
        thread = await self.session.get(AgentThread, thread_id)
        if not thread:
            return False
        thread.title = title
        thread.updated_at = datetime.utcnow()
        legacy = await self.session.get(AgentSession, thread_id)
        if legacy:
            legacy.title = title
            legacy.updated_at = thread.updated_at
        await self.session.flush()
        return True

    async def archive_thread(self, thread_id: str) -> bool:
        thread = await self.get_thread(thread_id)
        if not thread:
            return False
        thread.status = "archived"
        thread.archived_at = datetime.utcnow()
        thread.updated_at = datetime.utcnow()
        legacy = await self.session.get(AgentSession, thread_id)
        if legacy:
            legacy.is_archived = True
            legacy.updated_at = datetime.utcnow()
        await self.session.flush()
        return True

    async def ensure_legacy_session(self, thread: AgentThread) -> AgentSession:
        legacy = await self.session.get(AgentSession, thread.id)
        if legacy:
            return legacy
        legacy = AgentSession(
            id=thread.id,
            user_id=thread.user_id,
            title=thread.title,
            messages="[]",
            context=json.dumps(_safe_json_loads(thread.metadata_json, {}).get("legacy_context") or {}, ensure_ascii=False),
            is_archived=thread.status == "archived",
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
        self.session.add(legacy)
        await self.session.flush()
        return legacy

    async def update_context(self, thread_id: str, context: dict[str, Any]) -> bool:
        thread = await self.get_thread(thread_id)
        if not thread:
            return False
        metadata = _safe_json_loads(thread.metadata_json, {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["legacy_context"] = context or {}
        thread.metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)
        thread.updated_at = datetime.utcnow()
        legacy = await self.session.get(AgentSession, thread_id)
        if legacy:
            legacy.context = json.dumps(context or {}, ensure_ascii=False, default=str)
            legacy.updated_at = thread.updated_at
        await self.session.flush()
        return True

    async def append_message(
        self,
        thread_id: str,
        message: dict[str, Any],
        *,
        run_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage | None:
        thread = await self.get_thread(thread_id)
        if not thread:
            return None
        # M2.3: Single entry point — write to AgentMessage table
        row = AgentMessage(
            thread_id=thread_id,
            run_id=run_id or str(message.get("run_id") or ""),
            role=str(message.get("role") or "user"),
            content=str(message.get("content") or ""),
            content_json=json.dumps(message, ensure_ascii=False, default=str),
            tool_call_id=str(message.get("tool_call_id") or ""),
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, default=str),
        )
        self.session.add(row)
        thread.updated_at = datetime.utcnow()
        # M2.3: Dual-write to legacy AgentSession.messages for backward compat
        legacy = await self.session.get(AgentSession, thread_id)
        if legacy:
            legacy_messages = _safe_json_loads(legacy.messages or "[]", [])
            legacy_messages.append(message)
            legacy.messages = json.dumps(legacy_messages, ensure_ascii=False, default=str)
            legacy.updated_at = thread.updated_at
        await self.session.flush()
        return row

    async def get_messages(self, thread_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = select(AgentMessage).where(AgentMessage.thread_id == thread_id).order_by(AgentMessage.id.asc())
        if limit:
            query = query.limit(limit)
        result = await self.session.execute(query)
        rows = list(result.scalars().all())
        if rows:
            return [
                {
                    **(_safe_json_loads(row.content_json, {}) if row.content_json else {}),
                    "id": row.id,
                    "run_id": row.run_id or "",
                    "role": row.role,
                    "content": row.content,
                    "tool_call_id": row.tool_call_id or None,
                    "metadata": _safe_json_loads(row.metadata_json, {}),
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
                for row in rows
            ]
        legacy = await self.session.get(AgentSession, thread_id)
        if legacy:
            return _safe_json_loads(legacy.messages or "[]", [])
        return []

    async def create_context_snapshot(
        self,
        *,
        thread_id: str,
        run_id: str = "",
        kind: str = "planning",
        context: dict[str, Any],
        summary: str = "",
        token_estimate: int = 0,
    ) -> AgentContextSnapshot:
        snapshot = AgentContextSnapshot(
            thread_id=thread_id,
            run_id=run_id,
            kind=kind,
            context_json=json.dumps(context or {}, ensure_ascii=False, default=str),
            summary=summary,
            token_estimate=token_estimate,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def build_thread_context(
        self,
        thread_id: str,
        *,
        message_limit: int = 50,
        include_memories: bool = True,
        include_snapshots: bool = True,
        include_recent_runs: bool = True,
        recent_run_limit: int = 5,
    ) -> dict[str, Any]:
        """Build the full thread-level context from the database (M4.1).

        Collects messages, recent context snapshots, confirmed memories, and recent runs
        into a structured context dict suitable for model injection.
        """
        result: dict[str, Any] = {
            "thread_id": thread_id,
            "sections": {},
        }

        # 1. Short-term context: recent messages
        messages = await self.get_messages(thread_id, limit=message_limit)
        result["sections"]["short_term_context"] = {
            "message_count": len(messages),
            "messages": [
                {
                    "role": str(m.get("role") or "user"),
                    "content": str(m.get("content") or "")[:500],
                    "run_id": str(m.get("run_id") or ""),
                }
                for m in messages[-20:]
                if isinstance(m, dict) and m.get("role") in {"user", "assistant", "system", "tool"}
            ],
        }

        # 2. Conversation state: from the last context snapshot
        if include_snapshots:
            try:
                snap_result = await self.session.execute(
                    select(AgentContextSnapshot)
                    .where(AgentContextSnapshot.thread_id == thread_id)
                    .order_by(AgentContextSnapshot.created_at.desc())
                    .limit(1)
                )
                last_snapshot = snap_result.scalar_one_or_none()
                if last_snapshot:
                    snapshot_data = _safe_json_loads(last_snapshot.context_json, {})
                    if isinstance(snapshot_data, dict):
                        result["sections"]["conversation_state"] = snapshot_data.get(
                            "conversation_state", {}
                        )
                        result["sections"]["project_context"] = {
                            k: v
                            for k, v in snapshot_data.items()
                            if k
                            in {
                                "profile",
                                "context_summary",
                                "routed_skills",
                                "effective_context_keys",
                            }
                        }
                        result["sections"]["recent_run_context"] = snapshot_data.get(
                            "recent_run_context", []
                        )
            except SQLAlchemyError as exc:
                result["sections"]["conversation_state"] = {"error": str(exc)}

        # 3. Project context: from thread metadata
        thread = await self.session.get(AgentThread, thread_id)
        if thread:
            metadata = _safe_json_loads(thread.metadata_json, {})
            if isinstance(metadata, dict):
                project_id = metadata.get("project_id") or metadata.get("creative_project_id")
                if project_id:
                    result["sections"]["project_context"] = {
                        **(result["sections"].get("project_context") or {}),
                        "project_id": project_id,
                        "active_profile_id": thread.active_profile_id or "",
                    }

        # 4. Memory context: confirmed memories for this thread
        if include_memories:
            try:
                mem_result = await self.session.execute(
                    select(AgentMemory)
                    .where(
                        AgentMemory.thread_id == thread_id,
                        AgentMemory.status == "confirmed",
                    )
                    .order_by(AgentMemory.updated_at.desc())
                    .limit(20)
                )
                memories = list(mem_result.scalars().all())
                result["sections"]["memory_context"] = {
                    "memory_count": len(memories),
                    "memories": [
                        {
                            "content": m.content or "",
                            "confidence": float(m.confidence or 1.0),
                            "source": m.source or "",
                            "run_id": m.run_id or "",
                        }
                        for m in memories
                    ],
                }
            except SQLAlchemyError as exc:
                result["sections"]["memory_context"] = {"error": str(exc)}

        # 5. Recent runs on this thread
        if include_recent_runs:
            try:
                run_result = await self.session.execute(
                    select(AgentRun)
                    .where(AgentRun.session_id == thread_id)
                    .order_by(AgentRun.created_at.desc())
                    .limit(recent_run_limit)
                )
                runs = list(run_result.scalars().all())
                result["sections"]["recent_runs"] = [
                    {
                        "run_id": r.id,
                        "status": r.status,
                        "objective": (r.objective or "")[:200],
                        "tool_call_count": len(
                            _safe_json_loads(r.result_json or "{}", {}).get("tool_results", [])
                        ),
                    }
                    for r in runs
                ]
            except SQLAlchemyError as exc:
                result["sections"]["recent_runs"] = {"error": str(exc)}

        return result

    async def _migrate_legacy_session(self, legacy: AgentSession) -> AgentThread:
        existing = await self.session.get(AgentThread, legacy.id)
        if existing:
            return existing
        thread = AgentThread(
            id=legacy.id,
            user_id=legacy.user_id,
            title=legacy.title,
            status="archived" if legacy.is_archived else "active",
            metadata_json=json.dumps(
                {"legacy_session_id": legacy.id, "legacy_context": _safe_json_loads(legacy.context, {})},
                ensure_ascii=False,
                default=str,
            ),
            created_at=legacy.created_at,
            updated_at=legacy.updated_at,
            archived_at=legacy.updated_at if legacy.is_archived else None,
        )
        self.session.add(thread)
        await self.session.flush()
        messages = _safe_json_loads(legacy.messages or "[]", [])
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, dict):
                    self.session.add(
                        AgentMessage(
                            thread_id=thread.id,
                            role=str(message.get("role") or "user"),
                            content=str(message.get("content") or ""),
                            content_json=json.dumps(message, ensure_ascii=False, default=str),
                            tool_call_id=str(message.get("tool_call_id") or ""),
                            metadata_json=json.dumps({"migrated_from_session": True}, ensure_ascii=False),
                            created_at=legacy.created_at,
                        )
                    )
        await self.session.flush()
        return thread
