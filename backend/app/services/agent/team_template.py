"""Declarative agent team templates.

A team is a list of roles + dependencies + budget, described in YAML and
validated before execution. This replaces hard-coded multi-agent orchestration
(``multi_agent_coordinator.py``) with composition, mirroring the host/agent
plane and team-template ideas borrowed from a plugin-based harness.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

# Repo-internal team template directory: backend/app/agent_teams/*.yml
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "agent_teams"


class TeamTemplateError(ValueError):
    """Raised when a team template is missing, malformed or structurally invalid."""


@dataclasses.dataclass
class RoleSpec:
    id: str
    profile: str
    persona: str = ""
    tools: list[str] = dataclasses.field(default_factory=list)
    skills: list[str] = dataclasses.field(default_factory=list)
    spawn: str = "spawn"  # spawn | fork
    template: bool = False  # expand one instance per resolved item
    resolve: dict[str, Any] = dataclasses.field(default_factory=dict)
    parallel: bool = False
    max_parallel: int = 3
    depends_on: list[str] = dataclasses.field(default_factory=list)
    join: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RoleSpec":
        return cls(
            id=str(value.get("id") or "").strip(),
            profile=str(value.get("profile") or "").strip(),
            persona=str(value.get("persona") or ""),
            tools=[str(t) for t in (value.get("tools") or [])],
            skills=[str(s) for s in (value.get("skills") or [])],
            spawn=str(value.get("spawn") or "spawn").strip() or "spawn",
            template=bool(value.get("template") or False),
            resolve=dict(value.get("resolve") or {}),
            parallel=bool(value.get("parallel") or False),
            max_parallel=int(value.get("max_parallel") or 3),
            depends_on=[str(d) for d in (value.get("depends_on") or [])],
            join=bool(value.get("join") or False),
        )


@dataclasses.dataclass
class BudgetSpec:
    max_depth: int = 2
    max_children: int = 6
    max_concurrent: int = 3
    timeout_s: float = 300.0

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "BudgetSpec":
        value = value or {}
        return cls(
            max_depth=int(value.get("max_depth") or 2),
            max_children=int(value.get("max_children") or 6),
            max_concurrent=int(value.get("max_concurrent") or 3),
            timeout_s=float(value.get("timeout_s") or 300.0),
        )


@dataclasses.dataclass
class TeamTemplate:
    name: str
    version: int = 1
    roles: list[RoleSpec] = dataclasses.field(default_factory=list)
    join_strategy: str = "all"
    budget: BudgetSpec = dataclasses.field(default_factory=BudgetSpec)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TeamTemplate":
        team = value.get("team") if isinstance(value.get("team"), dict) else value
        if not isinstance(team, dict):
            raise TeamTemplateError("模板必须是映射或包含顶层 team 键")
        return cls(
            name=str(team.get("name") or "").strip(),
            version=int(team.get("version") or 1),
            roles=[RoleSpec.from_dict(r) for r in (team.get("roles") or [])],
            join_strategy=str(team.get("join_strategy") or "all"),
            budget=BudgetSpec.from_dict(team.get("budget")),
        )


class TeamTemplateValidator:
    """Structural validation for a loaded team template."""

    def validate(self, template: TeamTemplate) -> None:
        if not template.name:
            raise TeamTemplateError("模板缺少 name")
        if not template.roles:
            raise TeamTemplateError("模板至少需要一个角色")

        ids = [r.id for r in template.roles]
        if len(set(ids)) != len(ids):
            raise TeamTemplateError("角色 id 必须唯一")
        id_set = set(ids)

        join_count = 0
        for role in template.roles:
            if not role.id:
                raise TeamTemplateError("角色缺少 id")
            if not role.profile:
                raise TeamTemplateError(f"角色 {role.id} 缺少 profile")
            if role.spawn not in {"spawn", "fork"}:
                raise TeamTemplateError(f"角色 {role.id} 的 spawn 必须是 spawn 或 fork")
            if role.template and not role.resolve:
                raise TeamTemplateError(f"角色 {role.id} 声明 template 但缺少 resolve")
            if role.join:
                join_count += 1
            unknown = [d for d in role.depends_on if d not in id_set]
            if unknown:
                raise TeamTemplateError(f"角色 {role.id} 依赖未知角色：{', '.join(unknown)}")
            if role.id in role.depends_on:
                raise TeamTemplateError(f"角色 {role.id} 不能依赖自身")
            if role.max_parallel < 1:
                raise TeamTemplateError(f"角色 {role.id} 的 max_parallel 必须 >= 1")

        if self._has_cycle(template):
            raise TeamTemplateError("角色依赖存在循环")

        if join_count != 1:
            raise TeamTemplateError(f"模板必须恰好一个 join 角色，当前 {join_count} 个")
        if template.join_strategy not in {"all", "best_effort"}:
            raise TeamTemplateError("join_strategy 只支持 all 或 best_effort")

    @staticmethod
    def _has_cycle(template: TeamTemplate) -> bool:
        """Kahn's algorithm over the role dependency DAG (edge dep -> role)."""
        from collections import defaultdict, deque

        indegree = {role.id: len(role.depends_on) for role in template.roles}
        dependents: dict[str, list[str]] = defaultdict(list)
        for role in template.roles:
            for dep in role.depends_on:
                dependents[dep].append(role.id)
        queue = deque(rid for rid, degree in indegree.items() if degree == 0)
        seen = 0
        while queue:
            rid = queue.popleft()
            seen += 1
            for nxt in dependents[rid]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        return seen != len(template.roles)


class TeamTemplateLoader:
    """Load team templates from repo YAML files or inline dicts."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or TEMPLATE_DIR

    def load(self, template_id: str) -> TeamTemplate:
        path = self.directory / f"{template_id}.yml"
        if not path.exists():
            raise TeamTemplateError(f"团队模板不存在：{template_id}")
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise TeamTemplateError(f"团队模板 {template_id} YAML 解析失败：{exc}") from exc
        if not isinstance(raw, dict):
            raise TeamTemplateError(f"团队模板 {template_id} 不是合法 YAML 映射")
        return TeamTemplate.from_dict(raw)

    def from_dict(self, value: dict[str, Any]) -> TeamTemplate:
        return TeamTemplate.from_dict(value)
