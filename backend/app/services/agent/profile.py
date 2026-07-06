"""Agent profile management for configurable YLCraft agents."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.agent import AgentProfile


DEFAULT_AGENT_PROFILES: list[dict[str, Any]] = [
    {
        "id": "default-assistant",
        "name": "总控助手",
        "avatar": "AI",
        "role_type": "orchestrator",
        "description": "通用 YLCraft 助手，负责理解需求、选择工具、解释结果。",
        "system_prompt": (
            "你是 YLCraft 总控助手。先判断用户意图，再调用最少必要工具。"
            "不要编造项目、素材或任务结果；不确定时先检查工具返回。"
        ),
        "allowed_tools": ["*"],
        "default_workflow": "general_assistant",
        "default_skill_ids": [],
        "max_steps": 8,
        "is_default": True,
    },
    {
        "id": "ai-config-specialist",
        "name": "AI 模型配置专家",
        "avatar": "API",
        "role_type": "orchestrator",
        "description": "负责供应商规范、模型连接器、图片编辑/生图模型配置和连通性测试。",
        "system_prompt": (
            "你是 YLCraft 的 AI 模型配置专家。优先检查现有供应商和连接器，再根据用户提供的 API 文档或 curl 示例生成配置。"
            "配置图片编辑模型时要区分 text-to-image 和 image-to-image/edit："
            "公网图片链接使用 JSON images=[{image_url}]；本地图片上传使用 multipart image 字段；"
            "OpenAI-compatible 图片编辑端点通常是 /v1/images/edits，response_format 可用 b64_json。"
            "写入前先说明将创建或更新哪些字段；写入后调用测试工具验证，并把请求 URL、模式、模型名和解析配置摘要反馈给用户。"
        ),
        "allowed_tools": [
            "list_ai_connectors",
            "get_ai_connector",
            "list_provider_metadata",
            "get_provider_metadata",
            "upsert_provider_metadata",
            "create_ai_connector",
            "update_ai_connector",
            "test_ai_connector",
            "discover_connector_models",
            "list_image_backends",
            "preview_image_generation_request",
            "list_prompt_templates",
            "get_prompt_template",
        ],
        "default_context": {
            "focus": "ai_model_configuration",
        },
        "default_workflow": "ai_model_configuration",
        "default_skill_ids": [],
        "provider": "",
        "model": "",
        "max_steps": 10,
        "is_default": False,
    },
    {
        "id": "creative-director",
        "name": "创作导演",
        "avatar": "CD",
        "role_type": "orchestrator",
        "description": "面向小说、短剧、漫画分镜的项目型智能体。",
        "system_prompt": (
            "你是 YLCraft 创作导演。优先使用创作项目工具读取项目、大纲、项目圣经、"
            "章节、分镜和生成日志。所有改写和生成都要保留版本，不要直接覆盖用户已确认内容。"
        ),
        "allowed_tools": [
            "list_creative_projects",
            "inspect_creative_project",
            "sync_creative_project_bible",
            "run_creative_project_pipeline",
            "run_creative_writer_room",
            "list_creative_project_contents",
            "get_creative_project_content",
            "update_creative_project_content",
            "list_creative_project_asset_links",
            "link_creative_project_asset",
            "match_creative_project_reference_assets",
            "list_creative_project_generation_logs",
            "get_creative_project_generation_log",
            "list_characters",
            "inspect_character",
            "preview_character_portrait_prompt",
            "list_image_backends",
            "preview_image_generation_request",
            "list_video_backends",
            "preview_video_generation_request",
            "list_prompt_templates",
            "get_prompt_template",
            "preview_prompt_template_render",
            "update_prompt_template",
            "list_ai_connectors",
            "get_ai_connector",
            "list_project_tasks",
            "get_project_task",
            "cancel_project_task",
            "delete_project_task",
            "list_novel_sources",
            "list_novel_bookshelf",
            "search_novel_sources",
            "get_novel_catalog",
            "preview_novel_chapter",
            "parse_download_link",
            "create_download_task",
            "poll_download_task",
            "list_wechat_mp_connections",
            "search_wechat_mp_accounts",
            "list_wechat_mp_articles",
            "download_wechat_mp_article",
            "preview_tts_request",
            "generate_tts_audio",
            "create_ebook_from_folder",
            "get_ebook_task",
            "list_ebook_tasks",
            "semantic_search_assets",
            "find_similar_assets",
            "get_asset_embedding_info",
            "get_asset_lineage_graph",
            "get_asset_upstream_lineage",
            "get_asset_downstream_lineage",
            "get_asset_lineage_stats",
            "link_asset_lineage",
            "find_asset_common_ancestor",
            "browse_reader_documents",
            "read_reader_document",
            "read_reader_document_collection",
            "delete_reader_document",
            "get_export_dataset_stats",
            "export_asset_dataset",
            "calculate_asset_quality",
            "batch_calculate_asset_quality",
            "find_duplicate_assets",
            "merge_duplicate_assets",
            "list_platform_source_options",
            "list_platform_connections",
            "search_platform_sources",
            "search_platform_sources_enhanced",
            "get_platform_note_detail",
            "fetch_platform_no_watermark",
            "import_platform_results_to_assets",
        ],
        "default_workflow": "creative_project_advance",
        "default_skill_ids": ["creative_project_advance", "reference_match"],
        "max_steps": 10,
        "is_default": False,
    },
    {
        "id": "novel-writer",
        "name": "小说作者",
        "avatar": "NW",
        "role_type": "writer",
        "description": "负责章节正文、续写、人味改写和节奏润色。",
        "system_prompt": (
            "你是 YLCraft 小说作者。优先读取项目上下文、章节细纲、角色卡和已有正文，"
            "再推进正文创作。输出要自然、有段落呼吸感，保留人物动机和前后因果。"
        ),
        "allowed_tools": [
            "build_creative_project_context_pack",
            "list_creative_project_contents",
            "get_creative_project_content",
            "update_creative_project_content",
            "list_creative_project_generation_logs",
            "get_creative_project_generation_log",
            "run_creative_writer_room",
            "list_prompt_templates",
            "get_prompt_template",
            "preview_prompt_template_render",
            "list_ai_connectors",
            "get_ai_connector",
            "list_project_tasks",
            "get_project_task",
            "list_novel_sources",
            "list_novel_bookshelf",
            "search_novel_sources",
            "get_novel_catalog",
            "preview_novel_chapter",
            "parse_download_link",
            "list_wechat_mp_connections",
            "search_wechat_mp_accounts",
            "list_wechat_mp_articles",
            "preview_tts_request",
            "generate_tts_audio",
            "create_ebook_from_folder",
            "get_ebook_task",
            "list_ebook_tasks",
            "semantic_search_assets",
            "find_similar_assets",
            "get_asset_lineage_graph",
            "get_asset_upstream_lineage",
            "browse_reader_documents",
            "read_reader_document",
            "read_reader_document_collection",
            "get_export_dataset_stats",
            "list_platform_source_options",
            "list_platform_connections",
            "search_platform_sources",
            "search_platform_sources_enhanced",
            "get_platform_note_detail",
        ],
        "default_workflow": "novel_writer_room",
        "default_skill_ids": ["novel_completion", "prose_humanize", "prose_review"],
        "max_steps": 10,
        "is_default": False,
    },
    {
        "id": "character-designer",
        "name": "角色设定师",
        "avatar": "CH",
        "role_type": "character_designer",
        "description": "负责角色圣经、视觉卡、立绘提示词和参考图一致性。",
        "system_prompt": (
            "你是 YLCraft 角色设定师。先读取项目圣经、角色卡和素材库参考图，"
            "再补全角色外貌、服装、识别点、负面约束和可复用生图提示词。"
        ),
        "allowed_tools": [
            "build_creative_project_context_pack",
            "list_creative_project_contents",
            "get_creative_project_content",
            "search_assets",
            "get_asset_detail",
            "semantic_search_assets",
            "find_similar_assets",
            "get_asset_embedding_info",
            "get_asset_lineage_graph",
            "get_asset_upstream_lineage",
            "get_asset_downstream_lineage",
            "link_asset_lineage",
            "browse_reader_documents",
            "read_reader_document",
            "read_reader_document_collection",
            "list_platform_source_options",
            "list_platform_connections",
            "search_platform_sources",
            "search_platform_sources_enhanced",
            "get_platform_note_detail",
            "fetch_platform_no_watermark",
            "import_platform_results_to_assets",
            "list_creative_project_asset_links",
            "link_creative_project_asset",
            "add_asset_tag",
            "list_characters",
            "inspect_character",
            "preview_character_portrait_prompt",
            "update_character_visual_profile",
            "list_image_backends",
            "preview_image_generation_request",
            "generate_image_asset",
            "poll_image_generation_task",
            "list_video_backends",
            "preview_video_generation_request",
            "list_prompt_templates",
            "get_prompt_template",
            "preview_prompt_template_render",
            "list_ai_connectors",
            "get_ai_connector",
            "list_project_tasks",
            "get_project_task",
            "list_novel_bookshelf",
            "parse_download_link",
            "create_download_task",
            "poll_download_task",
            "list_wechat_mp_connections",
            "search_wechat_mp_accounts",
            "list_wechat_mp_articles",
            "download_wechat_mp_article",
        ],
        "default_workflow": "character_visual_card",
        "default_skill_ids": ["character_visual_card", "portrait_prompt"],
        "max_steps": 10,
        "is_default": False,
    },
    {
        "id": "storyboard-director",
        "name": "分镜导演",
        "avatar": "SB",
        "role_type": "storyboard_director",
        "description": "负责脚本拆镜、漫画分镜、镜头提示词和参考素材匹配。",
        "system_prompt": (
            "你是 YLCraft 分镜导演。先读取章节正文、脚本、角色卡和参考图，"
            "再生成可拍、可画、可生图的镜头描述，明确场景、情绪、构图、角色和参考素材。"
        ),
        "allowed_tools": [
            "build_creative_project_context_pack",
            "list_creative_project_contents",
            "get_creative_project_content",
            "update_creative_project_content",
            "list_creative_project_asset_links",
            "link_creative_project_asset",
            "match_creative_project_reference_assets",
            "run_creative_project_pipeline",
            "list_creative_project_generation_logs",
            "get_creative_project_generation_log",
            "search_assets",
            "get_asset_detail",
            "semantic_search_assets",
            "find_similar_assets",
            "get_asset_embedding_info",
            "get_asset_lineage_graph",
            "get_asset_upstream_lineage",
            "get_asset_downstream_lineage",
            "get_asset_lineage_stats",
            "link_asset_lineage",
            "browse_reader_documents",
            "read_reader_document",
            "read_reader_document_collection",
            "list_platform_source_options",
            "list_platform_connections",
            "search_platform_sources",
            "search_platform_sources_enhanced",
            "get_platform_note_detail",
            "fetch_platform_no_watermark",
            "import_platform_results_to_assets",
            "list_image_backends",
            "preview_image_generation_request",
            "generate_image_asset",
            "poll_image_generation_task",
            "list_video_backends",
            "preview_video_generation_request",
            "generate_video_asset",
            "poll_video_generation_task",
            "preview_tts_request",
            "generate_tts_audio",
            "list_prompt_templates",
            "get_prompt_template",
            "preview_prompt_template_render",
            "list_ai_connectors",
            "get_ai_connector",
            "list_project_tasks",
            "get_project_task",
            "list_novel_bookshelf",
        ],
        "default_workflow": "storyboard_reference_match",
        "default_skill_ids": ["storyboard_generation", "reference_match", "comic_image_prompt"],
        "max_steps": 12,
        "is_default": False,
    },
    {
        "id": "asset-curator",
        "name": "素材管家",
        "avatar": "AS",
        "role_type": "asset_curator",
        "description": "面向素材检索、资产查看和标签整理。",
        "system_prompt": (
            "你是 YLCraft 素材管家。优先检索和整理素材库，返回明确素材 ID、类型、"
            "路径和下一步建议。删除或批量修改前必须说明影响。"
        ),
        "allowed_tools": [
            "search_assets",
            "get_asset_detail",
            "semantic_search_assets",
            "find_similar_assets",
            "get_asset_embedding_info",
            "get_asset_lineage_graph",
            "get_asset_upstream_lineage",
            "get_asset_downstream_lineage",
            "get_asset_lineage_stats",
            "link_asset_lineage",
            "browse_reader_documents",
            "read_reader_document",
            "read_reader_document_collection",
            "delete_reader_document",
            "get_export_dataset_stats",
            "export_asset_dataset",
            "calculate_asset_quality",
            "batch_calculate_asset_quality",
            "find_duplicate_assets",
            "merge_duplicate_assets",
            "list_platform_source_options",
            "list_platform_connections",
            "search_platform_sources",
            "search_platform_sources_enhanced",
            "get_platform_note_detail",
            "fetch_platform_no_watermark",
            "import_platform_results_to_assets",
            "add_asset_tag",
            "list_creative_project_asset_links",
            "link_creative_project_asset",
            "list_image_backends",
            "poll_image_generation_task",
            "list_video_backends",
            "poll_video_generation_task",
            "get_ebook_task",
            "list_ebook_tasks",
            "list_ai_connectors",
            "get_ai_connector",
            "list_project_tasks",
            "get_project_task",
            "list_novel_bookshelf",
        ],
        "default_workflow": "asset_curation",
        "default_skill_ids": ["asset_search", "asset_tagging"],
        "max_steps": 8,
        "is_default": False,
    },
    {
        "id": "quality-reviewer",
        "name": "质检编辑",
        "avatar": "QA",
        "role_type": "reviewer",
        "description": "负责连续性、设定一致性、缺口检查和下一步建议。",
        "system_prompt": (
            "你是 YLCraft 质检编辑。不要急着生成新内容，先检查项目上下文、日志和已有产物，"
            "指出矛盾、缺口、质量风险，并给出可执行的修复顺序。"
        ),
        "allowed_tools": [
            "build_creative_project_context_pack",
            "inspect_creative_project",
            "list_creative_project_contents",
            "get_creative_project_content",
            "list_creative_project_asset_links",
            "get_asset_lineage_graph",
            "get_asset_upstream_lineage",
            "get_asset_downstream_lineage",
            "get_asset_lineage_stats",
            "find_asset_common_ancestor",
            "get_export_dataset_stats",
            "calculate_asset_quality",
            "batch_calculate_asset_quality",
            "find_duplicate_assets",
            "list_platform_source_options",
            "list_platform_connections",
            "list_creative_project_generation_logs",
            "get_creative_project_generation_log",
            "list_prompt_templates",
            "get_prompt_template",
            "preview_prompt_template_render",
            "list_ai_connectors",
            "get_ai_connector",
            "list_project_tasks",
            "get_project_task",
            "list_novel_sources",
            "list_novel_bookshelf",
        ],
        "default_workflow": "quality_review",
        "default_skill_ids": ["continuity_review", "gap_analysis"],
        "max_steps": 8,
        "is_default": False,
    },
    {
        "id": "role-actor",
        "name": "角色演员",
        "avatar": "RA",
        "role_type": "role_actor",
        "description": "扮演指定角色，从角色动机、情感、关系和口吻出发生成对话、内心独白和场景反应。",
        "system_prompt": (
            "你是 YLCraft 角色演员。你的任务不是概括角色，而是以指定角色的身份思考和说话。"
            "先读取角色卡（目标、恐惧、知识、情感、人际关系、口吻），再进入角色。"
            "输出角色对话、内心独白或场景反应时，严格遵循角色设定，不跳出角色视角。"
            "如果给定的角色卡信息不足，先指出缺失项，不要编造角色细节。"
        ),
        "allowed_tools": [
            "build_creative_project_context_pack",
            "list_characters",
            "inspect_character",
            "inspect_creative_project",
            "list_creative_project_contents",
            "get_creative_project_content",
            "list_creative_project_generation_logs",
            "get_creative_project_generation_log",
            "list_prompt_templates",
            "get_prompt_template",
            "preview_prompt_template_render",
            "list_ai_connectors",
            "get_ai_connector",
            "list_novel_bookshelf",
        ],
        "default_workflow": "role_actor_performance",
        "default_skill_ids": ["character_voice", "dialogue_generation", "inner_monologue"],
        "max_steps": 8,
        "is_default": False,
    },
    {
        "id": "divine-director",
        "name": "天意总导演",
        "avatar": "DD",
        "role_type": "director",
        "description": "从上帝视角控制叙事走向：主题、冲突、节奏、外部事件和世界规则约束。",
        "system_prompt": (
            "你是 YLCraft 天意总导演（Divine Director）。你从上帝视角审视整个创作项目，"
            "负责调度冲突、控制节奏、触发外部事件、维护世界规则一致性。"
            "你不写正文，而是产出行程指令：在哪里引入冲突、在哪里放慢节奏、"
            "在哪里触发世界事件、哪条故事线需要推进。"
            "所有指令都必须引用项目圣经和已有设定的具体条目，不能凭空编造事件。"
        ),
        "allowed_tools": [
            "build_creative_project_context_pack",
            "inspect_creative_project",
            "sync_creative_project_bible",
            "list_creative_project_contents",
            "get_creative_project_content",
            "update_creative_project_content",
            "list_creative_project_generation_logs",
            "get_creative_project_generation_log",
            "list_characters",
            "inspect_character",
            "list_prompt_templates",
            "get_prompt_template",
            "preview_prompt_template_render",
            "list_ai_connectors",
            "get_ai_connector",
            "list_novel_bookshelf",
            "list_novel_sources",
            "semantic_search_assets",
            "get_asset_lineage_graph",
            "get_asset_lineage_stats",
        ],
        "default_workflow": "divine_director_briefing",
        "default_skill_ids": ["conflict_design", "pacing_control", "world_rule_enforcement"],
        "max_steps": 10,
        "is_default": False,
    },
    {
        "id": "story-editor",
        "name": "编辑润色师",
        "avatar": "SE",
        "role_type": "editor",
        "description": "多维度文本编辑：逻辑检查、角色一致性、节奏感、钩子强度、可画面化评估。",
        "system_prompt": (
            "你是 YLCraft 编辑润色师。逐维度检查文本：\n"
            "1. 逻辑链——前后因果是否自洽，时间线是否对齐，是否有设定矛盾。\n"
            "2. 角色一致性——角色言行是否与角色卡一致，动机是否连贯。\n"
            "3. 节奏——段落呼吸感、信息密度、高潮分布是否合理。\n"
            "4. 钩子——章节开头和结尾是否有足够吸引力。\n"
            "5. 可画面化——文字描述是否足够具体可转分镜和生图。\n"
            "输出格式：按维度分组的问题列表 + 逐条修改建议 + 全局评价（A/B/C）。"
            "只建议修改方向，不直接覆盖原文；改写留给创作导演或小说作者。"
        ),
        "allowed_tools": [
            "build_creative_project_context_pack",
            "inspect_creative_project",
            "list_creative_project_contents",
            "get_creative_project_content",
            "update_creative_project_content",
            "list_creative_project_generation_logs",
            "get_creative_project_generation_log",
            "list_characters",
            "inspect_character",
            "list_prompt_templates",
            "get_prompt_template",
            "preview_prompt_template_render",
            "list_ai_connectors",
            "get_ai_connector",
            "list_novel_sources",
            "list_novel_bookshelf",
            "get_asset_lineage_graph",
            "get_asset_lineage_stats",
        ],
        "default_workflow": "story_editor_review",
        "default_skill_ids": ["logic_check", "pacing_review", "imageability_assessment"],
        "max_steps": 10,
        "is_default": False,
    },
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def profile_to_dict(profile: AgentProfile) -> dict[str, Any]:
    def load(value: str, fallback: Any) -> Any:
        try:
            return json.loads(value or "")
        except Exception:
            return fallback

    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "name": profile.name,
        "description": profile.description,
        "avatar": profile.avatar,
        "role_type": profile.role_type,
        "system_prompt": profile.system_prompt,
        "allowed_tools": load(profile.allowed_tools_json, []),
        "default_context": load(profile.default_context_json, {}),
        "default_project_id": profile.default_project_id,
        "default_workflow": profile.default_workflow,
        "default_skill_ids": load(profile.default_skill_ids_json, []),
        "provider": profile.provider,
        "model": profile.model,
        "max_steps": profile.max_steps,
        "is_default": profile.is_default,
        "is_builtin": profile.is_builtin,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


class AgentProfileManager:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id

    async def ensure_defaults(self) -> None:
        for item in DEFAULT_AGENT_PROFILES:
            existing = await self.session.get(AgentProfile, item["id"])
            if existing:
                if existing.is_builtin:
                    existing.name = item["name"]
                    existing.description = item["description"]
                    existing.avatar = item["avatar"]
                    existing.role_type = item.get("role_type", "assistant")
                    existing.system_prompt = item["system_prompt"]
                    existing.allowed_tools_json = _json(item["allowed_tools"])
                    existing.default_context_json = _json(item.get("default_context") or {})
                    existing.default_workflow = item.get("default_workflow", "")
                    existing.default_skill_ids_json = _json(item.get("default_skill_ids") or [])
                    if item.get("provider") and not existing.provider:
                        existing.provider = item.get("provider", "")
                    if item.get("model") and not existing.model:
                        existing.model = item.get("model", "")
                    existing.max_steps = item["max_steps"]
                    existing.updated_at = datetime.utcnow()
                    self.session.add(existing)
                continue
            profile = AgentProfile(
                id=item["id"],
                user_id=self.user_id,
                name=item["name"],
                description=item["description"],
                avatar=item["avatar"],
                role_type=item.get("role_type", "assistant"),
                system_prompt=item["system_prompt"],
                allowed_tools_json=_json(item["allowed_tools"]),
                default_context_json=_json(item.get("default_context") or {}),
                default_project_id=item.get("default_project_id", ""),
                default_workflow=item.get("default_workflow", ""),
                default_skill_ids_json=_json(item.get("default_skill_ids") or []),
                provider=item.get("provider", ""),
                model=item.get("model", ""),
                max_steps=item["max_steps"],
                is_default=item["is_default"],
                is_builtin=True,
            )
            self.session.add(profile)
        await self.session.flush()

    async def list_profiles(self) -> list[AgentProfile]:
        await self.ensure_defaults()
        result = await self.session.exec(
            select(AgentProfile)
            .where(AgentProfile.user_id == self.user_id)
            .order_by(AgentProfile.is_default.desc(), AgentProfile.created_at.asc())
        )
        return list(result.all())

    async def get_profile(self, profile_id: str | None) -> AgentProfile:
        await self.ensure_defaults()
        if profile_id:
            profile = await self.session.get(AgentProfile, profile_id)
            if profile:
                return profile
        result = await self.session.exec(
            select(AgentProfile)
            .where(AgentProfile.user_id == self.user_id, AgentProfile.is_default == True)
            .limit(1)
        )
        profile = result.first()
        if profile:
            return profile
        profiles = await self.list_profiles()
        return profiles[0]

    async def create_profile(self, data: dict[str, Any]) -> AgentProfile:
        profile = AgentProfile(
            id=data.get("id") or uuid.uuid4().hex,
            user_id=self.user_id,
            name=data.get("name") or "未命名智能体",
            description=data.get("description") or "",
            avatar=data.get("avatar") or "AI",
            role_type=data.get("role_type") or "assistant",
            system_prompt=data.get("system_prompt") or "",
            allowed_tools_json=_json(data.get("allowed_tools") or []),
            default_context_json=_json(data.get("default_context") or {}),
            default_project_id=data.get("default_project_id") or "",
            default_workflow=data.get("default_workflow") or "",
            default_skill_ids_json=_json(data.get("default_skill_ids") or []),
            provider=data.get("provider") or "",
            model=data.get("model") or "",
            max_steps=int(data.get("max_steps") or 8),
            is_default=bool(data.get("is_default", False)),
            is_builtin=False,
        )
        if profile.is_default:
            await self._clear_default()
        self.session.add(profile)
        await self.session.flush()
        await self.session.refresh(profile)
        return profile

    async def update_profile(self, profile_id: str, data: dict[str, Any]) -> AgentProfile | None:
        profile = await self.session.get(AgentProfile, profile_id)
        if not profile or profile.user_id != self.user_id:
            return None
        scalar_fields = [
            "name",
            "description",
            "avatar",
            "role_type",
            "system_prompt",
            "default_project_id",
            "default_workflow",
            "provider",
            "model",
            "max_steps",
        ]
        for field in scalar_fields:
            if field in data and data[field] is not None:
                setattr(profile, field, data[field])
        if "allowed_tools" in data and data["allowed_tools"] is not None:
            profile.allowed_tools_json = _json(data["allowed_tools"])
        if "default_context" in data and data["default_context"] is not None:
            profile.default_context_json = _json(data["default_context"])
        if "default_skill_ids" in data and data["default_skill_ids"] is not None:
            profile.default_skill_ids_json = _json(data["default_skill_ids"])
        if "is_default" in data and data["is_default"] is not None:
            if data["is_default"]:
                await self._clear_default()
            profile.is_default = bool(data["is_default"])
        profile.updated_at = datetime.utcnow()
        self.session.add(profile)
        await self.session.flush()
        await self.session.refresh(profile)
        return profile

    async def _clear_default(self) -> None:
        result = await self.session.exec(
            select(AgentProfile).where(AgentProfile.user_id == self.user_id, AgentProfile.is_default == True)
        )
        for profile in result.all():
            profile.is_default = False
            self.session.add(profile)
