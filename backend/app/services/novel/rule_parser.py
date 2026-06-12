"""Parser for YLCraft book source rules."""

from __future__ import annotations

import re
import time
import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

try:
    from py_mini_racer import MiniRacer
    HAS_MINIRACER = True
except ImportError:
    MiniRacer = None
    HAS_MINIRACER = False

logger = logging.getLogger("ylcraft.novel.rule_parser")


class RuleParser:
    """Parse HTML with YLCraft CSS-selector rules."""

    def __init__(self, rule: Dict[str, Any]):
        self.rule = rule or {}

    def parse_search(self, html: str) -> Dict[str, Any]:
        start = time.perf_counter()
        search_rule = self.rule.get("search") or {}
        items_rule = search_rule.get("items") or {}
        items, matched = self._parse_items(html, items_rule)
        return {
            "type": "search",
            "parse_success": bool(items),
            "items": items,
            "total_items": len(items),
            "debug": {
                "rule_used": items_rule,
                "matched_elements": matched,
                "parse_time_ms": _elapsed_ms(start),
            },
        }

    def parse_toc(self, html: str) -> Dict[str, Any]:
        start = time.perf_counter()
        toc_rule = self.rule.get("toc") or {}
        items_rule = toc_rule.get("items") or {}
        items, matched = self._parse_items(html, items_rule)
        return {
            "type": "toc",
            "parse_success": bool(items),
            "items": items,
            "total_items": len(items),
            "debug": {
                "rule_used": items_rule,
                "matched_elements": matched,
                "parse_time_ms": _elapsed_ms(start),
            },
        }

    def parse_content(self, html: str) -> Dict[str, Any]:
        start = time.perf_counter()
        content_rule = self.rule.get("content") or {}
        selector = content_rule.get("selector") or ""
        soup = BeautifulSoup(html or "", "html.parser")
        element = soup.select_one(selector) if selector else None
        matched = 1 if element else 0

        if not element:
            return {
                "type": "content",
                "parse_success": False,
                "content": "",
                "debug": {
                    "rule_used": content_rule,
                    "matched_elements": matched,
                    "parse_time_ms": _elapsed_ms(start),
                },
            }

        for remove_selector in content_rule.get("remove") or []:
            for node in element.select(remove_selector):
                node.decompose()
        for node in element.find_all(["script", "style"]):
            node.decompose()

        if content_rule.get("text_only", True):
            join_with = content_rule.get("join_with") or "\n\n"
            lines = [line.strip() for line in element.get_text("\n").splitlines()]
            content = join_with.join(line for line in lines if line)
        else:
            content = str(element)

        content = self._apply_transforms(content, content_rule.get("transforms") or [])

        return {
            "type": "content",
            "parse_success": bool(content),
            "content": content,
            "debug": {
                "rule_used": content_rule,
                "matched_elements": matched,
                "parse_time_ms": _elapsed_ms(start),
            },
        }

    def parse(self, html: str, rule_type: str) -> Dict[str, Any]:
        if rule_type == "search":
            return self.parse_search(html)
        if rule_type == "toc":
            return self.parse_toc(html)
        if rule_type == "content":
            return self.parse_content(html)
        raise ValueError(f"unsupported rule_type: {rule_type}")

    def _parse_items(self, html: str, items_rule: Dict[str, Any]) -> tuple[List[Dict[str, Any]], int]:
        selector = items_rule.get("selector") or ""
        soup = BeautifulSoup(html or "", "html.parser")
        elements = soup.select(selector) if selector else []
        limit = items_rule.get("limit")
        if isinstance(limit, int) and limit > 0:
            elements = elements[:limit]

        fields = items_rule.get("fields") or {}
        items: List[Dict[str, Any]] = []
        for element in elements:
            item: Dict[str, Any] = {}
            for field_name, field_config in fields.items():
                item[field_name] = self.extract_field(element, field_config)
            if any(value for value in item.values()):
                items.append(item)
        return items, len(elements)

    def extract_field(self, root: Tag, field_config: Dict[str, Any]) -> str:
        # 支持 Legado 的 && 多选择器语法：
        #   "a.-1&&span.-1" -> 先选 a 倒数第 1 个，找不到再选 span 倒数第 1 个
        selector = field_config.get("selector") or ""
        result = self._extract_with_fallback(root, selector, field_config)
        if not result:
            return ""

        # 应用修饰符（prefix / suffix / max_length）
        if field_config.get("trim", True):
            result = result.strip()

        prefix = field_config.get("prefix") or ""
        suffix = field_config.get("suffix") or ""
        if (
            prefix.startswith(("http://", "https://"))
            and result
            and not result.startswith(("http://", "https://"))
        ):
            result = urljoin(prefix.rstrip("/") + "/", result.lstrip("/"))
        elif prefix:
            result = prefix + result
        if suffix:
            result = result + suffix

        result = self._apply_transforms(result, field_config.get("transforms") or [])

        max_length = field_config.get("max_length")
        if isinstance(max_length, int) and max_length >= 0:
            result = result[:max_length]
        return result

    def _apply_transforms(self, value: str, transforms: Any) -> str:
        if not transforms:
            return value
        if isinstance(transforms, dict):
            transforms = [transforms]
        if not isinstance(transforms, list):
            return value

        result = "" if value is None else str(value)
        for transform in transforms:
            result = self._apply_transform(result, transform)
        return result

    def _apply_transform(self, value: str, transform: Any) -> str:
        if isinstance(transform, str):
            config: Dict[str, Any] = {"type": transform}
        elif isinstance(transform, dict):
            config = transform
        else:
            return value

        transform_type = str(config.get("type") or config.get("name") or "").strip().lower()
        if not transform_type:
            return value

        try:
            if transform_type == "trim":
                return value.strip()
            if transform_type in {"replace", "text_replace"}:
                old = str(config.get("old", config.get("from", "")))
                new = str(config.get("new", config.get("to", "")))
                return value.replace(old, new) if old else value
            if transform_type in {"regex_replace", "replace_regex"}:
                pattern = str(config.get("pattern") or config.get("regex") or "")
                repl = str(config.get("repl", config.get("replacement", "")))
                return re.sub(pattern, repl, value, flags=_regex_flags(config)) if pattern else value
            if transform_type in {"regex_extract", "extract_regex"}:
                pattern = str(config.get("pattern") or config.get("regex") or "")
                if not pattern:
                    return value
                match = re.search(pattern, value, flags=_regex_flags(config))
                if not match:
                    return ""
                group = config.get("group", 1 if match.groups() else 0)
                try:
                    return str(match.group(group))
                except Exception:
                    return str(match.group(0))
            if transform_type == "prefix":
                prefix = str(config.get("value", config.get("prefix", "")))
                return _apply_prefix(value, prefix)
            if transform_type == "suffix":
                suffix = str(config.get("value", config.get("suffix", "")))
                return value + suffix if suffix else value
            if transform_type in {"urljoin", "absolute_url"}:
                base = str(config.get("base") or config.get("value") or self.rule.get("base_url") or "")
                return urljoin(base.rstrip("/") + "/", value) if base and value else value
            if transform_type in {"max_length", "truncate"}:
                length = config.get("value", config.get("length"))
                if isinstance(length, int) and length >= 0:
                    return value[:length]
                return value
            if transform_type == "slice":
                start = _optional_int(config.get("start"))
                end = _optional_int(config.get("end"))
                return value[start:end]
            if transform_type == "js":
                code = str(config.get("code") or config.get("script") or "")
                return _eval_js_transform(code, value) if code else value
        except Exception as exc:
            logger.warning("YLCraft transform failed: type=%s error=%s", transform_type, exc)
            return value
        return value

    def _extract_with_fallback(
        self,
        root: Tag,
        selector: str,
        field_config: Dict[str, Any],
    ) -> str:
        """按 && 拆分候选选择器，依次尝试直到命中。

        支持 Legado 兼容语法：
        - && 分隔的备选选择器
        - .N 索引语法（选择第 N 个）
        - .-N 索引语法（选择倒数第 N 个）
        """
        if not selector:
            element: Optional[Tag] = root
        else:
            element = None
            for candidate in self._split_fallback_selector(selector):
                element = self._select_with_legado_index(root, candidate)
                if element is not None:
                    break
            if element is None and selector:
                # 所有候选都失败，兜底使用最后一个
                element = None

        if element is None:
            return ""

        field_type = field_config.get("type", "text")
        if field_type == "attr":
            attr_name = field_config.get("attr") or ""
            result = element.get(attr_name, "") if attr_name else ""
        elif field_type == "html":
            result = str(element)
        else:
            result = element.get_text(strip=field_config.get("trim", True))

        if result is None:
            return ""
        return str(result)

    @staticmethod
    def _split_fallback_selector(selector: str) -> List[str]:
        """按 && 拆分成多个候选选择器，去掉空字符串。"""
        return [part.strip() for part in selector.split("&&") if part.strip()]

    @staticmethod
    def _select_one_safely(root: Optional[Tag], selector: str) -> Optional[Tag]:
        """安全地执行 select_one，解析失败返回 None 而不抛异常。"""
        if root is None or not selector:
            return None
        try:
            return root.select_one(selector)
        except Exception:
            return None

    @staticmethod
    def _select_with_legado_index(
        root: Optional[Tag],
        selector: str,
    ) -> Optional[Tag]:
        """支持 Legado 的 .N / .-N 索引语法。

        - "a"             -> 等同 CSS a（取首个）
        - "a.0"           -> 第 1 个 a
        - "a.-1"          -> 倒数第 1 个 a
        - "a.0.2"         -> 第 1 个和第 3 个 a（去重，取第一个）
        - ".author a.0"   -> .author 下第 1 个 a
        """
        if root is None or not selector:
            return None

        # 先尝试标准 CSS 解析
        element = RuleParser._select_one_safely(root, selector)
        if element is not None:
            return element

        # 解析 Legado 索引语法：拆出 selector 末尾的 .N / .-N
        # 支持 "a.0"、"a.-1"、"a.0.2"、".author a.0" 等
        match = re.match(r"^(.*?)\.(-?\d+(?:\.\d+)*)$", selector)
        if not match:
            return None

        base_selector = match.group(1)
        indices_str = match.group(2)
        try:
            raw_indices = [int(x) for x in indices_str.split(".")]
        except ValueError:
            return None
        if not base_selector:
            return None

        try:
            candidates = root.select(base_selector)
        except Exception:
            return None

        if not candidates:
            return None

        n = len(candidates)
        for idx in raw_indices:
            if idx < 0:
                idx = n + idx
            if 0 <= idx < n:
                return candidates[idx]
        return None


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _regex_flags(config: Dict[str, Any]) -> int:
    flags = 0
    raw_flags = str(config.get("flags") or "")
    if config.get("ignore_case") or "i" in raw_flags:
        flags |= re.IGNORECASE
    if config.get("multi_line") or "m" in raw_flags:
        flags |= re.MULTILINE
    if config.get("dot_all") or "s" in raw_flags:
        flags |= re.DOTALL
    return flags


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _apply_prefix(value: str, prefix: str) -> str:
    if not prefix:
        return value
    if prefix.startswith(("http://", "https://")) and value and not value.startswith(("http://", "https://")):
        return urljoin(prefix.rstrip("/") + "/", value.lstrip("/"))
    return prefix + value


def _eval_js_transform(code: str, result: str) -> str:
    if not HAS_MINIRACER or MiniRacer is None:
        logger.warning("py_mini_racer is not installed; keeping value before js transform")
        return result
    try:
        ctx = MiniRacer()
        ctx.eval(f"var result = {json.dumps(result)};")
        try:
            value = ctx.eval(code)
            if value is not None and value != "":
                return str(value)
        except Exception:
            pass

        value = ctx.eval("(function() {\n" + code + "\n})();")
        if value is None or value == "":
            value = ctx.eval("result")
        if value is None or value == "":
            return result
        return str(value)
    except Exception as exc:
        logger.warning("YLCraft js transform failed: %s", exc)
        return result
