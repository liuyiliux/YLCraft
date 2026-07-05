"""Context Compressor — inspired by DeerFlow SummarizationMiddleware + Hermes sentinel.

Automatically trims and summarizes conversation history when the message stack
approaches the model's token limit. Uses configurable token-threshold triggering
(DeerFlow-style) with a sentinel pre-check before each LLM call (Hermes-style).

Compared to DeerFlow's implementation:
- DeerFlow uses a token-count threshold (default 15564) with retain-N-last policy
- Hermes uses a sentinel pre-check + dual compression (summary + keep last)

This implementation combines both: sentinel pre-check before each _call_llm(),
token-approximation-based triggering, and pluggable compression strategies.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.ai import get_ai_service
from app.services.ai.types import LLMMessage

logger = logging.getLogger("ylcraft.agent.context_compressor")

# ---------------------------------------------------------------------------
# Configuration constants (inspired by DeerFlow config.yaml)
# ---------------------------------------------------------------------------

# Token threshold: trigger compression when estimated token count exceeds this.
# DeerFlow default: 15564; we set a conservative default for creative workflows.
DEFAULT_TOKEN_THRESHOLD = 12000

# Number of most-recent messages to always keep uncompressed.
# DeerFlow default: 10; we keep 8 for tighter creative-context loops.
DEFAULT_KEEP_LAST_MESSAGES = 8

# Maximum characters for the compressed summary (Hermes sentinel: 3575 chars).
MAX_SUMMARY_CHARS = 3500

# Minimum token budget to leave for the model response after compression.
MIN_RESPONSE_BUDGET = 2048


def estimate_tokens(text: str) -> int:
    """Rough token estimation: ~4 chars per token for Chinese, ~3.5 for English.

    This is a fast approximation — not exact tokenization — sufficient for
    threshold triggering.

    DeerFlow uses a more precise tiktoken-based counter; we use a simpler
    heuristic to avoid a heavy dependency.
    """
    if not text:
        return 0
    char_count = len(text)
    # Chinese chars are ~1.5 tokens each; ASCII ~0.25 tokens each
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    ascii_count = char_count - chinese_count
    return int(chinese_count * 1.5 + ascii_count * 0.25)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total token count for a list of message dicts."""
    total = 0
    for msg in messages:
        content = str(msg.get("content") or "")
        total += estimate_tokens(content)
        # +4 for role/formatting overhead per message
        total += 4
    return total


class ContextCompressor:
    """Manages context window compression during agent execution.

    The compressor intercepts the message list before each LLM call and
    either compresses or returns as-is, depending on token thresholds.

    Usage::

        compressor = ContextCompressor(ai_service)
        compressed_messages = await compressor.ensure_fits(
            messages=messages,
            system_prompt=system_text,
            memory_context=memory_text,
        )
    """

    def __init__(
        self,
        token_threshold: int = DEFAULT_TOKEN_THRESHOLD,
        keep_last: int = DEFAULT_KEEP_LAST_MESSAGES,
        response_budget: int = MIN_RESPONSE_BUDGET,
    ):
        self._token_threshold = token_threshold
        self._keep_last = keep_last
        self._response_budget = response_budget
        self._compress_count = 0

    @property
    def compression_count(self) -> int:
        return self._compress_count

    async def ensure_fits(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str = "",
        memory_context: str = "",
        profile: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Check token budget and compress if needed. Returns (possibly compressed)
        message list, potentially with a summary injected at the head.
        """
        system_tokens = estimate_tokens(system_prompt) + estimate_tokens(memory_context)
        msg_tokens = estimate_messages_tokens(messages)
        total = system_tokens + msg_tokens

        available = self._token_threshold - system_tokens - self._response_budget
        if msg_tokens <= available:
            # Within budget — no compression needed
            return messages

        # Need compression
        logger.info(
            "[ContextCompressor] Triggered: total_est=%d threshold=%d msg_tokens=%d available=%d",
            total, self._token_threshold, msg_tokens, available,
        )
        self._compress_count += 1

        return await self._compress(messages, available)

    async def _compress(
        self,
        messages: list[dict[str, Any]],
        budget: int,
    ) -> list[dict[str, Any]]:
        """Compress conversation history: summarize middle, keep last N.

        DeerFlow pattern: summarize oldest messages, keep the most recent
        keep_last messages fully intact.

        Hermes pattern: compress old turns to structured summary, keep
        lineage in SQLite for later retrieval.
        """
        if len(messages) <= self._keep_last + 2:
            # Not enough messages to compress meaningfully — just trim oldest
            logger.debug("[ContextCompressor] Too few messages to compress, trimming oldest")
            return messages[-max(1, len(messages) - 2):]

        # Split: oldest (to compress), newest (to keep)
        split_idx = max(0, len(messages) - self._keep_last)
        to_compress = messages[:split_idx]
        to_keep = messages[split_idx:]

        # Build a summary of compressed messages
        summary = self._build_fast_summary(to_compress)

        # Inject summary as a system message at the head of the keep list
        compressed = [
            {"role": "system", "content": f"[对话历史摘要]\n{summary}"},
            *to_keep,
        ]
        logger.debug(
            "[ContextCompressor] Compressed %d messages into summary (%d chars), keeping %d",
            len(to_compress), len(summary), len(to_keep),
        )
        return compressed

    def _build_fast_summary(self, messages: list[dict[str, Any]]) -> str:
        """Build a fast text summary of compressed messages.

        For MVP, this is a structural summary (role/topic extraction).
        In production, this could call a fast/cheap LLM for summarization
        (DeerFlow does this via MemoryUpdater LLM call).
        """
        if not messages:
            return ""

        parts: list[str] = []
        user_msgs = 0
        assistant_msgs = 0
        tool_msgs = 0
        topics: set[str] = set()

        for msg in messages:
            role = str(msg.get("role") or "")
            content = str(msg.get("content") or "")
            if role == "user":
                user_msgs += 1
                # Extract topic keywords from first 100 chars
                topic = content[:100].strip()
                if topic:
                    topics.add(topic)
            elif role == "assistant":
                assistant_msgs += 1
            elif role == "tool":
                tool_msgs += 1
            elif role == "system":
                continue

        parts.append(f"共压缩 {len(messages)} 条历史消息")
        parts.append(f"(用户提问{user_msgs}条、助手回复{assistant_msgs}条、工具结果{tool_msgs}条)")

        if topics:
            # Show last few topic summaries
            shown_topics = list(topics)[-5:]
            parts.append("涉及话题：" + "；".join(shown_topics[:5]))

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Token budget guard (fast inline check, no full compression)
# ---------------------------------------------------------------------------


def token_budget_check(
    messages: list[dict[str, Any]],
    system_parts: list[str],
    budget: int = DEFAULT_TOKEN_THRESHOLD,
) -> tuple[bool, int]:
    """Fast inline check: returns (should_compress, estimated_total_tokens).

    Called before every _call_llm() to decide whether compression is needed.
    Hermes-style sentinel pattern.
    """
    system_text = "\n".join(system_parts)
    total = estimate_tokens(system_text) + estimate_messages_tokens(messages)
    return (total > budget, total)
