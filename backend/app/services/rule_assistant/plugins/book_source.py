"""Book source rule repair plugin."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup, Tag

from app.services.ai.types import LLMMessage
from app.services.novel.source_parser import _select_elements
from app.services.rule_assistant.types import (
    RuleAssistantContext,
    RuleAssistantResult,
    RulePatch,
)


class BookSourceRuleRepairPlugin:
    name = "book_source_rule_repair"

    COMMON_SELECTORS = {
        "content": [
            "main",
            "article",
            "#content",
            ".content",
            ".chapter-content",
            ".read-content",
            ".j_readContent",
            ".reader-content",
            ".post-content",
            ".entry-content",
            ".book-content",
            ".chapter",
            ".text",
        ],
        "toc": [
            "#catalog",
            ".catalog",
            ".catalog-content li",
            ".chapter-list li",
            ".volume-list li",
            ".book-list li",
            "ul li a",
            "ol li a",
        ],
        "search": [
            ".book-img-text li",
            ".search-result li",
            ".result-list li",
            ".book-list li",
            ".book-item",
            ".bookbox",
            "article",
            "li",
        ],
    }

    VALID_TARGETS = {
        "legado": {"search_url", "rule_search", "rule_book_info", "rule_toc", "rule_content", "rule_explore"},
        "ylcraft": {"ylcraft_rule"},
    }

    def supports(self, context: RuleAssistantContext) -> bool:
        return context.domain == "book_source"

    def analyze(self, context: RuleAssistantContext) -> Dict[str, Any]:
        html = context.raw_html or ""
        soup = BeautifulSoup(html, "html.parser")
        for node in soup.find_all(["script", "style", "noscript"]):
            node.decompose()

        return {
            "page_meta": _page_meta(soup),
            "selector_candidates": self._selector_candidates(soup, context.rule_type),
            "html_excerpt": _compact_text(str(soup), 6000),
            "visible_text_excerpt": _compact_text(soup.get_text("\n", strip=True), 2500),
        }

    def build_messages(
        self,
        context: RuleAssistantContext,
        analysis: Dict[str, Any],
    ) -> List[LLMMessage]:
        payload = {
            "task": "repair_book_source_rule",
            "source": {
                "id": context.source_id,
                "name": context.source_name,
                "url": context.source_url,
            },
            "target_url": context.target_url,
            "rule_type": context.rule_type,
            "rule_format": context.rule_format,
            "current_rules": _compact_value(context.current_rules, 5000),
            "request_info": _compact_value(_safe_request_info(context.request_info), 2500),
            "parsed_result": _compact_value(_parsed_summary(context.parsed_result), 2500),
            "diagnostics": context.diagnostics,
            "rule_trace": context.debug_info.get("rule_trace") or [],
            "matched_elements": context.debug_info.get("matched_elements"),
            "page_meta": analysis.get("page_meta") or {},
            "selector_candidates": analysis.get("selector_candidates") or [],
            "visible_text_excerpt": analysis.get("visible_text_excerpt") or "",
            "html_excerpt": analysis.get("html_excerpt") or "",
        }

        system = (
            "You are a YLCraft and Legado book-source rule engineer. "
            "Return strict JSON only, with no markdown fences. "
            "Use concise Chinese in summary/reason/risks/test_plan. "
            "Do not invent cookies, tokens, login state, or request headers. "
            "Prefer the smallest scoped patch that fixes the selected rule_type. "
            "For YLCraft rules, prefer structured transforms over replacing an entire rule section. "
            "If evidence is insufficient, return warnings and no patch instead of guessing. "
            "If you say the rule should be repaired or changed, you must include at least one patch."
        )
        user = (
            "Repair the current book source rule from this debug context.\n\n"
            "Do not return summary-only advice when a concrete selector or rule value is available.\n\n"
            "Patch schema:\n"
            "{\n"
            '  "summary": "short Chinese explanation",\n'
            '  "patches": [\n'
            "    {\n"
            '      "target": "rule_content | rule_toc | rule_search | ylcraft_rule | search_url",\n'
            '      "format": "legado | ylcraft",\n'
            '      "mode": "merge | replace",\n'
            '      "value": {},\n'
            '      "reason": "why this should work",\n'
            '      "confidence": 0.0,\n'
            '      "risks": ["remaining risk"]\n'
            "    }\n"
            "  ],\n"
            '  "test_plan": ["what to retest"],\n'
            '  "warnings": []\n'
            "}\n\n"
            "Legado examples:\n"
            '- content patch: {"target":"rule_content","format":"legado","value":{"content":"main"}}\n'
            '- field-only patch: {"target":"rule_search","format":"legado","mode":"merge","value":{"author":".author .name@text"}}\n'
            '- toc patch: {"target":"rule_toc","format":"legado","value":{"chapterList":".chapter-list li","chapterName":"a@text","chapterUrl":"a@href"}}\n'
            '- search patch: {"target":"rule_search","format":"legado","value":{"bookList":".book-item","name":"h3@text","bookUrl":"a@href"}}\n\n'
            "Use mode=merge for partial object patches. Use mode=replace only when replacing the whole rule object is required.\n\n"
            "YLCraft examples:\n"
            '- content patch target is ylcraft_rule and updates content.selector.\n'
            '- field cleanup patch: {"target":"ylcraft_rule","format":"ylcraft","mode":"merge","value":{"search":{"items":{"fields":{"author":{"transforms":[{"type":"replace","old":"作者：","new":""},{"type":"trim"}]}}}}}}\n'
            '- relative URL patch: {"target":"ylcraft_rule","format":"ylcraft","mode":"merge","value":{"toc":{"items":{"fields":{"url":{"transforms":[{"type":"urljoin","base":"https://www.example.com"}]}}}}}}\n'
            '- supported transforms: trim, replace, regex_replace, regex_extract, prefix, suffix, urljoin, max_length, slice, js. Prefer non-js transforms when possible.\n\n'
            f"Debug context JSON:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]

    def parse_response(self, content: str) -> RuleAssistantResult:
        data = _loads_json_object(content)
        patches: List[RulePatch] = []
        warnings = _string_list(data.get("warnings"))

        for item in data.get("patches") or []:
            if not isinstance(item, dict):
                continue
            target = str(item.get("target") or "").strip()
            if not target or "value" not in item:
                warnings.append("模型返回了缺少 target/value 的补丁，已忽略")
                continue
            patches.append(
                RulePatch(
                    target=target,
                    format=str(item.get("format") or "legado").strip().lower(),
                    mode=str(item.get("mode") or "merge").strip().lower(),
                    value=item.get("value"),
                    reason=str(item.get("reason") or "").strip(),
                    confidence=_clamp_float(item.get("confidence"), 0.0, 1.0),
                    risks=_string_list(item.get("risks")),
                )
            )

        return RuleAssistantResult(
            success=True,
            summary=str(data.get("summary") or "").strip(),
            patches=patches,
            test_plan=_string_list(data.get("test_plan")),
            warnings=warnings,
        )

    def validate_patches(
        self,
        context: RuleAssistantContext,
        result: RuleAssistantResult,
    ) -> RuleAssistantResult:
        allowed = self.VALID_TARGETS.get(context.rule_format, set())
        html = context.raw_html or ""
        soup = BeautifulSoup(html, "html.parser") if html else None
        valid_patches: List[RulePatch] = []

        for patch in result.patches:
            if patch.format not in {"legado", "ylcraft"}:
                patch.risks.append("补丁格式不是 legado 或 ylcraft")
                continue
            if patch.target not in allowed and patch.target not in self.VALID_TARGETS.get(patch.format, set()):
                patch.risks.append(f"当前规则格式不支持写入 {patch.target}")
                continue
            if not _target_matches_rule_type(patch.target, context.rule_type, patch.format):
                patch.risks.append("补丁目标和当前测试类型不完全一致，请应用后重点复测")

            selector = _selector_from_patch(patch, context.rule_type)
            if selector and soup is not None:
                patch.validation = _validate_selector(soup, html, selector, patch.format)
                if patch.validation.get("matched_elements") == 0:
                    patch.risks.append("选择器在当前 HTML 中未命中")
            elif selector:
                patch.validation = {"selector": selector, "status": "no_html"}
            else:
                patch.validation = {"status": "unchecked"}
            valid_patches.append(patch)

        result.patches = valid_patches
        if not result.summary:
            result.summary = "已根据当前调试结果生成候选规则补丁"
        if not result.test_plan:
            result.test_plan = ["应用补丁到当前编辑器", "使用相同 URL 重新运行测试", "确认命中数和解析结果后再保存规则"]
        return result

    def _selector_candidates(self, soup: BeautifulSoup, rule_type: str) -> List[Dict[str, Any]]:
        selectors: List[str] = list(self.COMMON_SELECTORS.get(rule_type, []))
        selectors.extend(_derived_selectors(soup, rule_type))

        seen = set()
        candidates: List[Dict[str, Any]] = []
        for selector in selectors:
            selector = selector.strip()
            if not selector or selector in seen:
                continue
            seen.add(selector)
            try:
                elements = soup.select(selector)
            except Exception:
                continue
            if not elements:
                continue
            first = elements[0]
            text = first.get_text(" ", strip=True) if isinstance(first, Tag) else str(first)
            candidates.append(
                {
                    "selector": selector,
                    "matches": len(elements),
                    "text_length": len(text),
                    "sample": _compact_text(text, 220),
                    "link_count": len(first.select("a")) if isinstance(first, Tag) else 0,
                }
            )

        candidates.sort(key=lambda item: (item["matches"] > 0, item["text_length"], item["link_count"]), reverse=True)
        return candidates[:24]


def _loads_json_object(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("response JSON must be an object")
    return data


def _page_meta(soup: BeautifulSoup) -> Dict[str, str]:
    def meta_value(name: str) -> str:
        node = soup.select_one(f'meta[name="{name}"]')
        return _compact_text(str(node.get("content") or ""), 400) if node else ""

    title = soup.title.get_text(strip=True) if soup.title else ""
    return {
        "title": _compact_text(title, 300),
        "keywords": meta_value("keywords"),
        "description": meta_value("description"),
    }


def _derived_selectors(soup: BeautifulSoup, rule_type: str) -> List[str]:
    keywords = {
        "content": ("content", "chapter", "read", "article", "main", "text"),
        "toc": ("catalog", "chapter", "volume", "toc", "list"),
        "search": ("book", "result", "search", "item", "list"),
    }.get(rule_type, ())
    selectors: List[str] = []
    for element in soup.find_all(True):
        if not isinstance(element, Tag):
            continue
        element_id = str(element.get("id") or "")
        classes = [str(item) for item in element.get("class") or []]
        haystack = " ".join([element.name, element_id, *classes]).lower()
        if not any(keyword in haystack for keyword in keywords):
            continue
        if element_id:
            selectors.append(f"#{_css_escape_identifier(element_id)}")
        for cls in classes[:3]:
            if cls:
                selectors.append(f".{_css_escape_identifier(cls)}")
    return selectors


def _css_escape_identifier(value: str) -> str:
    return re.sub(r"([^a-zA-Z0-9_-])", r"\\\1", value.strip())


def _selector_from_patch(patch: RulePatch, rule_type: str) -> str:
    value = patch.value
    if patch.format == "ylcraft":
        if patch.target == "ylcraft_rule" and isinstance(value, dict):
            if rule_type == "content":
                return str(((value.get("content") or {}).get("selector")) or "")
            items = ((value.get(rule_type) or {}).get("items") or {})
            return str(items.get("selector") or "")
        return ""

    if not isinstance(value, dict):
        return ""
    if patch.target == "rule_content":
        return str(value.get("content") or "")
    if patch.target == "rule_toc":
        return str(value.get("chapterList") or "")
    if patch.target == "rule_search":
        return str(value.get("bookList") or "")
    return ""


def _validate_selector(soup: BeautifulSoup, html: str, selector: str, rule_format: str) -> Dict[str, Any]:
    try:
        if rule_format == "legado":
            elements = _select_elements(selector, soup)
        else:
            elements = soup.select(selector)
    except Exception as exc:
        return {"selector": selector, "status": "invalid", "error": str(exc), "matched_elements": 0}

    sample = ""
    if elements:
        first = elements[0]
        sample = first.get_text(" ", strip=True) if isinstance(first, Tag) else str(first)
    return {
        "selector": selector,
        "status": "ok",
        "matched_elements": len(elements),
        "sample": _compact_text(sample, 240),
    }


def _target_matches_rule_type(target: str, rule_type: str, patch_format: str) -> bool:
    if patch_format == "ylcraft":
        return target == "ylcraft_rule"
    expected = {
        "search": "rule_search",
        "toc": "rule_toc",
        "content": "rule_content",
    }.get(rule_type)
    return target in {expected, "search_url"}


def _parsed_summary(parsed_result: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(parsed_result or {})
    if isinstance(result.get("content"), str):
        result["content"] = _compact_text(result["content"], 800)
    if isinstance(result.get("items"), list) and len(result["items"]) > 5:
        result["items"] = result["items"][:5]
        result["items_truncated"] = True
    return result


def _safe_request_info(request_info: Dict[str, Any]) -> Dict[str, Any]:
    info = dict(request_info or {})
    headers = dict(info.get("headers") or {})
    for key in list(headers.keys()):
        if key.lower() == "cookie":
            headers[key] = "<hidden>"
    if headers:
        info["headers"] = headers
    return info


def _compact_value(value: Any, limit: int) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return {"_truncated_json": text[:limit]}


def _compact_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _string_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return low
    return max(low, min(high, parsed))
