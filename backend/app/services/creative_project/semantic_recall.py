"""Optional project-local semantic recall contract for narrative Context Pack T5.

The shared embedding service indexes Asset Hub records and runs on an async
session. It is intentionally not called from the synchronous creative-project
service: asset metadata is not narrative canon. A deployment may provide a
retriever backed by that indexing infrastructure only after it indexes approved
``novel_body`` content with this project-local contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class NarrativeRecallCandidate:
    """An approved prose version eligible for semantic recall."""

    content_id: str
    chapter_number: int
    version: int
    text: str


@dataclass(frozen=True)
class NarrativeRecallResult:
    """Bounded recall output. Source ids must refer to supplied candidates."""

    text: str = ""
    source_content_ids: list[str] = field(default_factory=list)
    status: str = "available"
    diagnostics: str = ""


class NarrativeSemanticRecallAdapter(Protocol):
    """Optional synchronous adapter for a project-owned semantic index."""

    def recall(
        self,
        *,
        project_id: str,
        chapter_number: int,
        query: str,
        candidates: list[NarrativeRecallCandidate],
        character_budget: int,
    ) -> NarrativeRecallResult:
        """Recall only from the approved candidates provided by the runtime."""


class DisabledNarrativeSemanticRecallAdapter:
    """Default adapter: no vector/index provider is a valid configuration."""

    def recall(
        self,
        *,
        project_id: str,
        chapter_number: int,
        query: str,
        candidates: list[NarrativeRecallCandidate],
        character_budget: int,
    ) -> NarrativeRecallResult:
        return NarrativeRecallResult(status="not_configured")

