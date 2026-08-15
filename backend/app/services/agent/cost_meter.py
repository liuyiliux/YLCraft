"""CostMeter — measure LLM prompt-cache hit rate from usage metadata.

DeepSeek / OpenAI-compatible APIs expose cached prompt tokens as
``usage.prompt_tokens_details.cached_tokens`` (or a top-level ``cached_tokens``
field). A stable tool-catalog prefix makes those cached tokens non-zero across
requests; the meter turns that into an observable regression signal.
"""

from __future__ import annotations

from typing import Any


class CostMeter:
    @staticmethod
    def cached_prompt_tokens(usage: dict[str, Any] | None) -> int:
        if not isinstance(usage, dict):
            return 0
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            cached = details.get("cached_tokens")
            if isinstance(cached, (int, float)):
                return int(cached)
        # OpenAI-compatible providers also expose top-level cache-hit counters;
        # DeepSeek reports ``prompt_cache_hit_tokens`` here.
        for key in ("prompt_cache_hit_tokens", "cached_tokens"):
            cached = usage.get(key)
            if isinstance(cached, (int, float)):
                return int(cached)
        return 0

    @staticmethod
    def total_prompt_tokens(usage: dict[str, Any] | None) -> int:
        if not isinstance(usage, dict):
            return 0
        total = usage.get("prompt_tokens")
        if isinstance(total, (int, float)):
            return int(total)
        return 0

    @classmethod
    def cache_hit_rate(cls, usage: dict[str, Any] | None) -> float | None:
        """Return cached/total prompt token ratio in [0, 1], or None when unknown."""
        cached = cls.cached_prompt_tokens(usage)
        total = cls.total_prompt_tokens(usage)
        if total <= 0:
            return None
        return round(min(1.0, max(0.0, cached / total)), 4)
