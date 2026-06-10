"""Book source test runner."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.services.browser.patchright_runtime import get_patchright_runtime
from app.services.novel.book_source_manager import BookSourceManager, _build_search_url
from app.services.novel.cookie_manager import BookSourceCookieManager, count_cookies
from app.services.novel.rule_converter import convert_legado_to_ylcraft, convert_ylcraft_to_legado
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
        url: Optional[str] = None,
        rule_type: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        show_raw: bool = True,
        rule_format: str = "legado",
        rule_override: Optional[Dict[str, Any]] = None,
        request_headers: Optional[Dict[str, Any]] = None,
        fetch_mode: str = "http",
    ) -> Dict[str, Any]:
        source = self.source_manager.get_source(source_id)
        if not source:
            raise ValueError("book source does not exist")
        actual_fetch_mode = (fetch_mode or "http").lower()
        if actual_fetch_mode not in {"http", "browser"}:
            raise ValueError("fetch_mode must be one of: http, browser")
        source, actual_rule_format = self._build_test_source(source, rule_format, rule_override)
        if keyword and (rule_type is None or rule_type == "search"):
            search_config = _build_search_url(source.searchUrl or "", keyword, source.bookSourceUrl, page=page)
            url = search_config.get("url") or url
            method = str(search_config.get("method") or "GET").upper()
            data = search_config.get("data")
            rule_type = "search"
        else:
            method = "GET"
            data = None
        if not url:
            raise ValueError("url is required unless a search keyword is provided")
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")

        actual_rule_type = rule_type or self._detect_rule_type(url, source)
        if actual_rule_type not in {"search", "toc", "content"}:
            raise ValueError("rule_type must be one of: search, toc, content")

        header_overrides = _normalize_request_headers(request_headers)
        headers = self.source_manager._build_headers(source, url)
        headers.update(header_overrides)
        cookie_match = self.cookie_manager.get_cookie_match(url, source_id)
        cookie_source = _detect_cookie_source(headers, cookie_match, header_overrides)

        start = time.perf_counter()
        if actual_fetch_mode == "browser":
            try:
                rendered = await get_patchright_runtime().fetch_page(
                    url,
                    method=method,
                    headers=headers,
                    timeout_ms=30000,
                    wait_until="networkidle",
                )
            except RuntimeError as exc:
                raise ValueError(str(exc)) from exc
            final_url = rendered.url
            status_code = rendered.status_code
            response_headers = rendered.headers
            html = rendered.html or ""
        else:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                verify=False,
                trust_env=False,
            ) as client:
                try:
                    if method == "POST":
                        response = await client.post(url, data=data, headers=headers)
                    else:
                        response = await client.get(url, headers=headers)
                except httpx.HTTPError as exc:
                    message = str(exc) or "no details"
                    raise ValueError(f"request failed for {url}: {exc.__class__.__name__}: {message}") from exc
            final_url = str(response.url)
            status_code = response.status_code
            response_headers = dict(response.headers)
            html = response.text or ""
        response_time_ms = int((time.perf_counter() - start) * 1000)

        parsed = self._parse_response(source, html, url, actual_rule_type, actual_rule_format)
        raw_html = html[: self.RAW_HTML_LIMIT] if show_raw else ""
        diagnostics = _detect_response_diagnostics(status_code, html, actual_fetch_mode)

        return {
            "success": True,
            "data": {
                "url": final_url,
                "request_info": {
                    "url": url,
                    "method": method,
                    "data": data,
                    "headers": _safe_headers(headers),
                    "keyword": keyword,
                    "page": page,
                    "rule_format": actual_rule_format,
                    "fetch_mode": actual_fetch_mode,
                },
                "status_code": status_code,
                "headers": response_headers,
                "response_time_ms": response_time_ms,
                "raw_html": raw_html,
                "raw_html_truncated": show_raw and len(html) > self.RAW_HTML_LIMIT,
                "parsed_result": parsed["parsed_result"],
                "diagnostics": diagnostics,
                "debug_info": {
                    **parsed["debug_info"],
                    "cookie_used": cookie_source != "none",
                    "cookie_source": cookie_source,
                    "cookie_match": _safe_cookie_match(cookie_match),
                    "rule_type": actual_rule_type,
                    "rule_format": actual_rule_format,
                    "fetch_mode": actual_fetch_mode,
                    "diagnostics": diagnostics,
                },
            },
        }

    def _parse_response(
        self,
        source: Any,
        html: str,
        url: str,
        rule_type: str,
        rule_format: str = "legado",
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        rule_used: Dict[str, Any] = {}
        matched_elements = 0
        ylcraft_rule = None
        ylcraft_parsed = None
        ylcraft_error = None

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
            ) if not source.ylcraftRule else source.ylcraftRule
            ylcraft_parsed = RuleParser(ylcraft_rule).parse(html, rule_type)
            matched_elements = ylcraft_parsed.get("debug", {}).get("matched_elements", 0)
            rule_used = ylcraft_parsed.get("debug", {}).get("rule_used", {})
        except Exception as exc:
            ylcraft_error = str(exc)

        if rule_format == "ylcraft":
            if not ylcraft_parsed:
                parsed_result = {
                    "type": rule_type,
                    "parse_success": False,
                    "error": ylcraft_error or "YLCraft rule parse failed",
                }
            else:
                parsed_result = {k: v for k, v in ylcraft_parsed.items() if k != "debug"}
                rule_used = ylcraft_parsed.get("debug", {}).get("rule_used", {})
                matched_elements = ylcraft_parsed.get("debug", {}).get("matched_elements", 0)
            return {
                "parsed_result": parsed_result,
                "debug_info": {
                    "rule_used": rule_used,
                    "matched_elements": matched_elements,
                    "parse_time_ms": int((time.perf_counter() - start) * 1000),
                    "converted_ylcraft_rule": ylcraft_rule,
                    "conversion_warnings": (ylcraft_rule or {}).get("conversion_warnings", []),
                    "ylcraft_error": ylcraft_error,
                },
            }

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
                "converted_ylcraft_rule": ylcraft_rule,
                "ylcraft_result": _without_debug(ylcraft_parsed) if ylcraft_parsed else None,
                "conversion_warnings": (ylcraft_rule or {}).get("conversion_warnings", []),
                "ylcraft_error": ylcraft_error,
            },
        }

    def _build_test_source(
        self,
        source: Any,
        rule_format: str,
        rule_override: Optional[Dict[str, Any]],
    ) -> tuple[Any, str]:
        actual_rule_format = (rule_format or "legado").lower()
        if actual_rule_format not in {"legado", "ylcraft"}:
            raise ValueError("rule_format must be one of: legado, ylcraft")
        if not rule_override:
            return source, actual_rule_format

        if hasattr(source, "model_copy"):
            test_source = source.model_copy(deep=True)
        else:
            test_source = source.copy(deep=True)

        if actual_rule_format == "ylcraft":
            ylcraft_rule = rule_override.get("ylcraft_rule") or test_source.ylcraftRule
            if not isinstance(ylcraft_rule, dict):
                raise ValueError("ylcraft_rule must be a JSON object")
            converted = convert_ylcraft_to_legado(ylcraft_rule)
            test_source.searchUrl = (
                rule_override.get("search_url")
                or converted.get("searchUrl")
                or test_source.searchUrl
                or ""
            )
            test_source.ruleSearch = _rule_or_empty(converted.get("ruleSearch"))
            test_source.ruleBookInfo = _rule_or_empty(converted.get("ruleBookInfo"))
            test_source.ruleToc = _rule_or_empty(converted.get("ruleToc"))
            test_source.ruleContent = _rule_or_empty(converted.get("ruleContent"))
            test_source.ruleExplore = _rule_or_empty(rule_override.get("rule_explore"))
            test_source.ylcraftRule = ylcraft_rule
            return test_source, actual_rule_format

        if "search_url" in rule_override:
            test_source.searchUrl = rule_override.get("search_url") or ""
        field_map = {
            "rule_search": "ruleSearch",
            "rule_book_info": "ruleBookInfo",
            "rule_toc": "ruleToc",
            "rule_content": "ruleContent",
            "rule_explore": "ruleExplore",
        }
        for payload_key, attr_name in field_map.items():
            if payload_key in rule_override:
                setattr(test_source, attr_name, _rule_or_empty(rule_override.get(payload_key), payload_key))
        if isinstance(rule_override.get("ylcraft_rule"), dict):
            test_source.ylcraftRule = rule_override["ylcraft_rule"]
        else:
            test_source.ylcraftRule = convert_legado_to_ylcraft(
                {
                    "bookSourceName": test_source.bookSourceName,
                    "bookSourceUrl": test_source.bookSourceUrl,
                    "searchUrl": test_source.searchUrl or "",
                    "ruleSearch": test_source.ruleSearch or {},
                    "ruleBookInfo": test_source.ruleBookInfo or {},
                    "ruleToc": test_source.ruleToc or {},
                    "ruleContent": test_source.ruleContent or {},
                }
            )
        return test_source, actual_rule_format

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


def _safe_headers(headers: Dict[str, str]) -> Dict[str, str]:
    safe = dict(headers or {})
    for name, value in list(safe.items()):
        if name.lower() == "cookie" and value:
            safe[name] = f"<hidden; {count_cookies(value)} cookies>"
    return safe


def _normalize_request_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not headers:
        return {}
    blocked = {
        "host",
        "content-length",
        "connection",
        "transfer-encoding",
        "accept-encoding",
    }
    normalized: Dict[str, str] = {}
    for key, value in headers.items():
        if value is None:
            continue
        name = str(key).strip()
        if not name or name.startswith(":") or name.lower() in blocked:
            continue
        normalized[name] = str(value)
    return normalized


def _detect_cookie_source(
    headers: Dict[str, str],
    cookie_match: Optional[Dict[str, Any]],
    header_overrides: Dict[str, str],
) -> str:
    if any(name.lower() == "cookie" for name in header_overrides):
        return "manual_header"
    if cookie_match is not None:
        return "book_source_cookie"
    if any(name.lower() == "cookie" for name in headers):
        return "legacy_source_cookie"
    return "none"


def _detect_response_diagnostics(status_code: int, html: str, fetch_mode: str) -> list[Dict[str, str]]:
    source = (html or "").lower()
    diagnostics: list[Dict[str, str]] = []
    is_probe_page = (
        status_code == 202
        and ("probe.js" in source or "debugger" in source or "aegis" in source)
    )
    if is_probe_page:
        suggestion = (
            "当前普通 HTTP 请求命中站点反爬探测页，建议切换到浏览器渲染模式，或补全从真实浏览器复制的 Cookie。"
            if fetch_mode == "http"
            else "浏览器渲染模式仍命中反爬探测页，请重新获取当前浏览器 Cookie，必要时使用可见浏览器完成站点校验后再测试。"
        )
        diagnostics.append(
            {
                "type": "anti_bot_probe",
                "message": "响应疑似站点反爬探测页",
                "suggestion": suggestion,
            }
        )
    return diagnostics


def _without_debug(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not result:
        return None
    return {key: value for key, value in result.items() if key != "debug"}


def _rule_or_empty(value: Any, name: str = "rule") -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ValueError(f"{name} must be a JSON object")
