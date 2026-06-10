"""Book source test runner."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.services.browser.patchright_runtime import get_patchright_runtime
from app.services.browser.visible_session import get_visible_browser_session_manager
from app.services.novel.book_source_manager import BookSourceManager, _build_search_url
from app.services.novel.cookie_manager import BookSourceCookieManager, count_cookies
from app.services.novel.rule_converter import convert_legado_to_ylcraft, convert_ylcraft_to_legado
from app.services.novel.rule_parser import RuleParser
from app.services.novel.source_parser import (
    _is_jsonpath_rule,
    _parse_content_rule,
    _parse_css_rule,
    _select_elements,
    parse_book_list,
    parse_chapter_content,
    parse_chapter_list,
)

_VISIBLE_BOOK_SOURCE_SESSIONS: Dict[str, Dict[str, Any]] = {}


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
        actual_fetch_mode = (fetch_mode or "http").lower()
        if actual_fetch_mode not in {"http", "browser"}:
            raise ValueError("fetch_mode must be one of: http, browser")
        prepared = self._prepare_test_request(
            source_id=source_id,
            url=url,
            rule_type=rule_type,
            keyword=keyword,
            page=page,
            rule_format=rule_format,
            rule_override=rule_override,
            request_headers=request_headers,
            fetch_mode=actual_fetch_mode,
        )
        source = prepared["source"]
        url = prepared["url"]
        method = prepared["method"]
        data = prepared["data"]
        headers = prepared["headers"]
        actual_rule_type = prepared["rule_type"]
        actual_rule_format = prepared["rule_format"]
        cookie_match = prepared["cookie_match"]
        cookie_source = prepared["cookie_source"]
        browser_cookie = None

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
            browser_cookie = _browser_cookie_summary(final_url, rendered.cookies)
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
        diagnostics = _detect_response_diagnostics(
            status_code,
            html,
            actual_fetch_mode,
            parsed["parsed_result"],
            parsed["debug_info"],
        )

        return {
            "success": True,
            "data": {
                "url": final_url,
                "request_info": prepared["request_info"],
                "status_code": status_code,
                "headers": response_headers,
                "response_time_ms": response_time_ms,
                "raw_html": raw_html,
                "raw_html_truncated": show_raw and len(html) > self.RAW_HTML_LIMIT,
                "parsed_result": parsed["parsed_result"],
                "diagnostics": diagnostics,
                "browser_cookie": browser_cookie,
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

    async def start_visible_browser_session(
        self,
        source_id: str,
        url: Optional[str] = None,
        rule_type: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        rule_format: str = "legado",
        rule_override: Optional[Dict[str, Any]] = None,
        request_headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prepared = self._prepare_test_request(
            source_id=source_id,
            url=url,
            rule_type=rule_type,
            keyword=keyword,
            page=page,
            rule_format=rule_format,
            rule_override=rule_override,
            request_headers=request_headers,
            fetch_mode="visible_browser",
        )
        if prepared["method"] != "GET":
            raise ValueError("visible browser mode currently supports GET requests only")

        started = await get_visible_browser_session_manager().start_session(
            prepared["url"],
            headers=prepared["headers"],
        )
        session_id = started["session_id"]
        _VISIBLE_BOOK_SOURCE_SESSIONS[session_id] = {
            "source": prepared["source"],
            "rule_type": prepared["rule_type"],
            "rule_format": prepared["rule_format"],
            "request_info": prepared["request_info"],
            "cookie_match": prepared["cookie_match"],
            "cookie_source": prepared["cookie_source"],
        }
        return {
            "success": True,
            "data": {
                "session_id": session_id,
                "url": started["url"],
                "status_code": started.get("status_code", 0),
                "headers": started.get("headers", {}),
                "request_info": prepared["request_info"],
            },
        }

    async def snapshot_visible_browser_session(
        self,
        session_id: str,
        show_raw: bool = True,
    ) -> Dict[str, Any]:
        meta = _VISIBLE_BOOK_SOURCE_SESSIONS.get(session_id)
        if not meta:
            raise ValueError("browser session does not exist")
        snapshot = await get_visible_browser_session_manager().snapshot_session(session_id)
        source = meta["source"]
        actual_rule_type = meta["rule_type"]
        actual_rule_format = meta["rule_format"]
        html = snapshot.get("html") or ""
        status_code = int(snapshot.get("status_code") or 0)
        final_url = snapshot.get("url") or meta["request_info"]["url"]
        parsed = self._parse_response(source, html, final_url, actual_rule_type, actual_rule_format)
        diagnostics = _detect_response_diagnostics(
            status_code,
            html,
            "visible_browser",
            parsed["parsed_result"],
            parsed["debug_info"],
        )
        raw_html = html[: self.RAW_HTML_LIMIT] if show_raw else ""
        browser_cookie = _browser_cookie_summary(final_url, snapshot.get("cookies") or [])
        return {
            "success": True,
            "data": {
                "url": final_url,
                "request_info": meta["request_info"],
                "status_code": status_code,
                "headers": snapshot.get("headers") or {},
                "response_time_ms": 0,
                "raw_html": raw_html,
                "raw_html_truncated": show_raw and len(html) > self.RAW_HTML_LIMIT,
                "parsed_result": parsed["parsed_result"],
                "diagnostics": diagnostics,
                "browser_cookie": browser_cookie,
                "debug_info": {
                    **parsed["debug_info"],
                    "cookie_used": meta["cookie_source"] != "none",
                    "cookie_source": meta["cookie_source"],
                    "cookie_match": _safe_cookie_match(meta["cookie_match"]),
                    "rule_type": actual_rule_type,
                    "rule_format": actual_rule_format,
                    "fetch_mode": "visible_browser",
                    "diagnostics": diagnostics,
                },
            },
        }

    async def close_visible_browser_session(self, session_id: str) -> Dict[str, Any]:
        _VISIBLE_BOOK_SOURCE_SESSIONS.pop(session_id, None)
        closed = await get_visible_browser_session_manager().close_session(session_id)
        return {"success": True, "data": {"closed": closed}}

    def _prepare_test_request(
        self,
        source_id: str,
        url: Optional[str],
        rule_type: Optional[str],
        keyword: Optional[str],
        page: int,
        rule_format: str,
        rule_override: Optional[Dict[str, Any]],
        request_headers: Optional[Dict[str, Any]],
        fetch_mode: str,
    ) -> Dict[str, Any]:
        source = self.source_manager.get_source(source_id)
        if not source:
            raise ValueError("book source does not exist")
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
        return {
            "source": source,
            "url": url,
            "method": method,
            "data": data,
            "headers": headers,
            "rule_type": actual_rule_type,
            "rule_format": actual_rule_format,
            "cookie_match": cookie_match,
            "cookie_source": cookie_source,
            "request_info": {
                "url": url,
                "method": method,
                "data": data,
                "headers": _safe_headers(headers),
                "keyword": keyword,
                "page": page,
                "rule_format": actual_rule_format,
                "fetch_mode": fetch_mode,
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
        rule_trace: list[Dict[str, Any]] = []

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
            rule_trace = _trace_ylcraft_rules(ylcraft_rule or {}, html, rule_type)
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
                    "rule_trace": rule_trace,
                },
            }

        if rule_type == "search":
            rule_used = source.ruleSearch or rule_used
            rule_trace = _trace_legado_rules(source.ruleSearch or {}, html, "search")
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
            rule_trace = _trace_legado_rules(source.ruleToc or {}, html, "toc")
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
            rule_trace = _trace_legado_rules(source.ruleContent or {}, html, "content")
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
                "rule_trace": rule_trace,
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


def _browser_cookie_summary(final_url: str, cookies: Optional[list[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    if not cookies:
        return None
    pairs = []
    domains = []
    seen = set()
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        pairs.append(f"{name}={value}")
        domain = str(cookie.get("domain") or "").strip()
        if domain and domain not in domains:
            domains.append(domain)
    cookie_content = "; ".join(pairs)
    host = urlparse(final_url).hostname or ""
    if not cookie_content:
        return None
    return {
        "domain": host,
        "cookie_count": count_cookies(cookie_content),
        "cookie_content": cookie_content,
        "source_domains": domains,
    }


def _detect_response_diagnostics(
    status_code: int,
    html: str,
    fetch_mode: str,
    parsed_result: Optional[Dict[str, Any]] = None,
    debug_info: Optional[Dict[str, Any]] = None,
) -> list[Dict[str, str]]:
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
    if status_code in {403, 412, 429}:
        messages = {
            403: "响应被站点拒绝",
            412: "响应疑似命中风控校验",
            429: "响应疑似触发访问频率限制",
        }
        diagnostics.append(
            {
                "type": f"http_{status_code}",
                "message": messages[status_code],
                "suggestion": "建议检查 Cookie 是否过期、Referer/User-Agent 是否匹配真实浏览器，并降低测试频率。",
            }
        )
    elif status_code >= 500:
        diagnostics.append(
            {
                "type": "server_error",
                "message": f"站点返回 HTTP {status_code}",
                "suggestion": "优先确认目标站点当前可访问；如果浏览器可访问但测试失败，再检查请求头和 Cookie。",
            }
        )

    stripped = (html or "").strip()
    if status_code < 400 and not stripped:
        diagnostics.append(
            {
                "type": "empty_response",
                "message": "响应内容为空",
                "suggestion": "检查请求 URL、请求方式和搜索模板；POST 搜索还需要确认 body 是否生成正确。",
            }
        )
    elif _looks_like_js_shell_page(stripped):
        diagnostics.append(
            {
                "type": "js_shell_page",
                "message": "响应疑似 JS 壳页面",
                "suggestion": "普通请求无法执行页面脚本，建议使用浏览器渲染模式，或寻找该页面背后的接口 URL。",
            }
        )

    parse_success = bool((parsed_result or {}).get("parse_success"))
    matched_elements = int((debug_info or {}).get("matched_elements") or 0)
    if status_code < 400 and stripped and not parse_success and matched_elements == 0 and not is_probe_page:
        diagnostics.append(
            {
                "type": "rule_no_match",
                "message": "规则没有命中页面元素",
                "suggestion": "查看规则命中视图，先修正列表/正文根选择器，再逐项调字段规则。",
            }
        )
    return diagnostics


def _looks_like_js_shell_page(html: str) -> bool:
    if len(html) > 2500:
        return False
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("body")
        text = body.get_text(strip=True) if body else ""
        scripts = len(soup.find_all("script"))
        return len(text) < 80 and scripts > 0
    except Exception:
        return False


def _trace_legado_rules(rule: Dict[str, Any], html: str, rule_type: str) -> list[Dict[str, Any]]:
    if not rule:
        return []
    if rule_type == "search":
        return _trace_legado_list_rules(rule, html, "bookList", ["name", "author", "bookUrl", "coverUrl", "intro"])
    if rule_type == "toc":
        return _trace_legado_list_rules(rule, html, "chapterList", ["chapterName", "chapterUrl"])
    return _trace_legado_content_rules(rule, html)


def _trace_legado_list_rules(
    rule: Dict[str, Any],
    html: str,
    list_key: str,
    field_keys: list[str],
) -> list[Dict[str, Any]]:
    trace: list[Dict[str, Any]] = []
    list_rule = rule.get(list_key)
    list_elements = _safe_select_legado(list_rule, html)
    trace.append(_trace_item(list_key, list_rule, len(list_elements), _element_sample(list_elements[0]) if list_elements else ""))
    first_html = str(list_elements[0]) if list_elements else ""
    for key in field_keys:
        field_rule = rule.get(key)
        if not field_rule:
            continue
        field_elements = _safe_select_legado(field_rule, first_html) if first_html else []
        sample = _safe_parse_legado_value(field_rule, first_html) if first_html else ""
        trace.append(_trace_item(key, field_rule, len(field_elements), sample))
    return trace


def _trace_legado_content_rules(rule: Dict[str, Any], html: str) -> list[Dict[str, Any]]:
    content_rule = rule.get("content")
    selector = ""
    if isinstance(content_rule, str):
        selector, _, _ = _parse_content_rule(content_rule)
    content_elements = _safe_select_legado(selector or content_rule, html)
    trace = [
        _trace_item("content", content_rule, len(content_elements), _element_sample(content_elements[0]) if content_elements else "")
    ]
    remove_rule = rule.get("removeContent")
    if remove_rule:
        trace.append(_trace_item("removeContent", remove_rule, len(_safe_select_legado(remove_rule, html)), ""))
    return trace


def _trace_ylcraft_rules(rule: Dict[str, Any], html: str, rule_type: str) -> list[Dict[str, Any]]:
    if not rule:
        return []
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    trace: list[Dict[str, Any]] = []
    if rule_type in {"search", "toc"}:
        container = (rule.get(rule_type) or {}).get("items") or {}
        selector = container.get("selector") or ""
        elements = _safe_select_css(soup, selector)
        trace.append(_trace_item("items.selector", selector, len(elements), _element_sample(elements[0]) if elements else ""))
        first = elements[0] if elements else None
        for field_name, field_config in (container.get("fields") or {}).items():
            field_selector = (field_config or {}).get("selector") or ""
            field_elements = _safe_select_css(first, field_selector) if first is not None else []
            sample = RuleParser(rule).extract_field(first, field_config) if first is not None else ""
            trace.append(_trace_item(f"fields.{field_name}", field_selector or "<root>", len(field_elements) if field_selector else (1 if first else 0), sample))
        return trace

    content_rule = rule.get("content") or {}
    selector = content_rule.get("selector") or ""
    elements = _safe_select_css(soup, selector)
    trace.append(_trace_item("content.selector", selector, len(elements), _element_sample(elements[0]) if elements else ""))
    first = elements[0] if elements else None
    for remove_selector in content_rule.get("remove") or []:
        trace.append(_trace_item("content.remove", remove_selector, len(_safe_select_css(first, remove_selector)) if first else 0, ""))
    return trace


def _safe_select_legado(rule_value: Any, html: Any) -> list[Any]:
    selector = _selection_rule(rule_value)
    if not selector:
        return []
    try:
        return _select_elements(selector, html)
    except Exception:
        return []


def _safe_parse_legado_value(rule_value: Any, html: str) -> str:
    if not isinstance(rule_value, str) or _is_jsonpath_rule(rule_value):
        return ""
    try:
        return _short_text(_parse_css_rule(rule_value, html) or "")
    except Exception:
        return ""


def _selection_rule(rule_value: Any) -> str:
    if not isinstance(rule_value, str) or _is_jsonpath_rule(rule_value):
        return ""
    selector = rule_value.strip()
    if not selector or selector.startswith("@js:") or selector.startswith("{{"):
        return ""
    if "<js>" in selector:
        selector = selector.split("<js>", 1)[0].rstrip("@").strip()
    if "@js:" in selector:
        selector = selector.split("@js:", 1)[0].rstrip("@").strip()
    if "##" in selector and not selector.startswith("##"):
        selector = selector.split("##", 1)[0].strip()
    if "@" in selector:
        parts = [part for part in selector.split("@") if part]
        if parts and (parts[-1] in {"text", "html"} or _looks_like_attr_name(parts[-1])):
            parts = parts[:-1]
        selector = "@".join(parts)
    return selector


def _looks_like_attr_name(value: str) -> bool:
    return value in {
        "href",
        "src",
        "title",
        "alt",
        "content",
        "data-src",
        "data-original",
        "data-bid",
        "data-cid",
    }


def _safe_select_css(root: Any, selector: str) -> list[Any]:
    if root is None or not selector:
        return []
    try:
        return root.select(selector)
    except Exception:
        return []


def _trace_item(name: str, rule: Any, matches: int, sample: str) -> Dict[str, Any]:
    return {
        "name": name,
        "rule": rule if rule is not None else "",
        "matches": matches,
        "sample": _short_text(sample),
    }


def _element_sample(element: Any) -> str:
    if element is None:
        return ""
    try:
        text = element.get_text(" ", strip=True)
        return text or str(element)[:160]
    except Exception:
        return str(element)[:160]


def _short_text(value: Any, limit: int = 180) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    return text[:limit] + ("..." if len(text) > limit else "")


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
