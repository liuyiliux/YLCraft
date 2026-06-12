"""Convert Legado book source rules into YLCraft rule format."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Tuple


SUPPORTED_YLCRAFT_VERSION = "1.0"
_JS_TAG_PATTERN = re.compile(r"<js>(.*?)</js>", re.DOTALL | re.IGNORECASE)
_SUPPORTED_TRANSFORM_PATHS = {
    "ruleSearch.name",
    "ruleSearch.author",
    "ruleSearch.bookUrl",
    "ruleSearch.coverUrl",
    "ruleSearch.intro",
    "ruleSearch.kind",
    "ruleSearch.wordCount",
    "ruleBookInfo.name",
    "ruleBookInfo.author",
    "ruleBookInfo.coverUrl",
    "ruleBookInfo.intro",
    "ruleBookInfo.tocUrl",
    "ruleBookInfo.kind",
    "ruleBookInfo.wordCount",
    "ruleToc.chapterName",
    "ruleToc.chapterUrl",
    "ruleContent.content",
}


def convert_legado_to_ylcraft(legado_json: Any) -> Dict[str, Any]:
    if isinstance(legado_json, str):
        source = json.loads(legado_json)
    else:
        source = legado_json or {}

    warnings: List[str] = []
    rule: Dict[str, Any] = {
        "version": "1.0",
        "name": source.get("bookSourceName") or source.get("name") or "",
        "base_url": source.get("bookSourceUrl") or source.get("base_url") or "",
        "conversion_warnings": warnings,
    }

    search = _convert_search(source.get("ruleSearch") or {}, source.get("searchUrl") or "", warnings)
    if search:
        rule["search"] = search

    book_info = _convert_book_info(source.get("ruleBookInfo") or {}, warnings)
    if book_info:
        rule["book_info"] = book_info

    toc = _convert_toc(source.get("ruleToc") or {}, warnings)
    if toc:
        rule["toc"] = toc

    content = _convert_content(source.get("ruleContent") or {}, warnings)
    if content:
        rule["content"] = content

    _scan_unsupported_js(source, warnings)
    return rule


def convert_ylcraft_to_legado(ylcraft_json: Any) -> Dict[str, Any]:
    if isinstance(ylcraft_json, str):
        rule = json.loads(ylcraft_json)
    else:
        rule = copy.deepcopy(ylcraft_json or {})

    source: Dict[str, Any] = {
        "bookSourceName": rule.get("name") or "",
        "bookSourceUrl": rule.get("base_url") or "",
        "bookSourceType": 0,
        "enabled": True,
        "searchUrl": "",
        "ruleSearch": {},
        "ruleBookInfo": {},
        "ruleToc": {},
        "ruleContent": {},
        "ruleFormat": "ylcraft",
        "ruleVersion": rule.get("version") or SUPPORTED_YLCRAFT_VERSION,
        "ylcraftRule": rule,
        "originalFormat": "ylcraft",
        "originalSource": rule,
    }

    search = rule.get("search") or {}
    if search:
        source["searchUrl"] = search.get("url") or ""
        items = search.get("items") or {}
        rule_search: Dict[str, Any] = {}
        if items.get("selector"):
            rule_search["bookList"] = items["selector"]
        fields = items.get("fields") or {}
        _assign_field(rule_search, "name", fields.get("title"))
        _assign_field(rule_search, "author", fields.get("author"))
        _assign_field(rule_search, "bookUrl", fields.get("url"))
        _assign_field(rule_search, "coverUrl", fields.get("cover"))
        _assign_field(rule_search, "intro", fields.get("desc"))
        _assign_field(rule_search, "kind", fields.get("category"))
        source["ruleSearch"] = rule_search

    book_info = rule.get("book_info") or {}
    if book_info:
        fields = book_info.get("fields") or {}
        rule_book_info: Dict[str, Any] = {}
        _assign_field(rule_book_info, "name", fields.get("title"))
        _assign_field(rule_book_info, "author", fields.get("author"))
        _assign_field(rule_book_info, "coverUrl", fields.get("cover"))
        _assign_field(rule_book_info, "intro", fields.get("intro"))
        _assign_field(rule_book_info, "tocUrl", fields.get("toc_url"))
        _assign_field(rule_book_info, "kind", fields.get("category"))
        source["ruleBookInfo"] = rule_book_info

    toc = rule.get("toc") or {}
    if toc:
        items = toc.get("items") or {}
        rule_toc: Dict[str, Any] = {}
        if items.get("selector"):
            rule_toc["chapterList"] = items["selector"]
        fields = items.get("fields") or {}
        _assign_field(rule_toc, "chapterName", fields.get("title"))
        _assign_field(rule_toc, "chapterUrl", fields.get("url"))
        source["ruleToc"] = rule_toc

    content = rule.get("content") or {}
    if content:
        rule_content: Dict[str, Any] = {}
        if content.get("selector"):
            rule_content["content"] = _append_transforms_to_legado_rule(
                str(content["selector"]),
                content.get("transforms") or [],
            )
        remove = content.get("remove") or []
        if isinstance(remove, list) and remove:
            rule_content["removeContent"] = ", ".join(str(item) for item in remove if item)
        elif isinstance(remove, str):
            rule_content["removeContent"] = remove
        source["ruleContent"] = rule_content

    return source


def detect_source_format(source: Dict[str, Any]) -> str:
    if is_ylcraft_rule(source):
        return "ylcraft"
    if any(key in source for key in ("bookSourceName", "bookSourceUrl", "ruleSearch", "ruleToc", "ruleContent")):
        return "legado"
    return "unknown"


def normalize_import_source(source: Dict[str, Any]) -> Dict[str, Any]:
    source_format = detect_source_format(source)
    if source_format == "ylcraft":
        legado = convert_ylcraft_to_legado(source)
        legado["ruleFormat"] = "ylcraft"
        legado["ruleVersion"] = source.get("version") or SUPPORTED_YLCRAFT_VERSION
        legado["ylcraftRule"] = source
        legado["originalFormat"] = "ylcraft"
        legado["originalSource"] = source
        return legado
    if source_format == "legado":
        legado = copy.deepcopy(source)
        ylcraft_rule = convert_legado_to_ylcraft(source)
        legado["ruleFormat"] = "ylcraft"
        legado["ruleVersion"] = ylcraft_rule.get("version", SUPPORTED_YLCRAFT_VERSION)
        legado["ylcraftRule"] = ylcraft_rule
        legado["originalFormat"] = "legado"
        legado["originalSource"] = source
        return legado
    raise ValueError("unsupported book source format")


def parse_mixed_book_source_json(json_str: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse failed: {e}")

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("book source JSON must be an object or array")

    normalized = []
    errors = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"item {index}: expected object")
            continue
        try:
            normalized.append(normalize_import_source(item))
        except Exception as e:
            name = item.get("bookSourceName") or item.get("name") or f"item {index}"
            errors.append(f"{name}: {e}")

    if errors and not normalized:
        raise ValueError("; ".join(errors))
    return normalized


def convert_selector(legado_selector: str) -> str:
    selector = (legado_selector or "").strip()
    if not selector:
        return ""

    selector, _ = _extract_rule_transforms(selector)
    selector = selector.split("##", 1)[0]
    parts = [part for part in selector.split("@") if part]
    css_parts: List[str] = []
    for part in parts:
        if _is_extract_directive(part):
            continue
        css = _convert_selector_part(part)
        if css:
            css_parts.append(css)
    return " ".join(css_parts)


def convert_field_rule(legado_rule: str) -> Dict[str, Any]:
    raw_rule, transforms = _extract_rule_transforms(legado_rule or "")
    selector, field_type, attr = _split_field_rule(raw_rule)
    config: Dict[str, Any] = {
        "selector": selector,
        "type": field_type,
    }
    if attr:
        config["attr"] = attr
    if transforms:
        config["transforms"] = transforms
    return config


def is_ylcraft_rule(source: Dict[str, Any]) -> bool:
    if not isinstance(source, dict):
        return False
    has_identity = "version" in source and ("name" in source or "base_url" in source)
    has_rule_section = any(key in source for key in ("search", "book_info", "toc", "content"))
    return bool(has_identity and has_rule_section)


def _convert_search(rule_search: Dict[str, Any], search_url: str, warnings: List[str]) -> Dict[str, Any]:
    if not rule_search:
        return {}
    fields = {}
    mapping = {
        "name": "title",
        "author": "author",
        "bookUrl": "url",
        "coverUrl": "cover",
        "intro": "desc",
        "kind": "category",
        "wordCount": "word_count",
    }
    for legado_key, ylcraft_key in mapping.items():
        if rule_search.get(legado_key):
            fields[ylcraft_key] = convert_field_rule(str(rule_search[legado_key]))
    selector = convert_selector(str(rule_search.get("bookList") or ""))
    if not selector:
        warnings.append("ruleSearch.bookList could not be converted")
    return {
        "url": _convert_template(search_url),
        "method": "POST" if '"POST"' in search_url.upper() else "GET",
        "headers": {},
        "items": {
            "selector": selector,
            "fields": fields,
        },
    }


def _convert_book_info(rule_book_info: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    if not rule_book_info:
        return {}
    mapping = {
        "name": "title",
        "author": "author",
        "coverUrl": "cover",
        "intro": "intro",
        "tocUrl": "toc_url",
        "kind": "category",
        "wordCount": "word_count",
    }
    fields = {
        ylcraft_key: convert_field_rule(str(rule_book_info[legado_key]))
        for legado_key, ylcraft_key in mapping.items()
        if rule_book_info.get(legado_key)
    }
    return {"fields": fields} if fields else {}


def _convert_toc(rule_toc: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    if not rule_toc:
        return {}
    fields = {}
    if rule_toc.get("chapterName"):
        fields["title"] = convert_field_rule(str(rule_toc["chapterName"]))
    if rule_toc.get("chapterUrl"):
        fields["url"] = convert_field_rule(str(rule_toc["chapterUrl"]))
    selector = convert_selector(str(rule_toc.get("chapterList") or ""))
    if not selector:
        warnings.append("ruleToc.chapterList could not be converted")
    return {
        "items": {
            "selector": selector,
            "fields": fields,
        },
    }


def _convert_content(rule_content: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    if not rule_content:
        return {}
    raw_content, transforms = _extract_rule_transforms(str(rule_content.get("content") or ""))
    selector = convert_selector(raw_content)
    remove = rule_content.get("removeContent") or []
    if isinstance(remove, str):
        remove = [convert_selector(remove)] if remove else []
    config = {
        "selector": selector,
        "remove": [item for item in remove if item],
        "text_only": True,
    }
    if transforms:
        config["transforms"] = transforms
    return config


def _split_field_rule(rule: str) -> Tuple[str, str, str]:
    parts = [part for part in rule.split("@") if part]
    directive = "text"
    attr = ""
    if parts and _is_extract_directive(parts[-1]):
        last = parts.pop()
        if last in {"text", "html"}:
            directive = last
        else:
            directive = "attr"
            attr = last
    elif parts:
        inferred_attr = _infer_attr(parts[-1])
        if inferred_attr:
            directive = "attr"
            attr = inferred_attr
    selector = convert_selector("@".join(parts))
    return selector, directive, attr


def _convert_selector_part(part: str) -> str:
    item = part.strip()
    item = re.sub(r"[.!]\d+$", "", item)
    if item.startswith("tag."):
        return item[4:]
    if item.startswith("class."):
        return "." + item[6:]
    if item.startswith("id#"):
        return "#" + item[3:]
    if item.startswith("id."):
        return "#" + item[3:]
    return item


def _is_extract_directive(part: str) -> bool:
    return part in {
        "text",
        "html",
        "href",
        "src",
        "alt",
        "title",
        "content",
        "value",
        "data-src",
        "data-original",
    }


def _infer_attr(selector: str) -> str:
    if selector.endswith("img") or "img" in selector:
        return "src"
    if selector.endswith("a") or "tag.a" in selector:
        return "href"
    return ""


def _convert_template(value: str) -> str:
    result = (value or "").replace("{{key}}", "{{keyword}}")
    result = re.sub(r"(?<!\{)\{key\}(?!\})", "{{keyword}}", result)
    result = re.sub(r"(?<!\{)\{page\}(?!\})", "{{page}}", result)
    return result


def _assign_field(target: Dict[str, Any], key: str, config: Any) -> None:
    if isinstance(config, dict):
        target[key] = _field_to_legado(config)


def _field_to_legado(config: Dict[str, Any]) -> str:
    selector = config.get("selector") or ""
    field_type = config.get("type", "text")
    if field_type == "attr":
        attr = config.get("attr") or _infer_attr(selector) or "href"
        rule = f"{selector}@{attr}" if selector else attr
        return _append_transforms_to_legado_rule(rule, config.get("transforms") or [])
    if field_type == "html":
        rule = f"{selector}@html" if selector else "html"
        return _append_transforms_to_legado_rule(rule, config.get("transforms") or [])
    rule = f"{selector}@text" if selector else "text"
    return _append_transforms_to_legado_rule(rule, config.get("transforms") or [])


def _scan_unsupported_js(value: Any, warnings: List[str], path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _scan_unsupported_js(child, warnings, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_unsupported_js(child, warnings, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if ("@js:" in lowered or "<js>" in lowered) and path not in _SUPPORTED_TRANSFORM_PATHS:
            warnings.append(f"unsupported JS rule at {path}")
        if "{{" in value and path != "searchUrl":
            warnings.append(f"unsupported template rule at {path}")


def _extract_rule_transforms(rule_value: str) -> Tuple[str, List[Dict[str, Any]]]:
    text = (rule_value or "").strip()
    transforms: List[Dict[str, Any]] = []

    def collect_js(match: re.Match[str]) -> str:
        code = match.group(1).strip()
        if code:
            transforms.append({"type": "js", "code": code})
        return ""

    text = _JS_TAG_PATTERN.sub(collect_js, text)
    js_match = re.search(r"@js:", text, flags=re.IGNORECASE)
    if js_match:
        text, js_code = text[: js_match.start()], text[js_match.end() :]
        js_code = js_code.strip()
        if js_code:
            transforms.append({"type": "js", "code": js_code})

    regex_transforms: List[Dict[str, Any]] = []
    if "##" in text and not text.startswith("##"):
        text, pattern = text.split("##", 1)
        pattern = pattern.strip()
        if pattern:
            regex_transforms.append({"type": "regex_replace", "pattern": pattern, "repl": ""})

    return text.rstrip("@").strip(), regex_transforms + transforms


def _append_transforms_to_legado_rule(rule_value: str, transforms: Any) -> str:
    if isinstance(transforms, dict):
        transforms = [transforms]
    if not isinstance(transforms, list) or not transforms:
        return rule_value

    regex_suffixes: List[str] = []
    js_suffixes: List[str] = []
    for transform in transforms:
        if not isinstance(transform, dict):
            continue
        transform_type = str(transform.get("type") or transform.get("name") or "").strip().lower()
        if transform_type in {"regex_replace", "replace_regex"}:
            pattern = str(transform.get("pattern") or transform.get("regex") or "")
            repl = str(transform.get("repl", transform.get("replacement", "")))
            if pattern and repl == "":
                regex_suffixes.append(f"##{pattern}")
        elif transform_type == "js":
            code = str(transform.get("code") or transform.get("script") or "").strip()
            if code:
                js_suffixes.append(f"<js>{code}</js>")
    return rule_value + "".join(regex_suffixes) + "".join(js_suffixes)
