from __future__ import annotations

import json
import re
from typing import Any


CHARACTER_ENRICHMENT_SCHEMA: dict[str, Any] = {
    "appearance": "稳定外貌描述，包含脸型、发型、眼睛、体型、气质",
    "personality": "性格特点，避免空泛形容",
    "costume_hint": "默认服装和可复用穿搭提示",
    "age_range": "年龄范围",
    "background": "背景故事摘要",
    "visual_consistency": "生图一致性规则，强调不能漂移的点",
    "signature_items": ["标志物/道具/符号"],
    "expressions": ["常用表情"],
    "poses": ["常用姿态/动作"],
    "tags": ["检索标签"],
    "identity": {
        "alias": "别名/代号",
        "gender": "性别/性别表达",
        "species": "种族/类型",
        "organization": "组织/阵营",
        "position": "职位/社会身份",
        "logline": "一句话人设",
    },
    "motivation": {
        "desire": "核心欲望",
        "fear": "深层恐惧",
        "short_goal": "短期目标",
        "long_goal": "长期目标",
        "obsession": "执念",
        "values": "价值观",
    },
    "speech": {
        "tone": "说话语气",
        "catchphrase": "口头禅",
        "style": "句式/语速/措辞习惯",
        "taboo": "不会说的话",
    },
    "behavior": {
        "habit": "行为习惯",
        "stress_response": "压力反应",
        "boundary": "底线",
        "never_do": "绝不会做的事",
    },
    "ability": {
        "skills": "技能/特长",
        "weakness": "弱点",
        "limits": "能力限制",
        "cost": "代价",
    },
    "arc": {
        "start_state": "开局状态",
        "turning_point": "关键转折",
        "ending": "结局方向",
        "risk": "剧情雷点/禁区",
    },
}


TOP_LEVEL_TEXT_FIELDS = {
    "appearance",
    "personality",
    "costume_hint",
    "age_range",
    "background",
    "visual_consistency",
}
TOP_LEVEL_LIST_FIELDS = {"signature_items", "expressions", "poses", "tags"}
TOP_LEVEL_DICT_FIELDS = {"identity", "motivation", "speech", "behavior", "ability", "arc"}
ALL_FIELDS = TOP_LEVEL_TEXT_FIELDS | TOP_LEVEL_LIST_FIELDS | TOP_LEVEL_DICT_FIELDS


def build_character_enrichment_prompt(
    character_data: dict[str, Any],
    *,
    context: str = "",
    mode: str = "fill_missing",
) -> str:
    existing_json = json.dumps(character_data, ensure_ascii=False, indent=2)
    schema_json = json.dumps(CHARACTER_ENRICHMENT_SCHEMA, ensure_ascii=False, indent=2)
    policy = (
        "只补充空字段或明显缺失的子字段，不重写已有设定。"
        if mode != "rewrite"
        else "允许重写并统一所有字段，但必须保留角色原本的核心身份。"
    )
    return f"""你是影视/动画/漫画/游戏角色设定师。请基于已有角色资料补全 Character Bible 和视觉生产信息。

工作策略：{policy}

输出要求：
1. 只输出一个 JSON 对象，不要 Markdown，不要解释。
2. 字段必须使用下面 schema 中的 key，不要新增无关 key。
3. 所有内容使用中文，具体、可执行，适合后续小说写作、分镜、漫画和 AI 生图。
4. OOC 边界要写清楚这个角色绝不会做什么；Off-Model 相关内容写入 visual_consistency。
5. expressions 和 poses 建议给 6-9 个，便于后续生成表情九宫格/动作九宫格。

schema:
{schema_json}

已有角色资料:
{existing_json}

额外上下文:
{context or "无"}
"""


def parse_character_enrichment_response(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise ValueError("AI 返回为空")
    text = _strip_code_fence(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("AI 返回不是 JSON 对象")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("AI 返回不是 JSON 对象")
    return normalize_character_enrichment(data)


def normalize_character_enrichment(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in TOP_LEVEL_TEXT_FIELDS:
        value = data.get(field)
        if value is not None:
            result[field] = str(value).strip()
    for field in TOP_LEVEL_LIST_FIELDS:
        result[field] = _dedupe_strings(data.get(field))
    for field in TOP_LEVEL_DICT_FIELDS:
        value = data.get(field)
        result[field] = _clean_dict(value if isinstance(value, dict) else {})
    return {key: value for key, value in result.items() if _has_value(value)}


def merge_character_enrichment(
    current: dict[str, Any],
    proposal: dict[str, Any],
    *,
    mode: str = "fill_missing",
) -> tuple[dict[str, Any], list[str]]:
    normalized = normalize_character_enrichment(proposal)
    merged = dict(current)
    applied: list[str] = []
    rewrite = mode == "rewrite"

    for field in TOP_LEVEL_TEXT_FIELDS:
        candidate = str(normalized.get(field) or "").strip()
        if not candidate:
            continue
        if rewrite or not str(merged.get(field) or "").strip():
            merged[field] = candidate
            applied.append(field)

    for field in TOP_LEVEL_LIST_FIELDS:
        candidate = _dedupe_strings(normalized.get(field))
        if not candidate:
            continue
        current_values = _dedupe_strings(merged.get(field))
        if rewrite or not current_values:
            merged[field] = candidate
            applied.append(field)

    for field in TOP_LEVEL_DICT_FIELDS:
        candidate = normalized.get(field)
        if not isinstance(candidate, dict) or not candidate:
            continue
        current_dict = merged.get(field) if isinstance(merged.get(field), dict) else {}
        next_dict, changed = _merge_dict_missing(current_dict, candidate, rewrite=rewrite)
        if changed:
            merged[field] = next_dict
            applied.append(field)

    return merged, applied


def character_response_for_enrichment(character: Any) -> dict[str, Any]:
    return {
        "name": getattr(character, "name", "") or "",
        "role": getattr(character, "role", "") or "",
        "source_types": _json_list(getattr(character, "source_types", [])),
        "appearance": getattr(character, "appearance", "") or "",
        "personality": getattr(character, "personality", "") or "",
        "costume_hint": getattr(character, "costume_hint", "") or "",
        "signature_items": _json_list(getattr(character, "signature_items", [])),
        "expressions": _json_list(getattr(character, "expressions", [])),
        "poses": _json_list(getattr(character, "poses", [])),
        "visual_consistency": getattr(character, "visual_consistency", "") or "",
        "background": getattr(character, "background", "") or "",
        "age_range": getattr(character, "age_range", "") or "",
        "identity": _json_obj(getattr(character, "identity_json", {})),
        "motivation": _json_obj(getattr(character, "motivation_json", {})),
        "speech": _json_obj(getattr(character, "speech_json", {})),
        "behavior": _json_obj(getattr(character, "behavior_json", {})),
        "ability": _json_obj(getattr(character, "ability_json", {})),
        "arc": _json_obj(getattr(character, "arc_json", {})),
        "tags": _json_list(getattr(character, "tags", [])),
    }


def _merge_dict_missing(current: dict[str, Any], candidate: dict[str, Any], *, rewrite: bool) -> tuple[dict[str, Any], bool]:
    result = dict(current or {})
    changed = False
    for key, value in candidate.items():
        if not _has_value(value):
            continue
        if rewrite or not _has_value(result.get(key)):
            result[key] = value
            changed = True
    return result, changed


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _clean_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if _has_value(item)}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _dedupe_strings(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    result: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else list(values):
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _dedupe_strings(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            parsed = [value] if value.strip() else []
        return _dedupe_strings(parsed)
    return _dedupe_strings(value)


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
