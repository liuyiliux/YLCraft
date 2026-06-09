"""Book source test runner."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.services.novel.book_source_manager import BookSourceManager
from app.services.novel.cookie_manager import BookSourceCookieManager
from app.services.novel.rule_converter import convert_legado_to_ylcraft
from app.services.novel.rule_parser import RuleParser
from app.services.novel.source_parser import (
    parse_book_list,
    parse_chapter_content,
    parse_chapter_list,
)


class BookSourceTestManager:
    """Fetch a URL and return raw response plus parsed rule output."""

    RAW_HTML_LIMIT = 10000

    def __init__(self, db: Session):
        self.db = db
        self.source_manager = BookSourceManager(db)
        self.cookie_manager = BookSourceCookieManager(db)

    async def test_url(
        self,
        source_id: str,
        url: str,
        rule_type: Optional[str] = None,
        show_raw: bool = True,
    ) -> Dict[str, Any]:
        source = self.source_manager.get_source(source_id)
        if not source:
            raise ValueError("book source does not exist")
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")

        actual_rule_type = rule_type or self._detect_rule_type(url, source)
        if actual_rule_type not in {"search", "toc", "content"}:
            raise ValueError("rule_type must be one of: search, toc, content")

        headers = self.source_manager._build_headers(source, url)
        cookie_match = self.cookie_manager.get_cookie_match(url, source_id)

        start = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            verify=False,
        ) as client:
            response = await client.get(url, headers=headers)
        response_time_ms = int((time.perf_counter() - start) * 1000)
        html = response.text or ""

        parsed = self._parse_response(source, html, url, actual_rule_type)
        raw_html = html[: self.RAW_HTML_LIMIT] if show_raw else ""

        return {
            "success": True,
            "data": {
                "url": str(response.url),
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "response_time_ms": response_time_ms,
                "raw_html": raw_html,
                "raw_html_truncated": show_raw and len(html) > self.RAW_HTML_LIMIT,
                "parsed_result": parsed["parsed_result"],
                "debug_info": {
                    **parsed["debug_info"],
                    "cookie_used": cookie_match is not None,
                    "cookie_match": _safe_cookie_match(cookie_match),
                    "rule_type": actual_rule_type,
                },
            },
        }

    def _parse_response(self, source: Any, html: str, url: str, rule_type: str) -> Dict[str, Any]:
        start = time.perf_counter()
        rule_used: Dict[str, Any] = {}
        matched_elements = 0

        try:
            ylcraft_rule = convert_legado_to_ylcraft(
                {
                    "bookSourceName": source.bookSourceName,
                    "bookSourceUrl": source.bookSourceUrl,
                    "searchUrl": source.searchUrl or "",
                    "ruleSearch": source.ruleSearch or {},
                    "ruleBookInfo": source.ruleBookInfo or {},
                    "ruleToc": source.ruleToc or {},
                    "ruleContent": source.ruleContent or {},
                }
            )
            ylcraft_parsed = RuleParser(ylcraft_rule).parse(html, rule_type)
            matched_elements = ylcraft_parsed.get("debug", {}).get("matched_elements", 0)
            rule_used = ylcraft_parsed.get("debug", {}).get("rule_used", {})
        except Exception:
            ylcraft_parsed = None

        if rule_type == "search":
            rule_used = source.ruleSearch or rule_used
            items = parse_book_list(source.ruleSearch or {}, html, source.bookSourceUrl)
            parsed_result = {
                "type": "search",
                "parse_success": bool(items),
                "items": items,
                "total_items": len(items),
            }
            if matched_elements == 0:
                matched_elements = len(items)
        elif rule_type == "toc":
            rule_used = source.ruleToc or rule_used
            items = parse_chapter_list(source.ruleToc or {}, html, url)
            parsed_result = {
                "type": "toc",
                "parse_success": bool(items),
                "items": items,
                "total_items": len(items),
            }
            if matched_elements == 0:
                matched_elements = len(items)
        else:
            rule_used = source.ruleContent or rule_used
            content = parse_chapter_content(source.ruleContent or {}, html) or ""
            parsed_result = {
                "type": "content",
                "parse_success": bool(content),
                "content": content,
                "content_length": len(content),
            }
            if matched_elements == 0 and content:
                matched_elements = 1

        return {
            "parsed_result": parsed_result,
            "debug_info": {
                "rule_used": rule_used,
                "matched_elements": matched_elements,
                "parse_time_ms": int((time.perf_counter() - start) * 1000),
            },
        }

    def _detect_rule_type(self, url: str, source: Any) -> str:
        parsed = urlparse(url)
        haystack = f"{parsed.path}?{parsed.query}".lower()
        search_template = (source.searchUrl or "").lower()
        if source.ruleSearch and ("search" in haystack or "search" in search_template or "kw=" in haystack):
            return "search"
        if source.ruleToc and any(token in haystack for token in ("catalog", "toc", "list", "dir")):
            return "toc"
        if source.ruleContent and any(token in haystack for token in ("chapter", "read", ".html", ".htm")):
            return "content"
        if source.ruleSearch:
            return "search"
        if source.ruleToc:
            return "toc"
        return "content"


def _safe_cookie_match(cookie_match: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not cookie_match:
        return None
    return {
        "cookie_id": cookie_match.get("cookie_id"),
        "domain": cookie_match.get("domain"),
        "description": cookie_match.get("description"),
        "cookie_count": cookie_match.get("cookie_count", 0),
    }
