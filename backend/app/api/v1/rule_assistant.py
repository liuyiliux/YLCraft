"""Generic rule assistant API."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.rule_assistant import RuleAssistantContext, RuleAssistantService

router = APIRouter(tags=["rule-assistant"])


class RuleAssistantSuggestRequest(BaseModel):
    domain: Literal["book_source"] = "book_source"
    rule_type: Literal["search", "toc", "content"]
    rule_format: Literal["legado", "ylcraft"] = "legado"
    current_rules: Dict[str, Any] = Field(default_factory=dict)
    source_id: str = ""
    source_name: str = ""
    source_url: str = ""
    target_url: str = ""
    test_result: Dict[str, Any] = Field(default_factory=dict)
    provider: Optional[str] = None
    model: Optional[str] = None


@router.post("/suggest")
async def suggest_rule_patch(payload: RuleAssistantSuggestRequest):
    test_result = payload.test_result or {}
    debug_info = test_result.get("debug_info") or {}
    request_info = test_result.get("request_info") or {}
    diagnostics = test_result.get("diagnostics") or debug_info.get("diagnostics") or []
    context = RuleAssistantContext(
        domain=payload.domain,
        rule_type=payload.rule_type,
        rule_format=(payload.rule_format or "legado").lower(),
        current_rules=payload.current_rules or {},
        source_id=payload.source_id,
        source_name=payload.source_name,
        source_url=payload.source_url,
        target_url=payload.target_url or test_result.get("url") or request_info.get("url") or "",
        request_info=request_info,
        parsed_result=test_result.get("parsed_result") or {},
        debug_info=debug_info,
        diagnostics=diagnostics if isinstance(diagnostics, list) else [],
        raw_html=test_result.get("raw_html") or "",
    )
    result = await RuleAssistantService().suggest(
        context,
        provider=payload.provider,
        model=payload.model,
    )
    return {"success": result.success, "data": result.to_dict()}
