"""Agent run-loop orchestration.

This module owns the iterative plan -> tool -> observe control flow. Persistence
and domain side effects stay in AgentService through callbacks.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from app.services.agent.loop_detector import LoopDetector

logger = logging.getLogger("ylcraft.agent.runtime.loop")

ExecutePhase = Callable[[dict[str, Any], list[dict[str, Any]]], Awaitable[None]]
ObservePhase = Callable[[dict[str, Any]], Awaitable[None]]
PendingHandler = Callable[[dict[str, Any]], Awaitable[None]]
BudgetHandler = Callable[[dict[str, Any], int, int], Awaitable[None]]


class RunLoop:
    """DeerFlow/Hermes-style bounded agent loop.

    The loop is intentionally generic: it does not know about Bilibili, novels,
    assets, or any other business domain. Those are represented by routed skills
    and concrete tool calls before this loop executes.
    """

    def __init__(self, loop_detector: LoopDetector):
        self._loop_detector = loop_detector

    async def run(
        self,
        state: dict[str, Any],
        *,
        execute_phase: ExecutePhase,
        observe_phase: ObservePhase,
        handle_pending_confirmations: PendingHandler,
        handle_budget_exhausted: BudgetHandler,
    ) -> None:
        profile = state["profile"]
        iteration_budget = max(1, min(int(profile.get("max_steps") or 8), 20))

        for iteration in range(iteration_budget):
            remaining = iteration_budget - iteration - 1
            state["iteration"] = iteration + 1
            state["iteration_budget"] = iteration_budget
            state["remaining"] = remaining

            tool_calls = state["llm_response"].get("tool_calls") or []
            if not tool_calls:
                if iteration == 0:
                    logger.debug("[RunLoop] LLM returned a direct answer, no tool calls needed")
                break

            loop_warning = self._loop_detector.check(tool_calls)
            if loop_warning:
                logger.warning("[RunLoop] repeated tool pattern detected: %s", loop_warning)
                state["messages"].append({"role": "user", "content": loop_warning})

            logger.debug(
                "[RunLoop] iteration %s/%s (%s remaining), executing %s tool(s)",
                iteration + 1,
                iteration_budget,
                remaining,
                len(tool_calls),
            )
            await execute_phase(state, tool_calls)

            if state.get("pending_confirmations"):
                await handle_pending_confirmations(state)
                break

            if remaining == 0:
                await handle_budget_exhausted(state, iteration + 1, iteration_budget)
                break

            await observe_phase(state)
