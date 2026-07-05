"""Loop Detector — inspired by DeerFlow LoopDetectionMiddleware.

Detects when an agent is stuck repeating the same tool calls in a cycle.
DeerFlow uses sliding-window hash detection: hash each (tool_name, arguments)
tuple and check against a window of recent hashes. If a cycle is detected,
the loop detector injects a warning and suggests breaking the pattern.

Hermes achieves similar protection via max-iteration caps + provider-side
retry detection; DeerFlow adds explicit pattern-matching for tighter loops.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger("ylcraft.agent.loop_detector")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Window size for hash-based loop detection.
# DeerFlow default: 10; we match this.
DEFAULT_WINDOW_SIZE = 10

# Minimum number of repeated calls to declare a loop.
MIN_LOOP_REPEATS = 3

# Maximum number of consecutive same-tool calls before forced warning.
MAX_SAME_TOOL_CONSECUTIVE = 4


def _hash_tool_call(tool_name: str, arguments: dict[str, Any] | None) -> str:
    """Produce a stable hash for a (tool_name, arguments) pair.

    DeerFlow uses a sliding window of call hashes; we mirror this with
    SHA-256 on canonical JSON.
    """
    args_str = json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False)
    raw = f"{tool_name}::{args_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class LoopDetector:
    """Detect infinite loops in agent tool execution.

    Usage::

        detector = LoopDetector()
        for iteration in range(budget):
            tool_calls = response.get("tool_calls") or []
            warning = detector.check(pending_calls=tool_calls)
            if warning:
                state["messages"].append({"role": "user", "content": warning})
    """

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE):
        self._window_size = window_size
        self._call_history: list[str] = []  # hashes
        self._tool_counters: dict[str, int] = {}  # consecutive same-tool counts
        self._detection_count = 0

    @property
    def detection_count(self) -> int:
        return self._detection_count

    def check(self, pending_calls: list[dict[str, Any]]) -> str | None:
        """Check pending tool calls for loops. Returns warning string or None.

        Two detection strategies:
        1. Hash cycle: look for repeating (tool, args) patterns in the window
        2. Stuck-tool: detect calling the same tool repeatedly without varied args

        Returns a natural-language warning to inject into context, or None.
        """
        if not pending_calls:
            self._tool_counters.clear()
            return None

        new_hashes: list[str] = []
        warnings: list[str] = []

        for call in pending_calls:
            tool_name = str(call.get("name") or call.get("function", {}).get("name") or "")
            raw_args = call.get("arguments") or call.get("function", {}).get("arguments") or "{}"
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    arguments = {"raw": raw_args}
            else:
                arguments = raw_args if isinstance(raw_args, dict) else {}

            call_hash = _hash_tool_call(tool_name, arguments)
            new_hashes.append(call_hash)

            # Strategy 1: Hash cycle detection
            window = self._call_history[-self._window_size:]
            occurrences = sum(1 for h in window if h == call_hash)
            if occurrences >= MIN_LOOP_REPEATS - 1:
                warnings.append(
                    f"[循环检测] 工具 {tool_name}({_args_summary(arguments)}) "
                    f"在最近 {self._window_size} 轮中已调用 {occurrences + 1} 次。"
                    "请考虑是否陷入了循环——尝试不同的工具或生成最终答案。"
                )

            # Strategy 2: Consecutive same-tool detection
            self._tool_counters = self._tool_counters if not warnings else {}
            prev_count = self._tool_counters.get(tool_name, 0)
            self._tool_counters[tool_name] = prev_count + 1

            if prev_count + 1 >= MAX_SAME_TOOL_CONSECUTIVE:
                warnings.append(
                    f"[循环检测] 已连续调用 {tool_name} {prev_count + 1} 次。"
                    "如果多次调用结果相同，说明可能陷入局部最优——尝试切换策略。"
                )

        self._call_history.extend(new_hashes)
        # Trim history to window
        if len(self._call_history) > self._window_size * 3:
            self._call_history = self._call_history[-self._window_size * 2:]

        if warnings:
            self._detection_count += 1
            return "\n".join(warnings)

        return None

    def reset(self) -> None:
        """Reset detector state (called at start of new agent run)."""
        self._call_history.clear()
        self._tool_counters.clear()


def _args_summary(arguments: dict[str, Any]) -> str:
    """Brief summary of arguments for human-readable loop warnings."""
    if not arguments:
        return ""
    items = list(arguments.items())[:2]
    parts = [f"{k}={str(v)[:30]}" for k, v in items]
    if len(arguments) > 2:
        parts.append("...")
    return ", ".join(parts)
