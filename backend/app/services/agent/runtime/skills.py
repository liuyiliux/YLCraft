"""Skill routing for YLCraft agent runtime.

Skills are reusable work methods. Tools execute actions; skills tell the agent
when and how to combine tools for a domain workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillRoute:
    skill_id: str
    reason: str
    score: int = 1


class SkillRouter:
    """Route task/context/tool signals to reusable AgentSkill templates."""

    DOMAIN_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
        (
            "creative_project_advance",
            ("创作项目", "项目", "大纲", "章节", "正文", "脚本", "推进", "缺口"),
            ("project_id", "creative_project_id", "default_project_id", "creative_project_context"),
            ("inspect_creative_project", "run_creative_project_pipeline", "build_creative_project_context_pack"),
        ),
        (
            "gap_analysis",
            ("缺口", "还缺", "下一步", "检查", "完成情况"),
            ("creative_project_context",),
            ("inspect_creative_project", "list_creative_project_contents"),
        ),
        (
            "continuity_review",
            ("连贯", "连续性", "前后", "设定冲突", "一致性", "质检"),
            ("creative_project_context",),
            ("inspect_creative_project", "list_creative_project_contents"),
        ),
        (
            "novel_completion",
            ("小说", "正文", "章节", "补完", "续写", "重写", "润色"),
            (),
            ("run_creative_writer_room", "list_novel_bookshelf", "preview_novel_chapter"),
        ),
        (
            "prose_humanize",
            ("自然", "人味", "AI腔", "润色", "对白", "节奏"),
            (),
            ("run_creative_writer_room",),
        ),
        (
            "prose_review",
            ("审稿", "review", "检查正文", "问题", "改写建议"),
            (),
            ("run_creative_writer_room",),
        ),
        (
            "character_visual_card",
            ("角色", "人物", "立绘", "外貌", "视觉卡", "人设"),
            ("character_id",),
            ("inspect_character", "update_character_visual_profile", "preview_character_portrait_prompt"),
        ),
        (
            "portrait_prompt",
            ("立绘", "九宫格", "姿态", "头像", "角色图", "参考图"),
            ("character_id",),
            ("preview_character_portrait_prompt", "generate_image_asset"),
        ),
        (
            "storyboard_generation",
            ("分镜", "镜头", "漫画", "脚本转分镜", "画面"),
            (),
            ("generate_storyboard", "list_creative_project_contents", "update_creative_project_content"),
        ),
        (
            "reference_match",
            ("参考图", "匹配", "一致性", "素材匹配", "复用"),
            (),
            ("match_creative_project_reference_assets", "search_assets", "semantic_search_assets"),
        ),
        (
            "comic_image_prompt",
            ("漫画", "生图提示词", "图片提示词", "画面提示", "镜头图"),
            (),
            ("generate_image_asset", "preview_image_generation_request"),
        ),
        (
            "asset_search",
            ("素材", "搜索素材", "找图", "找视频", "资产", "素材库"),
            (),
            ("search_assets", "semantic_search_assets", "search_platform_sources"),
        ),
        (
            "asset_tagging",
            ("打标", "标签", "分类", "入库", "整理素材"),
            (),
            ("add_asset_tag", "import_platform_results_to_assets"),
        ),
        (
            "platform_source_search",
            ("平台", "B站", "小红书", "抖音", "快手", "微博", "知乎", "公众号", "外部搜索", "搜视频"),
            (),
            ("search_platform_sources", "search_platform_sources_enhanced", "get_platform_note_detail"),
        ),
        (
            "download_workflow",
            ("下载", "解析链接", "磁力", "网盘", "链接", "去水印"),
            (),
            ("parse_download_link", "create_download_task", "fetch_platform_no_watermark"),
        ),
        (
            "image_generation_workflow",
            ("生图", "生成图片", "AI图片", "参考图", "立绘", "漫画图"),
            (),
            ("preview_image_generation_request", "generate_image_asset", "poll_image_generation_task"),
        ),
        (
            "video_generation_workflow",
            ("视频生成", "生成视频", "AI视频", "图生视频", "文生视频"),
            (),
            ("list_video_backends", "generate_video_asset", "poll_video_generation_task"),
        ),
        (
            "subtitle_workflow",
            ("字幕", "提取字幕", "烧录字幕", "字幕样式"),
            (),
            ("extract_subtitle", "get_subtitle_styles", "burn_subtitle"),
        ),
        (
            "bgm_workflow",
            ("BGM", "背景音乐", "配乐", "混音", "音乐"),
            (),
            ("list_bgm_tracks", "add_bgm_to_video", "upload_bgm"),
        ),
        (
            "clip_workflow",
            ("剪辑", "混剪", "成片", "切片", "解说视频"),
            (),
            ("start_cutclaw_clip", "start_narrato_clip", "start_moe_clip", "get_clip_task_status"),
        ),
        (
            "tts_workflow",
            ("TTS", "配音", "语音", "文字转语音", "音色"),
            (),
            ("preview_tts_request", "generate_tts_audio"),
        ),
        (
            "ebook_workflow",
            ("电子书", "epub", "mobi", "小说导出", "书籍"),
            (),
            ("create_ebook_from_folder", "get_ebook_task"),
        ),
        (
            "export_quality_workflow",
            ("导出", "质检", "去重", "重复素材", "数据集", "发布包"),
            (),
            ("export_asset_dataset", "find_duplicate_assets", "merge_duplicate_assets"),
        ),
    )

    TOOL_SKILL_HINTS: dict[str, tuple[str, ...]] = {
        "search_platform_sources": ("asset_search",),
        "search_platform_sources_enhanced": ("asset_search", "platform_source_search"),
        "parse_download_link": ("asset_search", "download_workflow"),
        "create_download_task": ("asset_search", "download_workflow"),
        "generate_image_asset": ("comic_image_prompt", "reference_match", "image_generation_workflow"),
        "generate_video_asset": ("video_generation_workflow",),
        "run_creative_writer_room": ("novel_completion", "prose_humanize", "prose_review"),
        "build_creative_project_context_pack": ("creative_project_advance", "gap_analysis"),
        "extract_subtitle": ("subtitle_workflow",),
        "burn_subtitle": ("subtitle_workflow",),
        "add_bgm_to_video": ("bgm_workflow",),
        "start_cutclaw_clip": ("clip_workflow",),
        "start_narrato_clip": ("clip_workflow",),
        "start_moe_clip": ("clip_workflow",),
        "generate_tts_audio": ("tts_workflow",),
        "create_ebook_from_folder": ("ebook_workflow",),
        "export_asset_dataset": ("export_quality_workflow",),
    }

    def route(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        default_skill_ids: list[str] | None = None,
        max_skills: int = 8,
    ) -> list[SkillRoute]:
        text = (message or "").lower()
        context = context or {}
        allowed = set(allowed_tools or [])
        route_map: dict[str, SkillRoute] = {}

        def add(skill_id: str, reason: str, score: int = 1) -> None:
            current = route_map.get(skill_id)
            if not current or score > current.score:
                route_map[skill_id] = SkillRoute(skill_id=skill_id, reason=reason, score=score)

        for skill_id in default_skill_ids or []:
            add(str(skill_id), "profile/default", 10)

        for skill_id, keywords, context_keys, tool_names in self.DOMAIN_RULES:
            keyword_hits = [item for item in keywords if item.lower() in text]
            context_hits = [key for key in context_keys if context.get(key)]
            tool_hits = [tool for tool in tool_names if "*" in allowed or tool in allowed]
            if keyword_hits:
                add(skill_id, f"message:{','.join(keyword_hits[:3])}", 6 + len(keyword_hits))
            elif context_hits and tool_hits:
                add(skill_id, f"context:{','.join(context_hits[:3])}", 4 + len(context_hits))
            elif tool_hits and any(item in text for item in ("做", "生成", "搜索", "检查", "推进", "整理")):
                add(skill_id, f"tool:{','.join(tool_hits[:3])}", 2)

        for tool in allowed:
            for skill_id in self.TOOL_SKILL_HINTS.get(tool, ()):
                add(skill_id, f"allowed_tool:{tool}", 1)

        return sorted(route_map.values(), key=lambda item: (-item.score, item.skill_id))[:max_skills]
