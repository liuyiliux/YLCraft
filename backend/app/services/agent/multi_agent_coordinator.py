"""Declarative scene-simulation coordinator for YLCraft Agent Center.

Scene simulation now runs through the declarative ``scene-sim`` team template
via ``TeamComposer`` → ``SubagentOrchestrator``: each role (divine-director /
role-actor / story-editor / creative-director) is an isolated child agent with
its own async session. This replaces the previous hard-coded coordinator that
called ``AgentService.chat`` on one shared session across concurrent actors.

Pipeline: Divine Director → Role Actors (parallel) → Story Editor → Writer (join).
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models.creative_project import ProjectContent

logger = logging.getLogger("ylcraft.agent.multi_agent")


@dataclasses.dataclass
class SimulationConfig:
    """Configuration for one multi-agent simulation run."""

    project_id: str | None = None
    scene_context: str = ""  # chapter/scene description
    characters_of_interest: list[str] = dataclasses.field(default_factory=list)
    iteration_budget_per_agent: int = 8
    store_as_candidate: bool = True


class MultiAgentCoordinator:
    """Orchestrate a multi-agent scene simulation via a declarative team template."""

    def __init__(self, agent_service):
        """agent_service is an instance of AgentService (or compatible)."""
        self._svc = agent_service

    async def run_team(
        self,
        template_id: str,
        config: SimulationConfig,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """Run a declarative team template through the shared orchestrator.

        The team template drives isolated child runs with independent sessions;
        role actors expand per character and run in parallel under the budget
        policy, and the join role's output is persisted as a candidate.
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
            if not config.project_id or not config.store_as_candidate:
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
