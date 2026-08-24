"""Build user-visible visual planning summaries for media generation.

This module deliberately stores only auditable production intent.  It must not
capture hidden model reasoning or chain-of-thought.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_TEXT_LIMITS = {
    "intent": 240,
    "prompt": 4000,
    "negative_prompt": 2000,
    "style": 240,
    "composition": 400,
    "expected_output": 120,
    "provider": 160,
    "model": 160,
    "project_id": 120,
    "content_id": 120,
    "production_plan_id": 120,
    "production_node_id": 120,
}


def _text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit] if text else ""


def _ids(values: Sequence[Any] | None, limit: int = 24) -> list[str]:
    result: list[str] = []
    for value in values or []:
        item = _text(value, 160)
        if item and item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result


def _clean_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key).lower()
        if any(marker in normalized_key for marker in ("reasoning", "chain_of_thought", "cot", "thought_trace", "hidden_thought")):
            continue
        if item in (None, "", [], {}):
            continue
        if isinstance(item, str):
            cleaned[str(key)] = item[:800]
        elif isinstance(item, Mapping):
            nested = _clean_mapping(item)
            if nested:
                cleaned[str(key)] = nested
        elif isinstance(item, (list, tuple)):
            cleaned[str(key)] = [str(x)[:240] for x in item[:24]]
        else:
            cleaned[str(key)] = item
    return cleaned


def build_visual_planning_summary(
    kind: str,
    prompt: str,
    *,
    negative_prompt: str = "",
    provider: str = "",
    model: str = "",
    expected_output: str = "",
    reference_asset_ids: Sequence[Any] | None = None,
    project_id: str = "",
    content_id: str = "",
    production_plan_id: str = "",
    production_node_id: str = "",
    visual_intent: str = "",
    style: str = "",
    composition: str = "",
    aspect_ratio: str = "",
    duration: int | float | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a bounded, JSON-safe, user-facing production summary."""
    summary: dict[str, Any] = {
        "kind": _text(kind, 80),
        "intent": _text(visual_intent, _TEXT_LIMITS["intent"]),
        "prompt": _text(prompt, _TEXT_LIMITS["prompt"]),
        "negative_prompt": _text(negative_prompt, _TEXT_LIMITS["negative_prompt"]),
        "style": _text(style, _TEXT_LIMITS["style"]),
        "composition": _text(composition, _TEXT_LIMITS["composition"]),
        "aspect_ratio": _text(aspect_ratio, 40),
        "provider": _text(provider, _TEXT_LIMITS["provider"]),
        "model": _text(model, _TEXT_LIMITS["model"]),
        "expected_output": _text(expected_output, _TEXT_LIMITS["expected_output"]),
        "reference_assets": _ids(reference_asset_ids),
        "project_id": _text(project_id, _TEXT_LIMITS["project_id"]),
        "content_id": _text(content_id, _TEXT_LIMITS["content_id"]),
        "production_plan_id": _text(production_plan_id, _TEXT_LIMITS["production_plan_id"]),
        "production_node_id": _text(production_node_id, _TEXT_LIMITS["production_node_id"]),
    }
    if duration is not None:
        summary["duration"] = max(0, min(float(duration), 3600))
        if summary["duration"].is_integer():
            summary["duration"] = int(summary["duration"])
    summary.update(_clean_mapping(extra))
    return {key: value for key, value in summary.items() if value not in (None, "", [], {})}
