"""Rule Assistant service orchestration."""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from app.services.ai import get_ai_service
from app.services.ai.types import LLMMessage
from app.services.rule_assistant.plugins.book_source import BookSourceRuleRepairPlugin
from app.services.rule_assistant.types import (
    RuleAssistantContext,
    RuleAssistantPlugin,
    RuleAssistantResult,
)

logger = logging.getLogger("ylcraft.rule_assistant")


class RuleAssistantService:
    """Select a rule plugin, call the existing LLM stack, and validate patches."""

    def __init__(self, plugins: Optional[Iterable[RuleAssistantPlugin]] = None):
        self.plugins = list(plugins or [BookSourceRuleRepairPlugin()])

    async def suggest(
        self,
        context: RuleAssistantContext,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1800,
    ) -> RuleAssistantResult:
        plugin = self._select_plugin(context)
        if not plugin:
            return RuleAssistantResult(
                success=False,
                error=f"No rule assistant plugin supports domain={context.domain!r}",
            )

        analysis = plugin.analyze(context)
        try:
            ai_service = get_ai_service()
        except Exception as exc:
            return RuleAssistantResult(
                success=False,
                plugin=plugin.name,
                selector_candidates=analysis.get("selector_candidates", []),
                error=f"AIService is not available: {exc}",
            )

        messages = plugin.build_messages(context, analysis)
        llm_result = await ai_service.chat(
            messages=messages,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not llm_result.success:
            return RuleAssistantResult(
                success=False,
                plugin=plugin.name,
                selector_candidates=analysis.get("selector_candidates", []),
                usage=llm_result.usage or {},
                provider=llm_result.provider or "",
                model=llm_result.model or "",
                error=llm_result.error or "LLM request failed",
            )

        try:
            result = plugin.parse_response(llm_result.content or "")
        except Exception as exc:
            logger.warning("Rule assistant response parse failed: %s", exc)
            if llm_result.content:
                repair_result = await ai_service.chat(
                    messages=_build_json_repair_messages(llm_result.content),
                    provider=provider,
                    model=model,
                    temperature=0,
                    max_tokens=1200,
                )
                if repair_result.success:
                    try:
                        result = plugin.parse_response(repair_result.content or "")
                        result.warnings.append("模型首次返回非 JSON，已自动转换为可解析补丁格式")
                        result.plugin = plugin.name
                        result.raw_response = repair_result.content or ""
                        result.usage = repair_result.usage or llm_result.usage or {}
                        result.provider = repair_result.provider or llm_result.provider or ""
                        result.model = repair_result.model or llm_result.model or ""
                        if not result.selector_candidates:
                            result.selector_candidates = analysis.get("selector_candidates", [])
                        return plugin.validate_patches(context, result)
                    except Exception as repair_exc:
                        logger.warning("Rule assistant JSON repair parse failed: %s", repair_exc)
            return RuleAssistantResult(
                success=False,
                plugin=plugin.name,
                selector_candidates=analysis.get("selector_candidates", []),
                raw_response=llm_result.content or "",
                usage=llm_result.usage or {},
                provider=llm_result.provider or "",
                model=llm_result.model or "",
                error=(
                    "LLM returned empty content; please try another model or check this connector's response format"
                    if not llm_result.content
                    else f"LLM response is not valid patch JSON: {exc}"
                ),
            )

        result.plugin = plugin.name
        result.raw_response = llm_result.content or ""
        result.usage = llm_result.usage or {}
        result.provider = llm_result.provider or ""
        result.model = llm_result.model or ""
        if not result.selector_candidates:
            result.selector_candidates = analysis.get("selector_candidates", [])
        return plugin.validate_patches(context, result)

    def _select_plugin(self, context: RuleAssistantContext) -> RuleAssistantPlugin | None:
        for plugin in self.plugins:
            if plugin.supports(context):
                return plugin
        return None


def _build_json_repair_messages(content: str) -> list[LLMMessage]:
    schema = (
        "{"
        '"summary":"short Chinese explanation",'
        '"patches":[{"target":"rule_content|rule_toc|rule_search|ylcraft_rule|search_url",'
        '"format":"legado|ylcraft","mode":"merge|replace","value":{},"reason":"why","confidence":0.0,"risks":[]}],'
        '"test_plan":[],"warnings":[]'
        "}"
    )
    return [
        LLMMessage(
            role="system",
            content=(
                "You convert a previous assistant response into strict JSON. "
                "Return only one JSON object. No markdown. No prose. "
                "If there is no concrete patch in the source response, return patches as an empty array."
            ),
        ),
        LLMMessage(
            role="user",
            content=f"Target schema example:\n{schema}\n\nPrevious response:\n{content}",
        ),
    ]
