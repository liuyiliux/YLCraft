"""角色来源与字段来源标记（provenance）。

YLCraft 有两条互补的角色生产链路，字段来源语义不同：

1. ``extract``（先有外来文本，再提取角色卡）
   - 外来小说上传：项目 ``source_type == "novel"`` 且 ``source_ref`` 指向本地上传文本素材
     → 角色字段直接来自文本，标 ``original``。
   - 小说书架/导入：项目 ``source_type == "novel"`` 且 ``source_ref`` 指向外部抓取/导入的小说素材
     → 同上标 ``original``，但 ``extract_origin`` 记为 ``novel_import``。
   - 项目原创大纲角色：项目 ``source_type == "original_idea"``
     → 大纲由 LLM 生成，字段没有原文依据，标 ``ai_inferred``。

2. ``character_first``（角色先行）
   - 用户在角色工作区手填或 AI 补全：手填标 ``user_edited``，AI 补全标 ``ai_inferred``。

字段来源值沿用 `Character.field_sources_json` 的既有约定：
``original`` / ``ai_inferred`` / ``user_edited``（``unset`` 表示未设置）。
"""

from __future__ import annotations

from typing import Any

FIELD_SOURCE_ORIGINAL = "original"
FIELD_SOURCE_AI_INFERRED = "ai_inferred"
FIELD_SOURCE_USER_EDITED = "user_edited"

EXTRACT_ORIGIN_UPLOADED_NOVEL = "uploaded_novel"
EXTRACT_ORIGIN_IMPORTED_NOVEL = "imported_novel"
EXTRACT_ORIGIN_ORIGINAL_OUTLINE = "original_outline"
EXTRACT_ORIGIN_UNKNOWN = "unknown"

EXTRACT_ORIGIN_LABELS = {
    EXTRACT_ORIGIN_UPLOADED_NOVEL: "上传小说提取",
    EXTRACT_ORIGIN_IMPORTED_NOVEL: "外来小说导入",
    EXTRACT_ORIGIN_ORIGINAL_OUTLINE: "原创大纲（AI 推断）",
    EXTRACT_ORIGIN_UNKNOWN: "未标记",
}

# 大纲角色字段 -> 角色库字段的映射，用于为空字段补来源标记
OUTLINE_FIELD_MAP: dict[str, str] = {
    "appearance": "appearance",
    "image_prompt": "appearance",
    "costume_hint": "costume_hint",
    "personality": "personality",
    "background": "background",
    "arc": "background",
    "age_range": "age_range",
    "visual_consistency": "visual_consistency",
    "identity": "identity",
    "faction": "identity",
    "organization": "identity",
}

TRACKED_CHARACTER_FIELDS = (
    "appearance",
    "costume_hint",
    "personality",
    "background",
    "age_range",
    "visual_consistency",
)


def loads_json_mapping(value: Any) -> dict[str, str]:
    """Best-effort parse of the persisted field_sources mapping."""
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items() if str(v)}
    if isinstance(value, str) and value.strip():
        import json

        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if str(v)}
    return {}


def dumps_json_mapping(value: dict[str, str]) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False)


def resolve_extract_origin(project: Any) -> str:
    """判断一个创作项目的角色提取来源类型。

    Args:
        project: ``CreativeProject`` 实例（或带有 source_type / source_ref_json 的对象）。

    Returns:
        ``EXTRACT_ORIGIN_*`` 之一。
    """
    source_type = str(getattr(project, "source_type", "") or "").strip().lower()
    source_ref = getattr(project, "source_ref_json", "") or ""
    if isinstance(source_ref, str) and source_ref.strip():
        import json

        try:
            parsed = json.loads(source_ref)
        except (TypeError, ValueError):
            parsed = {}
        if isinstance(parsed, dict):
            source_ref_payload = parsed
        else:
            source_ref_payload = {}
    elif isinstance(source_ref, dict):
        source_ref_payload = source_ref
    else:
        source_ref_payload = {}

    if source_type != "novel":
        return EXTRACT_ORIGIN_ORIGINAL_OUTLINE

    # 外来/导入小说：来自小说搜索或书架抓取，素材带外部来源标记
    origin_marker = " ".join(
        str(source_ref_payload.get(key) or "")
        for key in ("source", "source_type", "origin", "source_name", "site", "provider")
    ).lower()
    external_tokens = ("novel_bookshelf", "novel_download", "novel_search", "crawler", "bookshelf", "download", "external")
    if any(token in origin_marker for token in external_tokens):
        return EXTRACT_ORIGIN_IMPORTED_NOVEL
    return EXTRACT_ORIGIN_UPLOADED_NOVEL


def extract_origin_label(origin: str) -> str:
    return EXTRACT_ORIGIN_LABELS.get(str(origin or ""), EXTRACT_ORIGIN_LABELS[EXTRACT_ORIGIN_UNKNOWN])


def build_field_sources(origin: str) -> str:
    """按提取来源决定大纲角色字段的来源标记。

    外来文本提取 -> ``original``（有原文依据）；原创大纲 -> ``ai_inferred``。
    """
    source = FIELD_SOURCE_ORIGINAL if origin in {
        EXTRACT_ORIGIN_UPLOADED_NOVEL,
        EXTRACT_ORIGIN_IMPORTED_NOVEL,
    } else FIELD_SOURCE_AI_INFERRED
    return source


def merge_field_sources(
    existing: Any,
    outline_character: dict[str, Any],
    *,
    source: str,
) -> dict[str, str]:
    """把大纲角色的字段来源合并进角色已有的来源映射。

    只补空缺（不覆盖用户/后续明确设置的标记），保证手动修正的来源不被同步流程冲掉。
    """
    merged = loads_json_mapping(existing)
    for outline_key, character_field in OUTLINE_FIELD_MAP.items():
        raw_value = outline_character.get(outline_key)
        if isinstance(raw_value, (list, dict)):
            has_value = bool(raw_value)
        else:
            has_value = bool(str(raw_value or "").strip())
        if not has_value:
            continue
        if not merged.get(character_field):
            merged[character_field] = source
    return merged


def mark_user_edited(existing: Any, fields: list[str]) -> dict[str, str]:
    """用户在工作区保存字段后，把这些字段标记为 ``user_edited``。"""
    merged = loads_json_mapping(existing)
    for field in fields:
        if field:
            merged[field] = FIELD_SOURCE_USER_EDITED
    return merged
