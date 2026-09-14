"""Declarative content-production profiles.

Profiles describe recommended orchestration only. Independent workspaces
remain usable without a project.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

#: 内容包族的计划阶段词表（design §1「内容包族」的执行顺序）。
#:
#: 内容包与叙事族共用同一套 `ProjectContent`、计划结构与确认规则，**区别只在编排单位**：
#: 内容包以「条目」（页 / 卡 / 镜头 / 文章包）为单位，叙事族以「章节与正文」为单位。
#: 因此内容包族的阶段名与叙事阶段名是两套词表，不能互相套用——把 `storybook` 的推荐
#: 阶段写成 `outline/chapter_plan/chapter_outline` 会让导演为一个绘本包提议章节大纲。
#: 每个阶段都对应一个**已存在的**能力，不是构想：
#:   - `package_plan`   ← 一次内容包规划（`POST .../content-package/plan`）
#:   - `item_text`      ← 逐条文本（`update_content_package_item` / 条目重跑）
#:   - `item_prompt`    ← 逐条媒体提示词（同上，prompt_only 模式）
#:   - `media_batch`    ← 批量出图/出视频（消耗型，需一次确认）
#:   - `package_outputs`← 平台适配输出（`POST .../content-package/outputs`）
PACKAGE_PLAN_STAGES: tuple[str, ...] = (
    "package_plan",
    "item_text",
    "item_prompt",
    "media_batch",
    "package_outputs",
)

#: `storybook` 的推荐阶段。**刻意不是 `PACKAGE_PLAN_STAGES`**。
#:
#: spec（`content-production-orchestration` 的「User creates a storybook project」）要求
#: storybook 暴露「页规划 / 角色参考 / 分镜 / 生图 / 排版」。通用内容包阶段只有
#: 「规划→文本→提示词→出图」，中间**把故事变成分镜的那一步整个缺失**——于是
#: 页数只能由用户在入口处硬填（`page_count` 默认 12 就是这么变成"12 页"的），
#: 助手也无从判断一个故事该有多少页。
#:
#: 这里补的是**故事中介步骤**，全部沿用既有能力名（`sync_characters` / `script` /
#: `storyboard` / `match_references` / `comic_pages` 都是工作台 `pipelineStageOptions`
#: 里已有的值）。刻意**不引入** `outline` / `chapter_plan` / `chapter_outline`：
#: 那三个属叙事词表，混用会让导演为一个绘本包提议章节大纲（见 `PACKAGE_PLAN_STAGES`
#: 上方的词表说明）。
#:
#: `package_plan` 仍是入口——它负责**依据故事内容判断页数并切页**，而不是按固定数字凑页。
STORYBOOK_STAGES: tuple[str, ...] = (
    "package_plan",      # 页规划：依据内容定页数、切页
    "sync_characters",   # 角色参考：定妆，人物一致性的载体
    "script",            # 脚本
    "storyboard",        # 分镜：页数的真正依据
    "media_batch",       # 生图
)

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
        # 内容包族：编排单位是「页」，不是章节与正文（#17）
        # 见 STORYBOOK_STAGES 的说明：这里必须用它，不能用通用 PACKAGE_PLAN_STAGES。
        "recommended_stages": list(STORYBOOK_STAGES),
        "optional_stages": [
            "item_text", "item_prompt", "match_references", "comic_pages",
            "layout", "item_review",
        ],
        "default_outputs": ["comic_pages", "image_set"],
        # 刻意**不给** `page_count` 默认值：页数应由内容与分镜推导，而不是先在
        # 契约里钉一个 12。留着它会让"12 页"在没有任何人显式选择的情况下生效。
        # 上限由 page_book 的 schema 兜底（max_items=120）。
        "constraints": {"aspect_ratio": "4:3"},
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
        # 内容包族：编排单位是「知识卡」，事实与来源随条目一并保留（#17）
        "recommended_stages": list(PACKAGE_PLAN_STAGES),
        "optional_stages": ["item_review"],
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
        # 内容包族：planning_unit=package，整篇文章一次成篇，媒体提示词属可选（#17）
        "recommended_stages": ["package_plan", "item_text", "package_outputs"],
        "optional_stages": ["item_prompt", "media_batch", "item_review"],
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
        "project_type": "mixed",
        # 内容包族：单镜头就是「一个条目 + 一个媒体任务」（#17）
        "recommended_stages": ["package_plan", "item_prompt", "media_batch"],
        "optional_stages": ["item_text", "package_outputs", "item_review"],
        "default_outputs": ["image", "video"], "constraints": {},
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
