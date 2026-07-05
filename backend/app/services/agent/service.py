"""YLCraft Agent service.

This is a lightweight Hermes-style loop:
profile -> memory -> LLM -> tool calls -> tool results -> final answer.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentMemorySnapshot, AgentRun, AgentRunStep, AgentToolCall, AgentSession
from app.services.agent import tools as _agent_tools  # noqa: F401 - register tools
from app.services.agent.context_compressor import ContextCompressor
from app.services.agent.context_pack import build_creative_project_context_pack
from app.services.agent.loop_detector import LoopDetector
from app.services.agent.memory.manager import MemoryManager
from app.services.agent.profile import AgentProfileManager, profile_to_dict
from app.services.agent.registry import ToolCallResult, ToolRegistry
from app.services.agent.runtime import ContextAssembler, Planner, RunLoop, SkillRouter, ToolExecutor
from app.services.agent.runtime.tools import CONFIRMATION_RISK_LEVELS

from app.services.agent.thread_manager import ThreadManager
from app.services.ai import get_ai_service

logger = logging.getLogger("ylcraft.agent.service")



AGENT_SYSTEM_PROMPT = """你是 YLCraft Agent Center 的总控智能体。你可以调用工具帮助用户完成素材管理、创作项目、字幕、剪辑、BGM、爆款拆解、AI 模型配置等任务。

工作原则：
1. 先判断用户意图，再选择最少必要工具。
2. 不要编造项目、素材、文件路径、任务状态或生成结果。
3. 会改动项目内容的工具必须保留版本和日志；不要绕过 YLCraft 现有服务。
4. 工具失败时要解释失败原因和下一步可做什么。
5. 执行模式：先规划→调用工具→观察结果→继续推进，每轮都是新的决策点。迭代预算耗尽时自动总结已完成工作和下一步建议。

AI 模型配置能力：
- 当用户需要配置新的 AI 供应商或模型时，先用 list_provider_metadata 查看已注册的供应商规范。
- 注册新供应商：调用 upsert_provider_metadata，填入 provider_id、name、base_url、api_format，以及各类型的 request_templates、response_configs。
- 创建连接器：调用 create_ai_connector，填入 name、provider、provider_type、default_model、api_key，必要时填 request_template、response_config。
- 修改连接器：调用 update_ai_connector，只传需要修改的字段。
- 验证配置：调用 test_ai_connector 测试连通性，调用 discover_connector_models 自动发现可用模型列表。

