"""Declarative content-production profiles.

Profiles describe recommended orchestration only. Independent workspaces
remain usable without a project.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CONTENT_PRODUCTION_PROFILES: dict[str, dict[str, Any]] = {
    "vertical_drama": {
        "id": "vertical_drama", "label": "竖屏短剧",
        "description": "从创意快速走到分集脚本、分镜和视频，不要求先写正文。",
        "project_type": "short_drama",
        "recommended_stages": ["outline", "chapter_plan", "chapter_outline", "script", "storyboard", "video"],
        "optional_stages": ["novel_body", "voiceover", "subtitles"],
        "default_outputs": ["script", "storyboard", "video"],
        "constraints": {"aspect_ratio": "9:16", "chapter_count": 12},
        "production_family": "narrative",
        "package_type": None,
        "required_inputs": ["topic"],
        "optional_inputs": ["reference_assets", "style", "audience"],
        "planning_unit": "stage",
        "output_adapters": ["asset_bundle"],
    },
    "storybook": {
        "id": "storybook", "label": "故事漫画 / 童话绘本",
        "description": "恐怖漫画、童话绘本和短篇故事共用的页式视觉叙事方案。",
        "project_type": "manga",
        "recommended_stages": ["outline", "chapter_plan", "chapter_outline", "script", "storyboard", "comic_pages"],
        "optional_stages": ["novel_body", "video", "voiceover"],
        "default_outputs": ["comic_pages", "image_set"],
        "constraints": {"aspect_ratio": "4:3", "page_count": 12},
        "production_family": "content_package",
        "package_type": "page_book",
        "required_inputs": ["topic"],
        "optional_inputs": ["reference_assets", "style", "audience", "page_count", "prompt_only"],
        "planning_unit": "item",
        "output_adapters": ["pdf_ebook", "asset_bundle"],
    },
    "knowledge_content": {
        "id": "knowledge_content", "label": "科普内容",
        "description": "先整理主题和事实，再输出图文卡片或短视频素材。",
        "project_type": "mixed",
        "recommended_stages": ["outline", "script", "storyboard", "image", "layout"],
        "optional_stages": ["video", "voiceover", "subtitles"],
        "default_outputs": ["image_set", "script"], "constraints": {"aspect_ratio": "4:3"},
        "production_family": "content_package",
        "package_type": "knowledge_cards",
        "required_inputs": ["topic"],
        "optional_inputs": ["reference_assets", "source_links", "style", "audience", "card_count", "prompt_only"],
        "planning_unit": "item",
        "output_adapters": ["wechat_official_account", "xiaohongshu_carousel", "asset_bundle"],
    },
    "platform_note": {
        "id": "platform_note", "label": "平台图文",
        "description": "内容完成后交给多平台生图和图片编辑器适配小红书、微信等渠道。",
        "project_type": "mixed",
        "recommended_stages": ["outline", "script", "image", "layout", "platform_adapter"],
        "optional_stages": ["video", "subtitles"],
        "default_outputs": ["platform_note", "image_set"],
        "constraints": {"platforms": ["xiaohongshu", "wechat", "douyin"]},
        "production_family": "content_package",
        "package_type": "article_package",
        "required_inputs": ["topic"],
        "optional_inputs": ["source_assets", "source_links", "style", "audience", "target_platform"],
        "planning_unit": "package",
        "output_adapters": ["wechat_official_account", "xiaohongshu_carousel", "asset_bundle"],
    },
    "novel_serial": {
        "id": "novel_serial", "label": "小说连载",
        "description": "完整叙事路线，适合需要正文、连续性检查和平台发布的项目。",
        "project_type": "novel",
        "recommended_stages": ["outline", "chapter_plan", "chapter_outline", "novel_body", "review"],
        "optional_stages": ["script", "storyboard", "comic_pages"],
        "default_outputs": ["novel_body"], "constraints": {"chapter_count": 12},
        "production_family": "narrative",
        "package_type": None,
        "required_inputs": ["topic"],
        "optional_inputs": ["source_assets", "audience", "style"],
        "planning_unit": "stage",
        "output_adapters": ["asset_bundle"],
    },
    "single_shot": {
        "id": "single_shot", "label": "单镜头 / 单页实验",
        "description": "用一句创意或一张素材快速试做一个镜头、画面或绘本页。",
        "project_type": "mixed", "recommended_stages": ["story_seed", "image", "video"],
        "optional_stages": ["script", "storyboard"], "default_outputs": ["image", "video"], "constraints": {},
        "production_family": "content_package",
        "package_type": "single_media",
        "required_inputs": ["topic"],
        "optional_inputs": ["reference_assets", "style", "aspect_ratio", "media_type"],
        "planning_unit": "item",
        "output_adapters": ["asset_bundle"],
    },
}

DEFAULT_PROFILE_BY_PROJECT_TYPE = {
    "short_drama": "vertical_drama", "manga": "storybook", "novel": "novel_serial", "mixed": "vertical_drama",
}


def get_content_production_profile(profile_id: str | None, project_type: str = "short_drama") -> dict[str, Any]:
    normalized = str(profile_id or "").strip().lower() or DEFAULT_PROFILE_BY_PROJECT_TYPE.get(project_type, "vertical_drama")
    profile = CONTENT_PRODUCTION_PROFILES.get(normalized)
    if profile is None:
        raise ValueError(f"不支持的内容生产方案：{profile_id}")
    return deepcopy(profile)


def is_content_package_profile(profile_id: str | None, project_type: str = "short_drama") -> bool:
    """Return whether a profile should use the lightweight content-package UI."""

    return get_content_production_profile(profile_id, project_type).get("production_family") == "content_package"


def validate_profile_inputs(
    profile_id: str | None,
    *,
    project_type: str = "short_drama",
    topic: str | None = None,
    source_assets: list[Any] | None = None,
    source_links: list[Any] | None = None,
) -> dict[str, Any]:
    """Validate the minimum user-facing inputs before an LLM request.

    A topic is normally required, but source assets or links can satisfy the
    requirement for source-first package workflows. The returned profile is a
    copy safe for callers to include in a response.
    """

    profile = get_content_production_profile(profile_id, project_type)
    normalized_topic = str(topic or "").strip()
    assets = [item for item in (source_assets or []) if item]
    links = [item for item in (source_links or []) if str(item).strip()]
    if "topic" in profile.get("required_inputs", []) and not normalized_topic and not assets and not links:
        raise ValueError("请输入主题，或至少提供一个参考素材/来源链接")
    return {
        "profile": profile,
        "topic": normalized_topic,
        "source_assets": assets,
        "source_links": links,
    }


def normalize_project_settings(settings: dict[str, Any] | None, *, profile_id: str | None, project_type: str) -> dict[str, Any]:
    result = dict(settings or {})
    profile = get_content_production_profile(profile_id, project_type)
    result["production_profile"] = profile["id"]
    result["production_family"] = profile["production_family"]
    result["package_type"] = profile.get("package_type")
    result.setdefault("production_profile_version", 1)
    return result
