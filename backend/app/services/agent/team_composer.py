"""Declarative agent team composer.

Turns a validated :class:`TeamTemplate` into a list of :class:`DelegatedTask`
instances and runs them through the shared :class:`SubagentOrchestrator`. This
replaces hard-coded multi-agent orchestration with composition: the same
template drives scene simulation and Writer Room team rehearsal.
"""

from __future__ import annotations

from typing import Any

from app.services.agent.runtime.delegation import DelegatedTask, SubagentOrchestrator
from app.services.agent.team_template import (
    TeamTemplate,
    TeamTemplateLoader,
    TeamTemplateValidator,
)


class TeamComposer:
    def __init__(
        self,
        orchestrator: SubagentOrchestrator,
        loader: TeamTemplateLoader | None = None,
    ):
        self.orchestrator = orchestrator
        self.loader = loader or TeamTemplateLoader()
        self.validator = TeamTemplateValidator()

    async def run(
        self,
        template_id: str,
        parent_run: Any,
        *,
        inputs: dict[str, Any] | None = None,
        user_id: str = "",
        join_strategy: str | None = None,
    ) -> dict[str, Any]:
        template = self.loader.load(template_id)
        self.validator.validate(template)
        return await self.run_template(
            template,
            parent_run,
            inputs=inputs,
            user_id=user_id,
            join_strategy=join_strategy,
        )

    async def run_template(
        self,
        template: TeamTemplate,
        parent_run: Any,
        *,
        inputs: dict[str, Any] | None = None,
        user_id: str = "",
        join_strategy: str | None = None,
    ) -> dict[str, Any]:
        from app.services.agent.scope import AgentScope

        tasks = self.build_tasks(template, inputs or {})
        strategy = join_strategy or template.join_strategy
        # Install a per-run agent-plane scope so downstream code can resolve the
        # team context without leaking it into module-level globals.
        with AgentScope.enter(
            host={},
            agent={"team_template": template.name, "join_strategy": strategy},
        ):
            result = await self.orchestrator.delegate(parent_run, tasks, join_strategy=strategy)
        result["team_template_id"] = template.name
        return result

    # ------------------------------------------------------------------
    # Pure task construction (no DB, no LLM) — unit-testable.
    # ------------------------------------------------------------------

    def build_tasks(self, template: TeamTemplate, inputs: dict[str, Any]) -> list[DelegatedTask]:
        role_instances: dict[str, list[dict[str, Any]]] = {
            role.id: self._resolve_role_instances(role, inputs) for role in template.roles
        }
        tasks: list[DelegatedTask] = []
        for role in template.roles:
            depends: tuple[str, ...] = tuple(
                instance["task_key"]
                for dep_id in role.depends_on
                for instance in role_instances.get(dep_id, [])
            )
            for instance in role_instances[role.id]:
                context = dict(instance["context"])
                if role.skills:
                    context["default_skill_ids"] = list(
                        dict.fromkeys(
                            list(context.get("default_skill_ids") or []) + list(role.skills)
                        )
                    )
                context["team_role_id"] = role.id
                tasks.append(
                    DelegatedTask(
                        task_key=instance["task_key"],
                        profile_id=role.profile,
                        objective=instance["objective"],
                        context=context,
                        depends_on=depends,
                        spawn_mode=role.spawn,
                    )
                )
        return tasks

    def _resolve_role_instances(self, role: Any, inputs: dict[str, Any]) -> list[dict[str, Any]]:
        if role.template:
            items = self._resolve_items(role, inputs)
            return [
                {
                    "task_key": f"{role.id}-{item.get('key') or idx + 1}",
                    "objective": self._build_objective(role, inputs, item),
                    "context": self._build_context(inputs, item),
                }
                for idx, item in enumerate(items)
            ]
        return [
            {
                "task_key": role.id,
                "objective": self._build_objective(role, inputs, None),
                "context": self._build_context(inputs, None),
            }
        ]

    def _resolve_items(self, role: Any, inputs: dict[str, Any]) -> list[dict[str, Any]]:
        source = (role.resolve or {}).get("source")
        if source == "project_characters":
            raw = inputs.get("characters") or inputs.get("project_characters") or []
            items: list[dict[str, Any]] = []
            for char in raw:
                if isinstance(char, str):
                    items.append({"key": char, "name": char})
                elif isinstance(char, dict):
                    name = char.get("name") or char.get("key") or char.get("id") or str(char)
                    items.append({"key": str(name), "name": str(name), "context": char})
                else:
                    items.append({"key": str(char), "name": str(char)})
            return items
        return []

    def _build_context(self, inputs: dict[str, Any], item: dict[str, Any] | None) -> dict[str, Any]:
        base = dict(inputs.get("context") or {})
        if item:
            extra = item.get("context") if isinstance(item.get("context"), dict) else {}
            base = {**base, **extra}
            base["resolved_item"] = item.get("name") or item.get("key")
        return base

    def _build_objective(self, role: Any, inputs: dict[str, Any], item: dict[str, Any] | None) -> str:
        parts: list[str] = []
        if role.persona:
            parts.append(role.persona)
        if inputs.get("scene_context"):
            parts.append(f"场景上下文：{inputs['scene_context']}")
        if inputs.get("project_id"):
            parts.append(f"项目 ID：{inputs['project_id']}")
        if item and item.get("name"):
            parts.append(f"请以「{item['name']}」的视角完成本场演绎。")
        if not parts:
            parts = [f"执行团队角色 {role.id} 的任务"]
        return "\n".join(parts)