如果当前模型不支持原生 function calling，也可以用 JSON 返回工具调用：
{"tool_calls":[{"id":"call_1","name":"inspect_creative_project","arguments":"{\\"project_id\\":\\"...\\"}"}]}
"""


class AgentService:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.thread_mgr = ThreadManager(session)
        self.memory_mgr = MemoryManager(session, user_id)
        self.profile_mgr = AgentProfileManager(session, user_id)
        self._llm_manager = None
        # DeerFlow-inspired: context compression + loop detection
        self._compressor = ContextCompressor()
        self._loop_detector = LoopDetector()
        self.context_assembler = ContextAssembler(session, creative_project_context_builder=build_creative_project_context_pack)
        self.skill_router = SkillRouter()
        self.tool_executor = ToolExecutor()
        self.run_loop = RunLoop(self._loop_detector)
        self.planner = Planner(
            llm_manager_getter=lambda: self.llm_manager,
            provider_chain_builder=self._build_failover_chain,
            compressor=self._compressor,
        )

    @property
    def llm_manager(self):
        if self._llm_manager is None:
            self._llm_manager = get_ai_service()
        return self._llm_manager

    async def chat(
        self,
        session_id: str,
        user_message: str,
        context: dict | None = None,
        profile_id: str | None = None,
        parent_run_id: str | None = None,
        force_new_thread: bool = False,
    ) -> dict[str, Any]:
        self._loop_detector.reset()
        # 入口防御性清理：若连接池复用导致当前 session 继承了 aborted 事务，
        # 在开始新工作前回滚清脏。仅对有活跃事务的 session 安全调用。
        if self.session.in_transaction():
            try:
                await self.session.rollback()
            except Exception:  # noqa: BLE001
                logger.debug("[AgentService] chat() entry rollback failed")

        try:
            state = await self._intake_phase(
                session_id=session_id,
                user_message=user_message,
                context=context or {},
                profile_id=profile_id,
                parent_run_id=parent_run_id,
                force_new_thread=force_new_thread,
            )
            await self.session.commit()

            await self._context_pack_phase(state)
            await self.session.commit()

            await self._plan_phase(state)
            await self.session.commit()

            await self._tool_loop_phase(state)
            await self.session.commit()

            result = await self._final_phase(state)
            await self.session.commit()
            return result
        except Exception:
            # 单 phase 失败：仅回滚当前未提交事务，已 commit 的前序步骤保留。
            try:
                await self.session.rollback()
            except Exception:  # noqa: BLE001
                logger.debug("[AgentService] chat() error rollback skipped")
            raise

    async def _intake_phase(
        self,
        session_id: str,
        user_message: str,
        context: dict[str, Any],
        profile_id: str | None,
        parent_run_id: str | None,
        force_new_thread: bool = False,
    ) -> dict[str, Any]:
        """Create or resume a thread, load the profile, and create the run."""
        incoming_id = str(session_id or "").strip()
        thread = None
        db_session = None

        if incoming_id and not force_new_thread:
            thread = await self.thread_mgr.get_thread(incoming_id)
            if thread:
                session_id = thread.id
                db_session = await self.thread_mgr.ensure_legacy_session(thread)

        if not thread and not force_new_thread:
            recovered_session = await self._recover_recent_session_for_followup(user_message)
            if recovered_session:
                db_session = recovered_session
                session_id = recovered_session.id
                thread = await self.thread_mgr.get_thread(recovered_session.id)

        if not thread:
            thread = await self.thread_mgr.create_thread(
                user_id=self.user_id,
                title=user_message[:50],
            )
            session_id = thread.id
            is_new_thread = True
        else:
            is_new_thread = False

        if not db_session:
            db_session = await self.thread_mgr.ensure_legacy_session(thread)

        session_context = self._safe_json_loads(getattr(db_session, "context", "") or "{}", {})
        thread_metadata = self._safe_json_loads(getattr(thread, "metadata_json", "") or "{}", {})
        if isinstance(thread_metadata, dict) and isinstance(thread_metadata.get("legacy_context"), dict):
            session_context = {**session_context, **thread_metadata["legacy_context"]}

        profile = await self.profile_mgr.get_profile(profile_id)
        profile_data = profile_to_dict(profile)
        effective_context = self.context_assembler.merge_context(session_context, profile_data, context)
        if effective_context:
            await self.thread_mgr.update_context(thread.id, effective_context)

        user_thread_message = await self.thread_mgr.append_message(
            thread.id,
            {"role": "user", "content": user_message},
            metadata={"phase": "intake"},
        )

        run = await self._create_run(
            session_id=thread.id,
            profile_id=str(profile_data.get("id") or ""),
            objective=user_message,
            context=effective_context,
            parent_run_id=parent_run_id,
        )
        if user_thread_message:
            user_thread_message.run_id = run.id
            await self.session.flush()
        await self._record_run_step(
            run.id,
            step_type="intake",
            status="completed",
            session_id=thread.id,
            profile_id=str(profile_data.get("id") or ""),
            order_index=0,
            summary="接收用户请求并创建运行记录",
            input_data={"message": user_message},
            output_data={"thread_id": thread.id, "session_id": thread.id, "profile": profile_data.get("name")},
        )
        return {
            "session_id": thread.id,
            "thread_id": thread.id,
            "is_new_thread": is_new_thread,
            "user_message": user_message,
            "request_context": context,
            "profile": profile_data,
            "effective_context": effective_context,
            "run": run,
            "step_index": 1,
            "messages": [],
            "memory_context": "",
            "llm_response": {},
            "tool_results": [],
        }

    async def _recover_recent_session_for_followup(self, user_message: str) -> AgentSession | None:
        """Recover the active thread when the client drops session_id for a short follow-up.

        This is a backend guardrail for refresh/HMR/stale-client cases. A full new
        objective should still create a fresh session unless the frontend sends an
        explicit session_id.
        """
        text = str(user_message or "").strip()
        if not self._looks_like_followup_message(text):
            return None
        try:
            result = await self.session.execute(
                select(AgentSession)
                .where(AgentSession.user_id == self.user_id, AgentSession.is_archived == False)
                .order_by(AgentSession.updated_at.desc())
                .limit(8)
            )
            sessions = list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] follow-up session recovery skipped: %s", exc)
            return None
        for candidate in sessions:
            messages = self._safe_json_loads(candidate.messages or "[]", [])
            if not isinstance(messages, list) or not messages:
                continue
            prior_state = self._safe_json_loads(candidate.context or "{}", {}).get("conversation_state", {})
            trial_messages = [*messages, {"role": "user", "content": text}]
            resolution = self.context_assembler.build_followup_resolution(trial_messages, prior_state)
            trial_state = self.context_assembler.build_conversation_state(trial_messages, prior_state)
            if resolution or trial_state.get("pending_action", {}).get("type") == "tool_call_ready":
                logger.info("[AgentService] recovered follow-up into recent session %s", candidate.id)
                return candidate
        return None

    def _looks_like_followup_message(self, text: str) -> bool:
        if not text:
            return False
        if self.context_assembler.extract_search_keyword(text):
            return False
        if self.context_assembler.extract_platform(text) and self.context_assembler.is_platform_refinement_without_keyword(text):
            return True
        compact = re.sub(r"\s+", "", text)
        if len(compact) > 40:
            return False
        return bool(
            re.search(
                r"(继续|确认|可以|好的|好|是|用|走|换|改|按|这个|那个|上面|刚才|技能|工具|平台|再|也|搜|搜索|b站|bili|douyin|xhs|dy|ks|wechat|公众号)",
                compact,
                flags=re.I,
            )
        )

    async def _context_pack_phase(self, state: dict[str, Any]) -> None:
        """Persist context and build memory/Skill prompt context.

        Injects: creative project context, character info, run history, default skills,
        and long-term memories into the agent's system prompt.
        """
        run: AgentRun = state["run"]
        profile = state["profile"]
        effective_context = state["effective_context"]

        # Build context summary text for injection
        context_parts: list[str] = []
        creative_pack = effective_context.get("creative_project_context")
        if creative_pack and creative_pack.get("project"):
            project = creative_pack["project"]
            context_parts.append(
                f"当前创作项目：{project.get('title') or '未命名'} "
                f"({project.get('project_type') or 'unknown'})，"
                f"阶段：{project.get('current_stage') or '未标记'}，"
                f"共 {project.get('chapter_count') or 0} 章"
            )
            characters = creative_pack.get("characters") or []
            if characters:
                names = [c.get("name") for c in characters[:8] if c.get("name")]
                context_parts.append(f"关联角色：{'、'.join(names)}")
            gaps = creative_pack.get("known_gaps") or []
            if gaps:
                context_parts.append(f"已知缺口：{'、'.join(gaps)}")

        # Inject past run history if continuing
        if effective_context.get("continued_from_run_id"):
            context_parts.append("这是继续之前的智能体运行，请基于已完成的工作继续推进。")

        state["context_summary"] = "\n".join(context_parts) if context_parts else ""
        state["effective_context"] = effective_context

        state["messages"] = await self.thread_mgr.get_messages(state["thread_id"])
        state["conversation_state"] = self.context_assembler.build_conversation_state(
            state["messages"],
            state["effective_context"].get("conversation_state") if isinstance(state["effective_context"], dict) else {},
        )
        state["effective_context"]["conversation_state"] = state["conversation_state"]
        state["routed_skills"] = self.skill_router.route(
            message=state["user_message"],
            context=state["effective_context"],
            allowed_tools=profile.get("allowed_tools") or [],
            default_skill_ids=state["effective_context"].get("default_skill_ids") or profile.get("default_skill_ids") or [],
        )
        state["effective_context"]["routed_skill_ids"] = [item.skill_id for item in state["routed_skills"]]
        await self.thread_mgr.update_context(state["thread_id"], state["effective_context"])
        state["recent_run_context"] = await self.context_assembler.build_recent_run_context(
            state["session_id"],
            current_run_id=run.id,
        )
        state["short_term_context"] = self.context_assembler.build_short_term_context_text(
            messages=state["messages"],
            effective_context=state["effective_context"],
            conversation_state=state["conversation_state"],
            recent_run_context=state["recent_run_context"],
            routed_skills=state["routed_skills"],
        )
        state["followup_resolution"] = self.context_assembler.build_followup_resolution(
            state["messages"],
            state["conversation_state"],
        )
        skill_ids = list(dict.fromkeys(
            (state["effective_context"].get("default_skill_ids") or profile.get("default_skill_ids") or [])
            + [item.skill_id for item in state["routed_skills"]]
        ))
        state["memory_context"] = await self.memory_mgr.build_memory_context(
            default_skill_ids=skill_ids
        )
        state["tool_index_context"] = self._build_tool_index_context(profile.get("allowed_tools") or [])
        profile["_tool_index_context"] = state["tool_index_context"]
        await self._create_memory_snapshot(state)
        await self._create_thread_context_snapshot(state)

        await self._record_run_step(
            run.id,
            step_type="context_pack",
            status="completed",
            session_id=state["session_id"],
            profile_id=str(profile.get("id") or ""),
            order_index=state["step_index"],
            summary="组装智能体上下文、项目包、记忆和 Skill 提示",
            input_data={"request_context": state["request_context"]},
            output_data={
                "effective_context": effective_context,
                "context_summary_lines": len(context_parts),
                "context_summary": state["context_summary"],
                "message_count": len(state["messages"]),
                "conversation_state": state["conversation_state"],
                "routed_skills": [
                    {"skill_id": item.skill_id, "reason": item.reason, "score": item.score}
                    for item in state["routed_skills"]
                ],
                "short_term_context_preview": self._summarize_text(state["short_term_context"], limit=800),
                "recent_run_context": state["recent_run_context"],
                "followup_resolution": state["followup_resolution"],
                "memory_context_injected": bool(state["memory_context"]),
                "memory_context_preview": self._summarize_text(state["memory_context"], limit=600),
                "tool_index_injected": bool(state["tool_index_context"]),
            },
        )
        state["step_index"] += 1

    async def _plan_phase(self, state: dict[str, Any]) -> None:
        """Ask the LLM to answer directly or select tools."""
        profile = state["profile"]
        state["llm_response"] = await self._call_llm(
            state["messages"],
            state["memory_context"],
            profile,
            context_summary=state.get("context_summary", ""),
            short_term_context=state.get("short_term_context", ""),
            followup_resolution=state.get("followup_resolution") or {},
        )
        if not state["llm_response"].get("tool_calls"):
            followup_tool_call = self.tool_executor.tool_call_from_followup_resolution(
                state.get("followup_resolution") or {},
                profile,
            )
            if followup_tool_call:
                state["llm_response"]["tool_calls"] = [followup_tool_call]
                state["llm_response"]["content"] = "我会把本轮补充条件和上一轮搜索目标合并后调用平台搜索工具。"
        await self._record_run_step(
            state["run"].id,
            step_type="llm_response",
            status="completed",
            session_id=state["session_id"],
            profile_id=str(profile.get("id") or ""),
            order_index=state["step_index"],
            summary=self._summarize_text(state["llm_response"].get("content") or "模型已返回响应"),
            input_data={"message_count": len(state["messages"]), "memory_injected": bool(state["memory_context"])},
            output_data=state["llm_response"],
        )
        state["step_index"] += 1

    async def _tool_loop_phase(self, state: dict[str, Any]) -> None:
        """Execute selected tools, observe results, and repeat within profile iteration budget.
        """
        await self.run_loop.run(
            state,
            execute_phase=self._execute_phase,
            observe_phase=self._observe_phase,
            handle_pending_confirmations=self._handle_pending_confirmations,
            handle_budget_exhausted=self._handle_budget_exhausted,
        )
        return

    async def _handle_pending_confirmations(self, state: dict[str, Any]) -> None:
        profile = state["profile"]
        pending_names = "、".join(
            item.get("tool_name") or item.get("name") or "工具"
            for item in state.get("pending_confirmations", [])
        )
        conversation_state = state.get("conversation_state") or {}
        if isinstance(conversation_state, dict):
            conversation_state["pending_action"] = {
                "type": "tool_confirmation",
                "tool_calls": state.get("pending_confirmations", []),
            }
            conversation_state["updated_at"] = datetime.utcnow().isoformat()
            state["conversation_state"] = conversation_state
            state["effective_context"]["conversation_state"] = conversation_state
            await self.thread_mgr.update_context(state["thread_id"], state["effective_context"])
        state["llm_response"] = {
            "content": f"已准备调用 {pending_names}。这是写入、删除或消耗类操作，请确认后我再执行。",
            "tool_calls": [],
        }

    async def _handle_budget_exhausted(
        self,
        state: dict[str, Any],
        iteration: int,
        iteration_budget: int,
    ) -> None:
        profile = state["profile"]
        warning = (
            f"[系统提示] 迭代预算已用尽 ({iteration_budget}/{iteration_budget})。"
            "请基于已获取的工具结果给出最终回答，总结已完成工作和下一步建议。"
        )
        state["messages"].append({"role": "user", "content": warning})
        await self._record_run_step(
            state["run"].id,
            step_type="budget_exhausted",
            status="completed",
            session_id=state["session_id"],
            profile_id=str(profile.get("id") or ""),
            order_index=state["step_index"],
            summary=f"迭代预算耗尽 ({iteration_budget} 轮)，自动触发总结",
            input_data={"iteration": iteration, "budget": iteration_budget},
        )
        state["step_index"] += 1
        state["llm_response"] = await self._call_llm(
            state["messages"],
            state["memory_context"],
            profile,
            context_summary=state.get("context_summary", ""),
            short_term_context=state.get("short_term_context", ""),
            followup_resolution=state.get("followup_resolution") or {},
        )

    async def _execute_phase(self, state: dict[str, Any], tool_calls: list[dict[str, Any]]) -> None:
        """Execute all tool calls chosen by the previous model response."""
        profile = state["profile"]
        for tool_call in tool_calls:
            tool_call = self.tool_executor.repair_tool_call_with_followup(
                tool_call,
                state.get("followup_resolution") or {},
            )
            result = await self.tool_executor.execute_tool_call(
                tool_call,
                profile,
                log_callback=lambda tool_name, tool_args, tool_result: self._log_tool_call(
                    state["session_id"],
                    tool_name,
                    tool_args,
                    tool_result,
                ),
            )
            state["tool_results"].append(result)
            pending_confirmation = self.tool_executor.is_pending_confirmation(result)
            await self._record_run_step(
                state["run"].id,
                step_type="tool_call",
                status="pending" if pending_confirmation else ("completed" if result.success else "failed"),
                session_id=state["session_id"],
                profile_id=str(profile.get("id") or ""),
                order_index=state["step_index"],
                tool_name=result.tool_name,
                summary=self._summarize_tool_result(result),
                input_data=self.tool_executor.tool_call_to_dict(tool_call),
                output_data=result.result if (result.success or pending_confirmation) else {"error": result.error},
                linked_objects=self._extract_linked_objects(result),
                error=result.error or "",
                duration_ms=result.duration_ms,
            )
            state["step_index"] += 1
            observation = self._tool_result_observation(tool_call, result)
            state["messages"].append(observation)
            await self.thread_mgr.append_message(
                state["thread_id"],
                observation,
                run_id=state["run"].id,
                metadata={
                    "phase": "tool_observation",
                    "tool_name": result.tool_name,
                    "success": result.success,
                },
            )
            if pending_confirmation:
                state.setdefault("pending_confirmations", []).append(self.tool_executor.tool_call_to_dict(tool_call))

    async def _observe_phase(self, state: dict[str, Any]) -> None:
        """Ask the LLM to continue after seeing tool observations."""
        profile = state["profile"]
        state["llm_response"] = await self._call_llm(
            state["messages"],
            state["memory_context"],
            profile,
            context_summary=state.get("context_summary", ""),
            short_term_context=state.get("short_term_context", ""),
            followup_resolution=state.get("followup_resolution") or {},
        )
        await self._record_run_step(
            state["run"].id,
            step_type="observe",
            status="completed",
            session_id=state["session_id"],
            profile_id=str(profile.get("id") or ""),
            order_index=state["step_index"],
            summary=self._summarize_text(state["llm_response"].get("content") or "模型已观察工具结果"),
            input_data={"message_count": len(state["messages"])},
            output_data=state["llm_response"],
        )
        state["step_index"] += 1

    async def _final_phase(self, state: dict[str, Any]) -> dict[str, Any]:
        """Persist the final answer, finish the run, and return the API payload."""
        profile = state["profile"]
        reply = state["llm_response"].get("content") or ""
        await self.thread_mgr.append_message(
            state["thread_id"],
            {"role": "assistant", "content": reply},
            run_id=state["run"].id,
            metadata={"phase": "final"},
        )
        # Auto-generate thread title on first meaningful exchange
        if state.get("is_new_thread") and reply.strip():
            await self._generate_thread_title(
                thread_id=state["thread_id"],
                user_message=state["user_message"],
                assistant_reply=reply,
            )
        await self._record_run_step(
            state["run"].id,
            step_type="final",
            status="completed",
            session_id=state["session_id"],
            profile_id=str(profile.get("id") or ""),
            order_index=state["step_index"],
            summary=self._summarize_text(reply or "本轮没有生成文本回复"),
            output_data={"reply": reply, "tool_call_count": len(state["tool_results"])},
        )
        state["step_index"] += 1
        memory_candidates = self._extract_memory_candidates(
            user_message=state["user_message"],
            reply=reply,
            context=state["effective_context"],
        )
        if memory_candidates:
            thread_id = state.get("thread_id") or state["session_id"]
            run_id = state["run"].id
            # Attach thread_id and run_id to each candidate for Hermes provenance
            candidates_with_provenance = [
                {**item, "thread_id": thread_id, "run_id": run_id}
                if isinstance(item, dict) else item
                for item in memory_candidates
            ]
            await self._record_run_step(
                run_id,
                step_type="memory_extract",
                status="pending",
                session_id=state["session_id"],
                profile_id=str(profile.get("id") or ""),
                order_index=state["step_index"],
                summary=f"提取到 {len(memory_candidates)} 条待确认记忆",
                input_data={"message": state["user_message"], "reply": reply},
                output_data={
                    "candidates": candidates_with_provenance,
                    "thread_id": thread_id,
                    "run_id": run_id,
                },
            )
        await self._finish_run(
            state["run"],
            status="completed",
            result={
                "reply": reply,
                "tool_call_count": len(state["tool_results"]),
                "memory_candidates": memory_candidates,
                "profile": {"id": profile.get("id"), "name": profile.get("name")},
            },
        )
        return {
            "session_id": state["session_id"],
            "thread_id": state["thread_id"],
            "run_id": state["run"].id,
            "reply": reply,
            "tool_calls": [self._tool_result_to_dict(item) for item in state["tool_results"]],
            "memory_candidates": memory_candidates,
            "done": True,
            "profile": {
                "id": profile.get("id"),
                "name": profile.get("name"),
            },
        }

    async def _generate_thread_title(
        self,
        thread_id: str,
        user_message: str,
        assistant_reply: str,
    ) -> None:
        """Generate a concise thread title from the first user message and assistant response.

        Uses a lightweight LLM call to extract the user's objective in a short title.
        Falls back to truncating the user message if LLM is unavailable.
        """
        try:
            title_prompt = (
                "根据以下用户请求和助手回复，提取用户的核心目标作为简短标题"
                "（不超过30字，不要引号、不要\"标题：\"前缀，直接输出标题文字）：\n\n"
                f"用户请求：{user_message}\n"
                f"助手回复：{assistant_reply[:500]}"
            )
            result = await self.llm_manager.chat(
                messages=[{"role": "user", "content": title_prompt}],
                max_tokens=50,
                temperature=0.3,
            )
            if result.success and result.content:
                title = result.content.strip()[:30]
                if title:
                    await self.thread_mgr.update_title(thread_id, title)
                    return
        except Exception:
            logger.debug("[AgentService] Thread title generation failed, using fallback")

        # Fallback: use first sentence of user message
        fallback = user_message.split("。")[0].split("\n")[0].strip()[:30]
        if fallback:
            await self.thread_mgr.update_title(thread_id, fallback)

    async def delegate_subtask(
        self,
        parent_run: AgentRun,
        target_profile_id: str,
        message: str,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Run a child agent task and record the delegation on the parent run."""
        parent_context = self._safe_json_loads(parent_run.context_json, {})
        delegated_context = {
            **parent_context,
            **(context or {}),
            "parent_run_id": parent_run.id,
            "delegated_by_profile_id": parent_run.profile_id,
        }
        objective = message or f"执行来自父 run {parent_run.id} 的委派任务"
        child_result = await self.chat(
            session_id=parent_run.session_id,
            user_message=objective,
            context=delegated_context,
            profile_id=target_profile_id,
            parent_run_id=parent_run.id,
        )
        next_index = await self._next_run_step_index(parent_run.id)
        await self._record_run_step(
            parent_run.id,
            step_type="delegate_subtask",
            status="completed" if child_result.get("done") else "failed",
            session_id=parent_run.session_id,
            profile_id=parent_run.profile_id,
            order_index=next_index,
            summary=f"委派给 {target_profile_id}：{self._summarize_text(objective, 120)}",
            input_data={
                "target_profile_id": target_profile_id,
                "message": objective,
                "context": context or {},
            },
            output_data={
                "child_run_id": child_result.get("run_id"),
                "reply": child_result.get("reply"),
                "profile": child_result.get("profile"),
            },
            linked_objects=[
                {
                    "type": "agent_run",
                    "id": child_result.get("run_id"),
                    "relation": "child_run",
                }
            ] if child_result.get("run_id") else [],
            error="" if child_result.get("done") else "委派任务未完成",
        )
        parent_run.updated_at = datetime.utcnow()
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] _delegate_subtask flush failed (rollback): %s", exc)
            try:
                if self.session.in_transaction():
                    await self.session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return {
            "success": bool(child_result.get("done")),
            "parent_run_id": parent_run.id,
            "child_run_id": child_result.get("run_id"),
            "target_profile_id": target_profile_id,
            "result": child_result,
        }

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        memory_context: str,
        profile: dict[str, Any],
        context_summary: str = "",
        short_term_context: str = "",
        followup_resolution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.planner.plan(
            messages=messages,
            memory_context=memory_context,
            profile=profile,
            agent_system_prompt=AGENT_SYSTEM_PROMPT,
            context_summary=context_summary,
            short_term_context=short_term_context,
            followup_resolution=followup_resolution,
        )

    async def _build_failover_chain(
        self, profile: dict[str, Any]
    ) -> list[tuple[str | None, str | None]]:
        """Hermes-inspired: build ordered list of (provider, model) tuples to try.

        Primary: profile's explicit provider/model
        Fallback: same-type active AIConnectors from the database
        Last resort: no provider (use LLM manager default)
        """
        primary = (profile.get("provider") or None, profile.get("model") or None)
        chain = [primary]

        # Add fallback connectors from the database (same provider_type)
        profile_role = profile.get("role_type") or "assistant"
        provider_type = self._role_to_provider_type(profile_role)
        try:
            from app.db.models.ai_connector import AIConnector
            from sqlalchemy import String, cast
            from sqlalchemy import select as sa_select

            async with self.session.begin_nested():
                result = await self.session.execute(
                    sa_select(AIConnector).where(
                        AIConnector.is_active == True,
                        cast(AIConnector.provider_type, String) == str(provider_type),
                    ).limit(3)
                )
                connectors = list(result.scalars().all())
            for conn in connectors:
                fallback = (conn.provider, conn.default_model)
                if fallback not in chain:
                    chain.append(fallback)
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] _build_failover_chain skipped (DB table unavailable): %s", exc)
            # NOTE: Do NOT call session.rollback() here. The outer chat() method
            # handles transaction cleanup via per-phase commits and entry-level rollback.
            # Rolling back inside a failed query path can corrupt the async greenlet
            # context (especially with SQLite+aiosqlite) and cause MissingGreenlet.

        # Last resort: None for provider (LLM manager picks default)
        if (None, None) not in chain:
            chain.append((None, None))

        return chain

    def _build_tool_index_context(self, allowed_tools: list[str] | None) -> str:
        return self.planner._build_tool_index_context(allowed_tools)

    @staticmethod
    def _role_to_provider_type(role_type: str) -> str:
        """Map agent role_type to AI connector provider_type for failover matching."""
        type_map = {
            "writer": "llm",
            "character_designer": "llm",
            "storyboard_director": "llm",
            "asset_curator": "llm",
            "reviewer": "llm",
            "orchestrator": "llm",
            "director": "llm",
            "role_actor": "llm",
            "editor": "llm",
            "assistant": "llm",
            "image_generator": "image",
            "video_creator": "video",
        }
        return type_map.get(role_type, "llm")

    def _augment_context(self, context: dict[str, Any]) -> dict[str, Any]:
        project_id = str(context.get("project_id") or context.get("creative_project_id") or "").strip()
        if not project_id or context.get("creative_project_context"):
            return context
        try:
            chapter_number = context.get("chapter_number")
            pack = build_creative_project_context_pack(
                project_id,
                chapter_number=int(chapter_number) if chapter_number else None,
            )
            if pack:
                return {**context, "creative_project_context": pack}
        except Exception as exc:
            logger.warning("[AgentService] creative project context pack failed: %s", exc)
            return {
                **context,
                "creative_project_context_error": str(exc),
            }
        return context

    def _profile_context(self, profile: dict[str, Any]) -> dict[str, Any]:
        context: dict[str, Any] = {
            "agent_profile": {
                "id": profile.get("id"),
                "name": profile.get("name"),
                "role_type": profile.get("role_type"),
            }
        }
        default_project_id = str(profile.get("default_project_id") or "").strip()
        if default_project_id:
            context.setdefault("project_id", default_project_id)
            context.setdefault("creative_project_id", default_project_id)
            context["default_project_id"] = default_project_id
        default_workflow = str(profile.get("default_workflow") or "").strip()
        if default_workflow:
            context["default_workflow"] = default_workflow
        default_skill_ids = profile.get("default_skill_ids") or []
        if default_skill_ids:
            context["default_skill_ids"] = default_skill_ids
        return context

    async def _build_recent_run_context(self, session_id: str, current_run_id: str = "") -> list[dict[str, Any]]:
        if not session_id:
            return []
        try:
            result = await self.session.execute(
                select(AgentRun)
                .where(AgentRun.session_id == session_id, AgentRun.id != current_run_id)
                .order_by(AgentRun.created_at.desc())
                .limit(5)
            )
            runs = list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] recent run context skipped: %s", exc)
            return []

        items: list[dict[str, Any]] = []
        for run in runs:
            result_json = self._safe_json_loads(run.result_json or "{}", {})
            items.append(
                {
                    "run_id": run.id,
                    "status": run.status,
                    "objective": self._summarize_text(run.objective or "", limit=160),
                    "reply": self._summarize_text(str(result_json.get("reply") or ""), limit=240),
                    "tool_call_count": result_json.get("tool_call_count", 0),
                    "updated_at": run.updated_at.isoformat() if run.updated_at else "",
                }
            )
        return items

    def _build_short_term_context_text(
        self,
        messages: list[dict[str, Any]],
        effective_context: dict[str, Any],
        conversation_state: dict[str, Any],
        recent_run_context: list[dict[str, Any]],
    ) -> str:
        recent_messages = [
            {
                "role": str(message.get("role") or "user"),
                "content": self._summarize_text(str(message.get("content") or ""), limit=320),
            }
            for message in messages[-10:]
            if message.get("role") in {"user", "assistant", "system"}
        ]
        context_keys = sorted(
            key for key, value in (effective_context or {}).items()
            if value not in (None, "", [], {})
        )
        compact_context = {
            key: effective_context[key]
            for key in context_keys
            if key in {
                "agent_profile",
                "default_workflow",
                "default_skill_ids",
                "project_id",
                "creative_project_id",
                "default_project_id",
                "conversation_state",
            }
        }
        payload = {
            "message_count": len(messages),
            "recent_messages": recent_messages,
            "session_context_keys": context_keys[:30],
            "session_context": compact_context,
            "conversation_state": conversation_state,
            "recent_runs": recent_run_context,
        }
        return (
            "以下是当前 thread 的完整短期上下文摘要，必须优先用于消解本轮省略、补充、确认、修正、继续等短句。\n"
            "如果用户本轮没有重复完整目标，请从 recent_messages、conversation_state、session_context 和 recent_runs 中继承。\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )

    def _build_conversation_state(
        self,
        messages: list[dict[str, Any]],
        previous_state: Any = None,
    ) -> dict[str, Any]:
        """Build a compact thread state that survives across turns."""
        prior = previous_state if isinstance(previous_state, dict) else {}
        user_messages = [
            str(message.get("content") or "").strip()
            for message in messages
            if message.get("role") == "user" and str(message.get("content") or "").strip()
        ]
        current = user_messages[-1] if user_messages else ""
        previous_slots = prior.get("slots") if isinstance(prior.get("slots"), dict) else {}
        platform = self._extract_platform(current) if current else None
        keyword = self._extract_search_keyword(current) if current else ""
        if platform and self._is_platform_refinement_without_keyword(current):
            keyword = ""

        if not keyword:
            keyword = str(previous_slots.get("keyword") or "").strip()
        if not keyword:
            for candidate in reversed(user_messages[:-1]):
                keyword = self._extract_search_keyword(candidate)
                if keyword:
                    break

        platform_value = str(previous_slots.get("platform") or "").strip()
        platform_label = str(previous_slots.get("platform_label") or "").strip()
        if platform:
            platform_value, platform_label = platform

        active_intent = str(prior.get("active_intent") or "").strip()
        if keyword or platform_value or re.search(r"(搜|搜索|找|查|检索|search)", current, flags=re.I):
            active_intent = "platform_search"

        slots: dict[str, Any] = {}
        if keyword:
            slots["keyword"] = keyword
        if platform_value:
            slots["platform"] = platform_value
            slots["platform_label"] = platform_label or platform_value

        missing_slots: list[str] = []
        if active_intent == "platform_search":
            if not slots.get("keyword"):
                missing_slots.append("keyword")
            if not slots.get("platform"):
                missing_slots.append("platform")

        pending_action = prior.get("pending_action") if isinstance(prior.get("pending_action"), dict) else {}
        if active_intent == "platform_search" and not missing_slots:
            pending_action = {
                "type": "tool_call_ready",
                "tool_name": "search_platform_sources",
                "arguments": {
                    "platform": slots["platform"],
                    "keyword": slots["keyword"],
                    "max_results": 20,
                },
            }
        elif missing_slots:
            pending_action = {
                "type": "await_user_slot",
                "missing_slots": missing_slots,
            }

        return {
            "version": 1,
            "active_intent": active_intent,
            "intent_label": "平台内容搜索" if active_intent == "platform_search" else "",
            "slots": slots,
            "missing_slots": missing_slots,
            "pending_action": pending_action,
            "last_user_message": current,
            "updated_at": datetime.utcnow().isoformat(),
        }

    def _build_followup_resolution(
        self,
        messages: list[dict[str, Any]],
        conversation_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve short follow-up turns such as "use B站" against the previous goal."""
        user_messages = [
            str(message.get("content") or "").strip()
            for message in messages
            if message.get("role") == "user" and str(message.get("content") or "").strip()
        ]
        if len(user_messages) < 2:
            return {}

        current = user_messages[-1]
        platform = self._extract_platform(current)
        if not platform:
            return {}

        slots = (conversation_state or {}).get("slots") if isinstance((conversation_state or {}).get("slots"), dict) else {}
        prior_keyword = str(slots.get("keyword") or "").strip()
        prior_message = ""
        if not prior_keyword:
            for candidate in reversed(user_messages[:-1]):
                keyword = self._extract_search_keyword(candidate)
                if keyword:
                    prior_keyword = keyword
                    prior_message = candidate
                    break

        if not prior_keyword:
            return {}

        compact_current = self._strip_platform_words(current)
        compact_current = re.sub(r"(有|用|走|调用|技能|工具|平台|搜索|搜|查|找|去|在|上|一下|可以|继续|就|吧|，|,|。|\s)+", "", compact_current, flags=re.I)
        if len(compact_current) > 8:
            return {}

        platform_value, platform_label = platform
        instruction = (
            f"上一轮用户的搜索目标是「{prior_keyword}」；本轮用户补充的平台/工具是「{platform_label}」。"
            f"请合并理解为：在 {platform_label} 搜索「{prior_keyword}」。不要再询问搜索关键词。"
        )
        return {
            "type": "platform_search_followup",
            "platform": platform_value,
            "platform_label": platform_label,
            "keyword": prior_keyword,
            "prior_message": prior_message,
            "current_message": current,
            "instruction": instruction,
        }

    def _extract_platform(self, text: str) -> tuple[str, str] | None:
        lowered = text.lower()
        aliases = [
            ("bili", "B站", ["b站", "b 站", "哔哩", "bilibili", "bili"]),
            ("xhs", "小红书", ["小红书", "xhs", "rednote"]),
            ("dy", "抖音", ["抖音", "douyin", "dy"]),
            ("ks", "快手", ["快手", "kuaishou", "ks"]),
            ("wb", "微博", ["微博", "weibo", "wb"]),
            ("zhihu", "知乎", ["知乎", "zhihu"]),
            ("wechat_mp", "公众号", ["公众号", "微信公号", "wechat"]),
        ]
        for value, label, terms in aliases:
            if any(term.lower() in lowered for term in terms):
                return value, label
        return None

    def _is_platform_refinement_without_keyword(self, text: str) -> bool:
        compact = self._strip_platform_words(text)
        compact = re.sub(
            r"(有|用|走|调用|技能|工具|平台|搜索|搜|查|找|去|在|上|一下|可以|继续|就|吧|，|,|。|\s)+",
            "",
            compact,
            flags=re.I,
        )
        return len(compact) <= 2

    def _strip_platform_words(self, text: str) -> str:
        result = text
        for term in [
            "B站", "b站", "b 站", "哔哩哔哩", "哔哩", "bilibili", "bili",
            "小红书", "xhs", "rednote", "抖音", "douyin", "dy", "快手", "kuaishou", "ks",
            "微博", "weibo", "wb", "知乎", "zhihu", "公众号", "微信公号", "wechat",
        ]:
            result = re.sub(re.escape(term), "", result, flags=re.I)
        return result

    def _extract_search_keyword(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if not re.search(r"(搜|搜索|找|查|检索|search|视频|素材|解说)", raw, flags=re.I):
            return ""
        cleaned = self._strip_platform_words(raw)
        cleaned = re.sub(r"^(请|麻烦|帮我|帮忙|给我|我要|想要|去|在|从|用|到|帮)?\s*", "", cleaned)
        cleaned = re.sub(r"^(搜索|搜|找|查找|查|检索|search)\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"(帮我|帮忙|一下|看看|能不能|可以吗|吗|么|呢|吧)", "", cleaned)
        cleaned = cleaned.strip(" ：:，,。.!！?？\n\t")
        if not cleaned or len(cleaned) < 2:
            return ""
        if len(cleaned) > 80:
            cleaned = cleaned[:80].strip()
        return cleaned

    def _tool_call_from_followup_resolution(
        self,
        state: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any] | None:
        resolution = state.get("followup_resolution") or {}
        if resolution.get("type") != "platform_search_followup":
            return None
        tool_name = "search_platform_sources"
        allowed_tools = profile.get("allowed_tools") or []
        if allowed_tools and "*" not in allowed_tools and tool_name not in allowed_tools:
            return None
        if not ToolRegistry.get_tool(tool_name):
            return None
        args = {
            "platform": resolution.get("platform") or "",
            "keyword": resolution.get("keyword") or "",
            "max_results": 20,
        }
        if not args["platform"] or not args["keyword"]:
            return None
        return {
            "id": f"followup_{uuid.uuid4().hex[:8]}",
            "name": tool_name,
            "arguments": json.dumps(args, ensure_ascii=False),
        }

    def _repair_tool_call_with_followup(
        self,
        tool_call: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        resolution = state.get("followup_resolution") or {}
        if resolution.get("type") != "platform_search_followup":
            return tool_call
        tool_name, args = self._tool_name_and_args(tool_call)
        if tool_name not in {"search_platform_sources", "search_platform_sources_enhanced"}:
            return tool_call
        repaired = dict(args)
        repaired.setdefault("platform", resolution.get("platform") or "")
        repaired.setdefault("keyword", resolution.get("keyword") or "")
        if repaired == args:
            return tool_call
        next_call = dict(tool_call)
        if "function" in next_call:
            function = dict(next_call.get("function") or {})
            function["arguments"] = json.dumps(repaired, ensure_ascii=False)
            next_call["function"] = function
        else:
            next_call["arguments"] = json.dumps(repaired, ensure_ascii=False)
        return next_call

    def _parse_tool_calls(self, content: str) -> list[dict[str, Any]]:
        return self.planner.parse_tool_calls(content)

    async def _execute_tool_call(
        self,
        tool_call: dict[str, Any],
        session_id: str,
        profile: dict[str, Any],
    ) -> ToolCallResult:
        return await self.tool_executor.execute_tool_call(
            tool_call,
            profile,
            log_callback=lambda tool_name, tool_args, tool_result: self._log_tool_call(
                session_id,
                tool_name,
                tool_args,
                tool_result,
            ),
        )

    def _tool_name_and_args(self, tool_call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return self.tool_executor.tool_name_and_args(tool_call)

    def _tool_call_id(self, tool_call: dict[str, Any]) -> str:
        return self.tool_executor.tool_call_id(tool_call)

    def _tool_call_to_dict(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        return self.tool_executor.tool_call_to_dict(tool_call)

    def _tool_result_observation(
        self,
        tool_call: dict[str, Any],
        result: ToolCallResult,
    ) -> dict[str, str]:
        """Feed fallback JSON tool results back as normal context.

        Native OpenAI tool messages require a preceding assistant message with
        matching tool_calls. Our current fallback parser reads JSON tool calls
        from text, so sending role=tool would break OpenAI-compatible backends.
        """
        payload = result.result if result.success else {"error": result.error}
        content = json.dumps(payload, ensure_ascii=False, default=str)
        tool_name = result.tool_name or self.tool_executor.tool_name_and_args(tool_call)[0]
        return {
            "role": "user",
            "content": (
                f"[工具结果]\n"
                f"工具: {tool_name}\n"
                f"调用ID: {self.tool_executor.tool_call_id(tool_call)}\n"
                f"状态: {'成功' if result.success else '失败'}\n"
                f"返回: {content}\n\n"
                "请基于这个工具结果继续推理；如果还需要工具，请继续返回 tool_calls JSON，"
                "否则直接给用户最终回答。"
            ),
        }

    async def _log_tool_call(
        self,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        result: ToolCallResult,
    ) -> None:
        log = AgentToolCall(
            session_id=session_id,
            tool_name=tool_name,
            tool_args=json.dumps(tool_args, ensure_ascii=False),
            result=json.dumps(result.result, ensure_ascii=False)[:2000] if result.result is not None else None,
            success=result.success,
            duration_ms=result.duration_ms,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(log)
                await self.session.flush()
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] _log_tool_call failed (rollback): %s", exc)
            try:
                if self.session.in_transaction():
                    await self.session.rollback()
            except Exception:  # noqa: BLE001
                pass

    async def _create_run(
        self,
        session_id: str,
        profile_id: str,
        objective: str,
        context: dict[str, Any],
        parent_run_id: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            id=uuid.uuid4().hex,
            user_id=self.user_id,
            session_id=session_id,
            profile_id=profile_id,
            parent_run_id=parent_run_id,
            status="running",
            objective=objective,
            context_json=json.dumps(context or {}, ensure_ascii=False, default=str),
            result_json="{}",
        )
        try:
            async with self.session.begin_nested():
                self.session.add(run)
                await self.session.flush()
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] _create_run failed (rollback): %s", exc)
            try:
                if self.session.in_transaction():
                    await self.session.rollback()
            except Exception:  # noqa: BLE001
                pass
            raise
        return run

    async def _create_memory_snapshot(self, state: dict[str, Any]) -> None:
        """Persist the exact memory/tool context frozen for this run."""
        run: AgentRun = state["run"]
        profile = state["profile"]
        memory_context = state.get("memory_context") or ""
        context_summary = state.get("context_summary") or ""
        tool_index_text = state.get("tool_index_context") or ""
        snapshot = AgentMemorySnapshot(
            user_id=self.user_id,
            run_id=run.id,
            session_id=state["session_id"],
            profile_id=str(profile.get("id") or ""),
            memory_context=memory_context,
            context_summary=context_summary,
            tool_index_text=tool_index_text,
            snapshot_json=json.dumps(
                {
                    "profile": {
                        "id": profile.get("id"),
                        "name": profile.get("name"),
                        "role_type": profile.get("role_type"),
                    },
                    "default_skill_ids": state["effective_context"].get("default_skill_ids") or profile.get("default_skill_ids") or [],
                    "message_count": len(state.get("messages") or []),
                    "conversation_state": state.get("conversation_state") or {},
                    "recent_run_context": state.get("recent_run_context") or [],
                    "short_term_context": state.get("short_term_context") or "",
                    "memory_context_chars": len(memory_context),
                    "tool_index_chars": len(tool_index_text),
                    "context_summary_chars": len(context_summary),
                },
                ensure_ascii=False,
                default=str,
            ),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(snapshot)
                await self.session.flush()
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] _create_memory_snapshot failed (rollback): %s", exc)

    async def _create_thread_context_snapshot(self, state: dict[str, Any]) -> None:
        """Persist the thread-root context snapshot with partitioned sections (M4.3)."""
        try:
            messages = state.get("messages") or []
            recent_messages = [
                {
                    "role": str(item.get("role") or ""),
                    "content": self._summarize_text(str(item.get("content") or ""), limit=320),
                }
                for item in messages[-10:]
                if isinstance(item, dict) and item.get("role") in {"user", "assistant", "system"}
            ]
            effective_context = state.get("effective_context") or {}
            project_id = effective_context.get("project_id") or effective_context.get("creative_project_id") or ""

            sections = {
                "short_term_context": {
                    "message_count": len(messages),
                    "recent_messages": recent_messages,
                },
                "conversation_state": {
                    "state": state.get("conversation_state") or {},
                    "followup_resolution": state.get("followup_resolution") or {},
                    "pending_action": (state.get("conversation_state") or {}).get("pending_action") or {},
                },
                "project_context": {
                    "project_id": project_id,
                    "context_summary": state.get("context_summary") or "",
                    "recent_run_context": state.get("recent_run_context") or [],
                } if project_id else {},
                "memory_context": {
                    "chars": len(state.get("memory_context") or ""),
                    "has_memory": bool(state.get("memory_context")),
                },
                "tool_index": {
                    "routed_skills": [
                        {"skill_id": item.skill_id, "reason": item.reason, "score": item.score}
                        for item in (state.get("routed_skills") or [])
                    ],
                    "tool_index_chars": len(state.get("tool_index_context") or ""),
                },
            }

            payload = {
                "thread_id": state.get("thread_id") or state.get("session_id"),
                "run_id": state["run"].id,
                "profile": {
                    "id": state.get("profile", {}).get("id"),
                    "name": state.get("profile", {}).get("name"),
                    "role_type": state.get("profile", {}).get("role_type"),
                },
                "sections": sections,
                "effective_context_keys": sorted(
                    key for key, value in effective_context.items()
                    if value not in (None, "", [], {})
                ) if isinstance(effective_context, dict) else [],
            }
            await self.thread_mgr.create_context_snapshot(
                thread_id=state.get("thread_id") or state["session_id"],
                run_id=state["run"].id,
                kind="planning",
                context=payload,
                summary=self._summarize_text(state.get("short_term_context") or state.get("context_summary") or "", limit=500),
                token_estimate=max(1, len(json.dumps(payload, ensure_ascii=False, default=str)) // 4),
            )
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] _create_thread_context_snapshot failed: %s", exc)

    async def _record_run_step(
        self,
        run_id: str,
        step_type: str,
        status: str = "completed",
        session_id: str = "",
        profile_id: str = "",
        order_index: int = 0,
        tool_name: str = "",
        summary: str = "",
        input_data: Any = None,
        output_data: Any = None,
        linked_objects: list[dict[str, Any]] | None = None,
        error: str = "",
        duration_ms: int = 0,
    ) -> AgentRunStep | None:
        """记录单个运行步骤，使用嵌套事务隔离单步失败。

        若本步 INSERT 失败（事务已中止、约束冲突等），自动回滚到 savepoint
        而非污染整个事务，保证后续业务逻辑仍可执行。返回 None 表示步骤
        落库失败但调用方不应崩溃。
        """
        step = AgentRunStep(
            run_id=run_id,
            session_id=session_id,
            profile_id=profile_id,
            step_type=step_type,
            status=status,
            order_index=order_index,
            tool_name=tool_name,
            summary=summary[:1000],
            input_json=json.dumps(input_data if input_data is not None else {}, ensure_ascii=False, default=str),
            output_json=json.dumps(output_data if output_data is not None else {}, ensure_ascii=False, default=str),
            linked_objects_json=json.dumps(linked_objects or [], ensure_ascii=False, default=str),
            error=error,
            duration_ms=duration_ms,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(step)
                await self.session.flush()
            return step
        except SQLAlchemyError as exc:
            logger.warning(
                "[AgentService] _record_run_step failed (step_type=%s, run_id=%s): %s",
                step_type, run_id, exc,
            )
            return None

    async def _next_run_step_index(self, run_id: str) -> int:
        from sqlalchemy import select

        try:
            result = await self.session.execute(
                select(AgentRunStep)
                .where(AgentRunStep.run_id == run_id)
                .order_by(AgentRunStep.order_index.desc(), AgentRunStep.id.desc())
                .limit(1)
            )
            last = result.scalar_one_or_none()
            return (last.order_index + 1) if last else 0
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] _next_run_step_index query failed, defaulting to 0: %s", exc)
            try:
                if self.session.in_transaction():
                    await self.session.rollback()
            except Exception:  # noqa: BLE001
                pass
            return 0

    async def _finish_run(
        self,
        run: AgentRun,
        status: str,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        run.status = status
        run.result_json = json.dumps(result or {}, ensure_ascii=False, default=str)
        run.error = error
        run.finished_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except SQLAlchemyError as exc:
            logger.warning("[AgentService] _finish_run flush failed (rollback): %s", exc)
            try:
                if self.session.in_transaction():
                    await self.session.rollback()
            except Exception:  # noqa: BLE001
                pass

    def _summarize_text(self, text: str, limit: int = 180) -> str:
        compact = " ".join(str(text or "").split())
        return compact[:limit] + ("..." if len(compact) > limit else "")

    def _safe_json_loads(self, value: str, fallback: Any) -> Any:
        try:
            return json.loads(value or "")
        except Exception:
            return fallback

    def _summarize_tool_result(self, result: ToolCallResult) -> str:
        if self.tool_executor.is_pending_confirmation(result):
            payload = result.result if isinstance(result.result, dict) else {}
            return f"工具 {result.tool_name} 等待确认：{payload.get('risk_level') or 'high'}"
        if not result.success:
            return f"工具 {result.tool_name} 执行失败：{result.error or '未知错误'}"
        payload = result.result
        if isinstance(payload, list):
            return f"工具 {result.tool_name} 返回 {len(payload)} 条记录"
        if isinstance(payload, dict):
            keys = list(payload.keys())
            title = payload.get("title") or payload.get("name") or payload.get("id")
            if title:
                return f"工具 {result.tool_name} 返回：{title}"
            return f"工具 {result.tool_name} 返回字段：{'、'.join(keys[:6])}"
        return f"工具 {result.tool_name} 执行完成"

    def _is_pending_confirmation(self, result: ToolCallResult) -> bool:
        return self.tool_executor.is_pending_confirmation(result)

    def _extract_linked_objects(self, result: ToolCallResult) -> list[dict[str, Any]]:
        payload = result.result
        objects: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add(kind: str, identifier: Any, title: Any = "", relation: str = "") -> None:
            if identifier is None or identifier == "":
                return
            item_id = str(identifier)
            key = (kind, item_id)
            if key in seen:
                return
            seen.add(key)
            objects.append(
                {
                    "type": kind,
                    "id": item_id,
                    "title": str(title or item_id),
                    "relation": relation or "result",
                }
            )

        def scan(value: Any, relation: str = "result") -> None:
            if isinstance(value, list):
                for item in value:
                    scan(item, relation)
                return
            if not isinstance(value, dict):
                return

            project_id = value.get("project_id") or value.get("creative_project_id")
            if not project_id and relation == "project":
                project_id = value.get("id")
            if project_id:
                add("project", project_id, value.get("project_title") or value.get("title") or project_id, relation)
            if value.get("chapter_number") is not None:
                add("chapter", value.get("chapter_number"), value.get("chapter_title") or value.get("title") or f"第 {value.get('chapter_number')} 章", relation)
            asset_id = value.get("asset_id") or (value.get("asset") or {}).get("id")
            if not asset_id and relation in {"asset", "assets", "reference_assets"}:
                asset_id = value.get("id")
            if asset_id:
                add("asset", asset_id, value.get("asset_title") or value.get("title") or value.get("name") or asset_id, relation)
            if value.get("version_id"):
                add("asset_version", value.get("version_id"), value.get("version_id"), relation)
            if value.get("task_id"):
                add("task", value.get("task_id"), value.get("task_type") or value.get("task_id"), relation)
            if value.get("id") and result.tool_name.startswith("get_asset"):
                add("asset", value.get("id"), value.get("title") or value.get("name") or value.get("id"), relation)
            if value.get("content_type") and value.get("id"):
                add("project_content", value.get("id"), value.get("title") or value.get("content_type"), relation)

            for key, nested in value.items():
                if key in {"project", "asset", "assets", "contents", "cards", "chapters", "characters", "tasks", "result", "data", "track", "bgm_track"}:
                    scan(nested, key)

        scan(payload)
        return objects[:30]

    def _tool_result_to_dict(self, result: ToolCallResult) -> dict[str, Any]:
        summary = self._summarize_tool_result(result)
        return {
            "tool_name": result.tool_name,
            "name": result.tool_name,
            "success": result.success,
            "result": result.result,
            "summary": summary,
            "raw_json": result.result,
            "linked_objects": self._extract_linked_objects(result),
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    def _extract_memory_candidates(
        self,
        user_message: str,
        reply: str = "",
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Extract user-confirmed memory candidates without writing them.

        This conservative first pass only proposes explicit user preferences,
        project rules, and durable facts. The user must confirm before anything
        is written to agent_memories.
        """
        text = " ".join(str(user_message or "").split())
        if not text:
            return []

        lowered = text.lower()
        triggers = [
            "记住",
            "以后",
            "后续",
            "默认",
            "偏好",
            "规则",
            "不要",
            "别",
            "统一",
            "保持",
            "使用",
            "用",
            "always",
            "remember",
            "prefer",
            "default",
            "never",
        ]
        if not any(trigger in lowered or trigger in text for trigger in triggers):
            return []

        memory_type = "preference"
        if any(token in text for token in ["项目", "创作项目", "角色", "分镜", "素材", "画风", "视觉"]):
            memory_type = "project_context"
        if any(token in text for token in ["是", "账号", "路径", "地址", "ID", "id"]) and "不要" not in text:
            memory_type = "fact" if memory_type != "project_context" else memory_type

        project_id = str((context or {}).get("project_id") or (context or {}).get("creative_project_id") or "").strip()
        prefix = "agent"
        if project_id:
            prefix = f"project.{project_id}"
        elif memory_type == "preference":
            prefix = "user.preference"
        elif memory_type == "project_context":
            prefix = "project.rule"

        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in text[:36]).strip("_")
        key = f"{prefix}.{normalized or stamp}"
        if len(key) > 96:
            key = f"{prefix}.{stamp}"

        importance = 8 if any(token in text for token in ["必须", "不要", "默认", "统一", "保持", "always", "never"]) else 6
        return [
            {
                "key": key,
                "value": text,
                "type": memory_type,
                "memory_type": memory_type,
                "importance": importance,
                "reason": "用户表达了可复用的偏好、规则或事实，需确认后保存。",
                "source": "agent_run",
            }
        ]
