"""Explicit host/agent plane boundary for YLCraft agent runs.

Host plane = process-global singletons (tool/skill/subagent registries, session
store, model route, sandbox/approval stack). Agent plane = per-session state
(persona, plan-mode, compaction, team role overrides).

A single ``contextvars.ContextVar`` carries the current scope so child
sessions/roles inherit host-plane singletons while isolating agent-plane state,
without relying on module-level globals or shared mutable instances.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Iterator

_scope_var: contextvars.ContextVar["AgentScope | None"] = contextvars.ContextVar(
    "ylcraft_agent_scope", default=None
)


class AgentScope:
    """A namespaced view over host-plane and agent-plane services.

    ``host`` holds keys bound to process singletons (registries, persistence,
    model route). ``agent`` holds per-session/role state. A child scope created
    with :meth:`child` shares the same ``host`` dict but gets an isolated copy
    of ``agent``, so concurrent team roles cannot leak mutable state into each
    other while still resolving the shared registries.
    """

    def __init__(self, host: dict[str, Any] | None = None, agent: dict[str, Any] | None = None):
        self.host = host if host is not None else {}
        self.agent = agent if agent is not None else {}

    # ---- host plane (process-global singletons) ----

    def get_host(self, key: str, default: Any = None) -> Any:
        return self.host.get(key, default)

    def set_host(self, key: str, value: Any) -> None:
        self.host[key] = value

    # ---- agent plane (per-session / per-role state) ----

    def get_agent(self, key: str, default: Any = None) -> Any:
        return self.agent.get(key, default)

    def set_agent(self, key: str, value: Any) -> None:
        self.agent[key] = value

    def child(self, *, role_id: str = "", **agent_overrides: Any) -> "AgentScope":
        """Return a child scope sharing host singletons but with isolated agent state."""
        child_agent = dict(self.agent)
        if role_id:
            child_agent["role_id"] = role_id
        child_agent.update(agent_overrides)
        return AgentScope(host=self.host, agent=child_agent)

    @classmethod
    def current(cls) -> "AgentScope | None":
        return _scope_var.get()

    @classmethod
    @contextmanager
    def enter(
        cls,
        host: dict[str, Any] | None = None,
        agent: dict[str, Any] | None = None,
    ) -> Iterator["AgentScope"]:
        """Install a scope for the duration of the ``with`` block."""
        scope = cls(host=host, agent=agent)
        token = _scope_var.set(scope)
        try:
            yield scope
        finally:
            _scope_var.reset(token)
