"""Bridge user-visible production plans to the shared Agent team runtime."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from app.services.agent.skill_loader import SkillPackageLoader
from app.services.agent.team_template import BudgetSpec, RoleSpec, TeamTemplate, TeamTemplateError, TeamTemplateValidator


class ProductionPlanTeamError(ValueError):
    """The selected production-plan nodes cannot form an executable team."""


# Profiles remain the authority boundary for tools.  A capability role selects
# procedural Skills; it never gives a child direct access to provider secrets.
ROLE_PROFILE_IDS = {
    "story-designer": "divine-director",
    "script-writer": "novel-writer",
    "visual-director": "storyboard-director",
    "character-director": "character-designer",
    "storyboard-director": "storyboard-director",
    "image-producer": "character-designer",
    "video-producer": "storyboard-director",
    "platform-adapter": "creative-director",
    "editorial-reviewer": "quality-reviewer",
}


class ProductionPlanTeamComposer:
    """Compile a selected, dependency-closed plan slice into a TeamTemplate.

    The parent creative-director Run is the director.  Each selected plan node
    becomes one isolated specialist Run and the existing TeamComposer joins
    their observations back into that parent.  We intentionally require a
    bounded explicit selection because the shared delegation policy limits a
    single team to six children; a plan can contain many more nodes and should
    be advanced stage by stage rather than silently truncating it.
    """

    def __init__(self, skill_loader: SkillPackageLoader | None = None):
        self.skill_loader = skill_loader or SkillPackageLoader()

    def build_template(
        self,
        plan: dict[str, Any],
        *,
        node_ids: Iterable[str],
        include_dependencies: bool = True,
    ) -> TeamTemplate:
        nodes = self._nodes_by_id(plan)
        selected = self._selected_nodes(nodes, node_ids, include_dependencies=include_dependencies)
        if len(selected) > 6:
            raise ProductionPlanTeamError(
                "本次计划编排最多执行 6 个节点；请按阶段选择更小的节点集合"
            )

        skills_by_role = self._skills_by_role()
        dependents = {
            dependency
            for node in selected
            for dependency in node.get("depends_on") or []
            if dependency in {item["id"] for item in selected}
        }
        leaf_ids = [node["id"] for node in selected if node["id"] not in dependents]
        join_node_id = leaf_ids[-1] if leaf_ids else selected[-1]["id"]

        roles: list[RoleSpec] = []
        for node in selected:
            node_id = node["id"]
            capability_role = str(node.get("specialist_role") or "").strip()
            profile_id = ROLE_PROFILE_IDS.get(capability_role)
            if not profile_id:
                raise ProductionPlanTeamError(f"节点 {node_id} 的专业角色不受支持：{capability_role or '未填写'}")
            role_id = self._role_id(node_id)
            roles.append(
                RoleSpec(
                    id=role_id,
                    profile=profile_id,
                    persona=self._node_objective(node),
                    skills=skills_by_role.get(capability_role, []),
                    spawn="fork",
                    depends_on=[
                        self._role_id(dependency)
                        for dependency in node.get("depends_on") or []
                        if dependency in {item["id"] for item in selected}
                    ],
                    join=node_id == join_node_id,
                )
            )

        template = TeamTemplate(
            name=f"production-plan-{str(plan.get('plan_version') or 'draft')}",
            version=1,
            roles=roles,
            join_strategy="all",
            budget=BudgetSpec(max_children=6, max_concurrent=3),
        )
        try:
            TeamTemplateValidator().validate(template)
        except TeamTemplateError as exc:
            raise ProductionPlanTeamError(str(exc)) from exc
        return template

    def _skills_by_role(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for package in self.skill_loader.load_packages():
            for role in package.creative.get("capability_roles", []):
                result.setdefault(str(role), []).append(package.name)
        return {role: sorted(set(skill_ids)) for role, skill_ids in result.items()}

    @staticmethod
    def _nodes_by_id(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw_nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
        result: dict[str, dict[str, Any]] = {}
        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                continue
            node_id = str(raw_node.get("id") or "").strip()
            if not node_id:
                continue
            result[node_id] = dict(raw_node, id=node_id)
        if not result:
            raise ProductionPlanTeamError("当前生产计划没有可执行节点")
        return result

    def affected_nodes(self, plan: dict[str, Any], *, changed_node_ids: Iterable[str]) -> list[dict[str, str]]:
        """Return changed nodes plus all downstream plan nodes in plan order."""
        nodes = self._nodes_by_id(plan)
        changed = self._requested_node_ids(nodes, changed_node_ids)
        dependents: dict[str, list[str]] = {node_id: [] for node_id in nodes}
        for node_id, node in nodes.items():
            for dependency in node.get("depends_on") or []:
                dependency_id = str(dependency).strip()
                if dependency_id not in nodes:
                    raise ProductionPlanTeamError(f"节点 {node_id} 依赖不存在的节点：{dependency_id}")
                dependents[dependency_id].append(node_id)

        reasons: dict[str, str] = {node_id: "changed" for node_id in changed}
        queue = list(changed)
        while queue:
            upstream = queue.pop(0)
            for downstream in dependents[upstream]:
                if downstream not in reasons:
                    reasons[downstream] = f"depends_on:{upstream}"
                    queue.append(downstream)
        return [
            {"node_id": node_id, "reason": reasons[node_id]}
            for node_id in nodes
            if node_id in reasons
        ]

    @classmethod
    def _selected_nodes(
        cls,
        nodes: dict[str, dict[str, Any]],
        node_ids: Iterable[str],
        *,
        include_dependencies: bool,
    ) -> list[dict[str, Any]]:
        requested = cls._requested_node_ids(nodes, node_ids)
        if not include_dependencies:
            selected = set(requested)
            return [node for node_id, node in nodes.items() if node_id in selected]

        selected: set[str] = set()

        def add_with_dependencies(node_id: str) -> None:
            if node_id in selected:
                return
            node = nodes[node_id]
            for dependency in node.get("depends_on") or []:
                dependency_id = str(dependency).strip()
                if dependency_id not in nodes:
                    raise ProductionPlanTeamError(f"节点 {node_id} 依赖不存在的节点：{dependency_id}")
                add_with_dependencies(dependency_id)
            selected.add(node_id)

        for node_id in requested:
            add_with_dependencies(node_id)
        return [node for node_id, node in nodes.items() if node_id in selected]

    @staticmethod
    def _requested_node_ids(nodes: dict[str, dict[str, Any]], node_ids: Iterable[str]) -> list[str]:
        requested = list(dict.fromkeys(str(node_id).strip() for node_id in node_ids if str(node_id).strip()))
        if not requested:
            raise ProductionPlanTeamError("请至少选择一个生产计划节点")
        missing = [node_id for node_id in requested if node_id not in nodes]
        if missing:
            raise ProductionPlanTeamError(f"生产计划节点不存在：{', '.join(missing)}")
        return requested

    @staticmethod
    def _role_id(node_id: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", node_id).strip("-") or "node"
        return f"plan-{normalized}"[:120]

    @staticmethod
    def _node_objective(node: dict[str, Any]) -> str:
        summary = node.get("planning_summary") if isinstance(node.get("planning_summary"), dict) else {}
        lines = [
            f"执行生产计划节点「{node.get('label') or node['id']}」。",
            f"阶段：{node.get('stage') or '未指定'}。",
            f"专业职责：{node.get('specialist_role') or '未指定'}。",
        ]
        if summary:
            lines.append(f"用户可见规划摘要：{json.dumps(summary, ensure_ascii=False, default=str)}")
        if node.get("requires_confirmation"):
            lines.append("此节点标记为需要确认；不得直接发起生成、下载、发布或其他外部写入。")
        return "\n".join(lines)


__all__ = ["ProductionPlanTeamComposer", "ProductionPlanTeamError", "ROLE_PROFILE_IDS"]
