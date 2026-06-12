"""Shared types for LLM-assisted rule plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol

from app.services.ai.types import LLMMessage


@dataclass
class RuleAssistantContext:
    domain: str
    rule_type: str
    rule_format: str = "legado"
    current_rules: Dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    source_name: str = ""
    source_url: str = ""
    target_url: str = ""
    request_info: Dict[str, Any] = field(default_factory=dict)
    parsed_result: Dict[str, Any] = field(default_factory=dict)
    debug_info: Dict[str, Any] = field(default_factory=dict)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    raw_html: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RulePatch:
    target: str
    value: Any
    format: str = "legado"
    mode: str = "merge"
    reason: str = ""
    confidence: float = 0.0
    risks: List[str] = field(default_factory=list)
    validation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "format": self.format,
            "mode": self.mode,
            "value": self.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "risks": self.risks,
            "validation": self.validation,
        }


@dataclass
class RuleAssistantResult:
    success: bool
    plugin: str = ""
    summary: str = ""
    patches: List[RulePatch] = field(default_factory=list)
    selector_candidates: List[Dict[str, Any]] = field(default_factory=list)
    test_plan: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    usage: Dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    raw_response: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "plugin": self.plugin,
            "summary": self.summary,
            "patches": [patch.to_dict() for patch in self.patches],
            "selector_candidates": self.selector_candidates,
            "test_plan": self.test_plan,
            "warnings": self.warnings,
            "usage": self.usage,
            "provider": self.provider,
            "model": self.model,
            "raw_response": self.raw_response,
            "error": self.error,
        }


class RuleAssistantPlugin(Protocol):
    name: str

    def supports(self, context: RuleAssistantContext) -> bool:
        ...

    def analyze(self, context: RuleAssistantContext) -> Dict[str, Any]:
        ...

    def build_messages(
        self,
        context: RuleAssistantContext,
        analysis: Dict[str, Any],
    ) -> List[LLMMessage]:
        ...

    def parse_response(self, content: str) -> RuleAssistantResult:
        ...

    def validate_patches(
        self,
        context: RuleAssistantContext,
        result: RuleAssistantResult,
    ) -> RuleAssistantResult:
        ...
