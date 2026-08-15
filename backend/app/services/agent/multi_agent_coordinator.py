"""Multi-Agent Coordinator for YLCraft Agent Center Phase 5.

Orchestrates role-agent, director, editor, and writer agents in a scene
simulation pipeline. Each agent runs independently with its own profile,
tool set, and iteration budget, passing structured outputs to the next.

Pipeline: Divine Director → Role Actors (parallel) → Story Editor → Writer/Novelist

DeerFlow-inspired concurrent sub-agent execution:
  - Role actors run in parallel via asyncio.gather (one per character)
  - Sub-agent limit imposed (default 3) — DeerFlow SubagentLimitMiddleware pattern
  - Each actor creates its own independent agent session, no state shared
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models.creative_project import ProjectContent

logger = logging.getLogger("ylcraft.agent.multi_agent")

# DeerFlow-inspired: max concurrent sub-agents
MAX_PARALLEL_ROLE_ACTORS = 3


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class AgentSlot:
    """A slot in the pipeline for one agent to run."""

    profile_id: str
    role_label: str  # human-readable label, e.g. "天意总导演"
    agent_input: str  # the prompt sent to this agent
    output: str | None = None  # agent's final text output
    step_ids: list[str] = dataclasses.field(default_factory=list)
    duration_ms: float = 0.0


@dataclasses.dataclass
class SimulationConfig:
    """Configuration for one multi-agent simulation run."""

    project_id: str | None = None
    scene_context: str = ""  # chapter/scene description
    characters_of_interest: list[str] = dataclasses.field(default_factory=list)
    iteration_budget_per_agent: int = 8
    store_as_candidate: bool = True


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class MultiAgentCoordinator:
    """Orchestrate a multi-agent scene simulation.

    The coordinator runs agents in sequence, using each agent's output as
    context for the next. All outputs are saved as candidate versions in
    the creative project, never overwriting approved content.

    Usage::

        coordinator = MultiAgentCoordinator(agent_service)
        result = await coordinator.run_scene_simulation(config)

    See Phase 5 of creative-project-optimization-roadmap for motivation.
    """

    def __init__(self, agent_service):
        """agent_service is an instance of AgentService (or compatible)."""
        self._svc = agent_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_scene_simulation(
        self, config: SimulationConfig, user_id: str = "default"
    ) -> dict[str, Any]:
        """Execute the full multi-agent pipeline for one scene.

        Returns a dict with:
          success, pipeline_steps (list of AgentSlot dicts),
          candidate_version_id, total_duration_ms, project_id
        """
        started = time.monotonic()
        slots: list[AgentSlot] = []

        logger.info(
            "[MultiAgent] Starting scene simulation for project=%s, chars=%s",
            config.project_id,
            config.characters_of_interest,
        )

        try:
            # --- Step 1: Divine Director ---
            director_output = await self._run_divine_director(config, user_id)
            slots.append(director_output)

            # --- Step 2: Role Actors (parallel per character, DeerFlow-inspired) ---
            actor_slots = await self._run_role_actors(config, director_output.output, user_id)
            slots.extend(actor_slots)

            # --- Step 3: Story Editor ---
            editor_output = await self._run_story_editor(config, slots, user_id)
            slots.append(editor_output)

            # --- Step 4: Writer (optional, if we have enough context) ---
            if config.project_id and editor_output.output:
                writer_output = await self._run_writer_synthesis(config, slots, user_id)
                slots.append(writer_output)

        except Exception as exc:
            logger.error("[MultiAgent] Pipeline failed at step %d: %s", len(slots), exc)
            return {
                "success": False,
                "error": str(exc),
                "pipeline_steps": [dataclasses.asdict(s) for s in slots],
                "total_duration_ms": int((time.monotonic() - started) * 1000),
            }

        total_ms = int((time.monotonic() - started) * 1000)

        # Store candidate version
        candidate_id = None
        if config.store_as_candidate and config.project_id:
            candidate_id = await self._store_candidate(config, slots)

        logger.info(
            "[MultiAgent] Pipeline complete in %d ms, %d steps, candidate=%s",
            total_ms,
            len(slots),
            candidate_id,
        )

        return {
            "success": True,
            "project_id": config.project_id,
            "pipeline_steps": [dataclasses.asdict(s) for s in slots],
            "candidate_version_id": candidate_id,
            "total_duration_ms": total_ms,
        }

    # ------------------------------------------------------------------
    # Declarative team path (agent-team-composition)
    # ------------------------------------------------------------------

    async def run_team(
        self,
        template_id: str,
        config: SimulationConfig,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """Run a declarative team template through the shared orchestrator.

        This is the migration target for ``run_scene_simulation``: the same
        templates (``scene-sim`` / ``writer-room-team``) drive isolated child
        runs with independent sessions, instead of the coordinator calling
        ``AgentService.chat`` on one shared session.
        """
        import uuid as _uuid

        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import sessionmaker

        from app.db.models.agent import AgentRun
        from app.services.agent.runtime.delegation import SubagentExecutor, SubagentOrchestrator
        from app.services.agent.team_composer import TeamComposer

        session = self._svc.session
        parent_run = AgentRun(
            id=f"team_{_uuid.uuid4().hex[:24]}",
            user_id=user_id,
            session_id=f"team_sess_{_uuid.uuid4().hex[:12]}",
            profile_id="creative-director",
            run_kind="primary",
            status="running",
            objective=f"团队推演 {template_id}",
            context_json=json.dumps(
                {"project_id": config.project_id, "scene_context": config.scene_context},
                ensure_ascii=False,
            ),
        )
        session.add(parent_run)
        await session.commit()

        session_factory = sessionmaker(
            bind=session.bind,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        def service_factory(child_session: AsyncSession, uid: str):
            from app.services.agent.service import AgentService

            child = AgentService(child_session, user_id=uid)
            child._llm_manager = getattr(self._svc, "_llm_manager", None)
            return child

        executor = SubagentExecutor(session_factory, service_factory=service_factory)
        orchestrator = SubagentOrchestrator(session, executor)
        composer = TeamComposer(orchestrator)
        result = await composer.run(
            template_id,
            parent_run,
            inputs={
                "project_id": config.project_id,
                "scene_context": config.scene_context,
                "characters": config.characters_of_interest,
            },
            user_id=user_id,
        )
        candidate_id = await self._store_team_candidate(config, result)
        return {
            "success": bool(result.get("success")),
            "project_id": config.project_id,
            "team": result,
            "candidate_version_id": candidate_id,
        }

    async def _store_team_candidate(
        self,
        config: SimulationConfig,
        team_result: dict[str, Any],
    ) -> str | None:
        """Persist the joined team observation as a scene-simulation candidate."""
        try:
            if not config.project_id:
                return None
            session = getattr(self._svc, "session", None)
            if session is None:
                return None
            payload = {
                "pipeline": "team_template_v1",
                "team_template_id": team_result.get("team_template_id"),
                "project_id": config.project_id,
                "candidate": True,
                "approved": False,
                "scene_context": config.scene_context,
                "joined_observation": team_result.get("joined_observation"),
                "delegations": team_result.get("delegations") or [],
            }
            latest_version = await session.scalar(
                select(func.max(ProjectContent.version)).where(
                    ProjectContent.project_id == config.project_id,
                    ProjectContent.content_type == "scene_simulation_candidate",
                )
            )
            candidate = ProjectContent(
                project_id=config.project_id,
                content_type="scene_simulation_candidate",
                title="多智能体团队推演候选",
                data_json=json.dumps(payload, ensure_ascii=False, default=str),
                text_content=str(team_result.get("joined_observation") or ""),
                version=int(latest_version or 0) + 1,
                is_locked=False,
            )
            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)
            return str(candidate.id)
        except SQLAlchemyError as exc:
            session = getattr(self._svc, "session", None)
            if session is not None:
                await session.rollback()
            logger.warning("[MultiAgent] Could not store team candidate: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("[MultiAgent] Could not store team candidate: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    async def _run_divine_director(
        self, config: SimulationConfig, user_id: str
    ) -> AgentSlot:
        """Step 1: Divine Director produces scene briefing with conflict/pacing/event directives.

        The director reads the project bible and scene context, then outputs
        structured briefing with: conflict triggers, pacing map, world events,
        character entry/exit cues.
        """
        prompt = self._build_director_prompt(config)
        slot = AgentSlot(
            profile_id="divine-director",
            role_label="天意总导演",
            agent_input=prompt,
        )
        slot.output, slot.step_ids, slot.duration_ms = await self._execute_agent(
            profile_id=slot.profile_id,
            user_message=prompt,
            user_id=user_id,
            budget=config.iteration_budget_per_agent,
        )
        return slot

    async def _run_role_actors(
        self, config: SimulationConfig, director_output: str | None, user_id: str
    ) -> list[AgentSlot]:
        """Step 2: Each role actor inhabits their character and produces reactions.

        DeerFlow-inspired: actors run in parallel via asyncio.gather with a
        concurrency cap (MAX_PARALLEL_ROLE_ACTORS). Each actor creates its own
        independent agent session — no shared state between characters.

        Characters read: their own character card + director briefing.
        Each produces: emotional state, inner monologue, dialogue candidate,
        action intent.
        """
        characters = config.characters_of_interest or []
        if not characters:
            return []

        # Build all actor prompts upfront
        actor_configs = []
        for char_name in characters:
            prompt = self._build_actor_prompt(char_name, director_output or "", config)
            actor_configs.append((char_name, prompt))

        logger.info(
            "[MultiAgent] Launching %d role actors (max_parallel=%d)",
            len(actor_configs), MAX_PARALLEL_ROLE_ACTORS,
        )

        # DeerFlow pattern: run in batches to respect concurrency limit
        slots: list[AgentSlot] = []
        for batch_start in range(0, len(actor_configs), MAX_PARALLEL_ROLE_ACTORS):
            batch = actor_configs[batch_start:batch_start + MAX_PARALLEL_ROLE_ACTORS]
            tasks = [
                self._execute_agent(
                    profile_id="role-actor",
                    user_message=prompt,
                    user_id=user_id,
                    budget=config.iteration_budget_per_agent,
                )
                for _, prompt in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (char_name, prompt), result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.error(
                        "[MultiAgent] Role actor %s failed: %s", char_name, result,
                    )
                    slot = AgentSlot(
                        profile_id="role-actor",
                        role_label=f"角色演员: {char_name}",
                        agent_input=prompt,
                        output=f"[错误] {result}",
                        duration_ms=0,
                    )
                else:
                    output, step_ids, duration_ms = result
                    slot = AgentSlot(
                        profile_id="role-actor",
                        role_label=f"角色演员: {char_name}",
                        agent_input=prompt,
                        output=output,
                        step_ids=step_ids,
                        duration_ms=duration_ms,
                    )
                slots.append(slot)

        return slots

    async def _run_story_editor(
        self, config: SimulationConfig, preceding_slots: list[AgentSlot], user_id: str
    ) -> AgentSlot:
        """Step 3: Story Editor reviews all preceding outputs for logic,
        character consistency, pacing, hooks, and imageability.
        """
        context = self._compile_pipeline_context(preceding_slots)
        prompt = (
            f"{config.scene_context}\n\n"
            f"------------------------\n"
            f"以下为前序智能体的输出摘要：\n\n{context}\n\n"
            f"------------------------\n"
            f"请逐维度检查（逻辑链/角色一致性/节奏/钩子/可画面化），"
            f"按格式输出：问题列表 + 逐条修改建议 + 全局评价(A/B/C)。"
        )
        slot = AgentSlot(
            profile_id="story-editor",
            role_label="编辑润色师",
            agent_input=prompt,
        )
        slot.output, slot.step_ids, slot.duration_ms = await self._execute_agent(
            profile_id=slot.profile_id,
            user_message=prompt,
            user_id=user_id,
            budget=config.iteration_budget_per_agent,
        )
        return slot

    async def _run_writer_synthesis(
        self, config: SimulationConfig, preceding_slots: list[AgentSlot], user_id: str
    ) -> AgentSlot:
        """Step 4: Creative Director synthesizes all outputs into scene outline."""
        context = self._compile_pipeline_context(preceding_slots)
        prompt = (
            f"项目ID: {config.project_id or '未知'}\n"
            f"场景上下文: {config.scene_context}\n\n"
            f"------------------------\n"
            f"前序智能体输出摘要：\n\n{context}\n\n"
            f"------------------------\n"
            f"请基于以上信息生成场景细纲：包含场景目标、冲突线、"
            f"角色出场顺序、关键对话节点、节奏断点和情绪曲线描述。"
            f"输出为结构化大纲，不要写成正文。"
        )
        slot = AgentSlot(
            profile_id="creative-director",
            role_label="创作导演（合成）",
            agent_input=prompt,
        )
        slot.output, slot.step_ids, slot.duration_ms = await self._execute_agent(
            profile_id=slot.profile_id,
            user_message=prompt,
            user_id=user_id,
            budget=config.iteration_budget_per_agent,
        )
        return slot

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_director_prompt(self, config: SimulationConfig) -> str:
        parts = [
            "【天意总导演任务】",
            f"项目: {config.project_id or '未指定'}",
            f"场景上下文: {config.scene_context}",
            f"关注角色: {', '.join(config.characters_of_interest) if config.characters_of_interest else '全部'}",
            "",
            "请读取项目圣经和已有设定，产出以下结构化指令：",
            "1. 冲突设计——本场景的核心冲突是什么？矛盾在哪里升级？",
            "2. 节奏地图——开场/发展/转折/高潮/收尾的强度分配。",
            "3. 世界事件——是否有需要触发的外部事件或世界规则介入？",
            "4. 角色调度——每个角色在本场景的出场顺序、状态变化和退场动机。",
            "5. 钩子建议——场景结尾应留下什么悬念或情感余韵。",
            "输出格式：每个指令单独成段，引用项目圣经的具体条目。",
        ]
        return "\n\n".join(parts)

    def _build_actor_prompt(
        self, char_name: str, director_briefing: str, config: SimulationConfig
    ) -> str:
        parts = [
            f"【角色演员任务：扮演 {char_name}】",
            f"项目: {config.project_id or '未指定'}",
            f"场景: {config.scene_context}",
            "",
            "导演指令：",
            director_briefing[:1500] if director_briefing else "（无导演指令）",
            "",
            "请先读取角色卡获取完整设定（目标、恐惧、知识、情感、关系、口吻），然后以该角色身份输出：",
            "1. 当前情绪状态——角色进入本场景时的内心感受。",
            "2. 目标/动机——角色在本场景中想要什么。",
            "3. 对话候选——角色可能说的 2-3 句台词（带口吻标记）。",
            "4. 行动意图——角色会做什么、走向哪里、与谁互动。",
            "输出格式：以上面 4 项分节，每节用自然语言描述。不要以第三人称概括角色，要以角色第一人称或深度代入视角输出内心世界。",
        ]
        return "\n\n".join(parts)

    def _compile_pipeline_context(self, slots: list[AgentSlot]) -> str:
        """Compile all agent outputs into a compact context for downstream agents."""
        lines: list[str] = []
        for i, s in enumerate(slots, 1):
            summary = str(s.output or "")[:800]
            lines.append(
                f"--- {s.role_label} ---\n{summary}\n"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Agent execution
    # ------------------------------------------------------------------

    async def _execute_agent(
        self,
        profile_id: str,
        user_message: str,
        user_id: str = "default",
        budget: int = 8,
    ) -> tuple[str, list[str], float]:
        """Run a single agent with the given prompt using AgentService.chat().

        Returns (output_text, step_ids, duration_ms).
        """
        import uuid

        started = time.monotonic()
        session_id = f"ma_{uuid.uuid4().hex[:12]}"
        try:
            result = await self._svc.chat(
                session_id=session_id,
                user_message=user_message,
                profile_id=profile_id,
            )
            output_text = result.get("answer") or result.get("content") or ""
            if isinstance(output_text, list):
                output_text = "\n".join(
                    str(item.get("content") or item) for item in output_text
                )
            step_ids = [
                str(s.get("id", "")) for s in (result.get("steps") or [])
            ]
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "[MultiAgent] Agent %s completed in %d ms, output_len=%d",
                profile_id,
                duration_ms,
                len(str(output_text)),
            )
            return str(output_text), step_ids, float(duration_ms)
        except Exception as exc:
            logger.error("[MultiAgent] Agent %s failed: %s", profile_id, exc)
            return f"[错误] {exc}", [], float((time.monotonic() - started) * 1000)

    async def _store_candidate(
        self, config: SimulationConfig, slots: list[AgentSlot]
    ) -> str | None:
        """Store the pipeline output as a candidate version in the creative project.

        Uses the creative project content update API to save the full pipeline
        output as a candidate (non-approved) version so the user can review later.
        """
        try:
            if not config.project_id:
                return None
            session = getattr(self._svc, "session", None)
            if session is None:
                return None

            pipeline_log = {
                "pipeline": "scene_simulation_v1",
                "project_id": config.project_id,
                "candidate": True,
                "approved": False,
                "scene_context": config.scene_context,
                "steps": [
                    {
                        "role": s.role_label,
                        "profile_id": s.profile_id,
                        "output": str(s.output or ""),
                        "duration_ms": s.duration_ms,
                    }
                    for s in slots
                ],
            }
            latest_version = await session.scalar(
                select(func.max(ProjectContent.version)).where(
                    ProjectContent.project_id == config.project_id,
                    ProjectContent.content_type == "scene_simulation_candidate",
                )
            )
            candidate = ProjectContent(
                project_id=config.project_id,
                content_type="scene_simulation_candidate",
                title="多智能体场景推演候选",
                data_json=json.dumps(pipeline_log, ensure_ascii=False),
                text_content=str(slots[-1].output or "") if slots else "",
                version=int(latest_version or 0) + 1,
                is_locked=False,
            )
            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)
            logger.info("[MultiAgent] Candidate stored: %s", candidate.id)
            return str(candidate.id)
        except SQLAlchemyError as exc:
            session = getattr(self._svc, "session", None)
            if session is not None:
                await session.rollback()
            logger.warning("[MultiAgent] Could not store candidate: %s", exc)
            return None
        except Exception as exc:
            logger.warning("[MultiAgent] Could not store candidate: %s", exc)
            return None
