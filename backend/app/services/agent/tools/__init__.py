"""
YLCraft — Agent 工具集合

统一导出所有 Agent 可调用的工具。

使用方法：
    from app.services.agent.tools import (
        search_assets,
        start_cutclaw_clip,
        extract_subtitle,
        ...
    )

或自动导入所有工具：
    from app.services.agent.tools import TOOLS
"""
from __future__ import annotations

# 基类
from .base import ToolResult

# 素材工具
from .asset_tools import (
    search_assets,
    get_asset_detail,
    download_asset,
    add_asset_tag,
    delete_asset,
    clean_asset_provenance,
)

# 剪辑工具
from .clip_tools import (
    start_cutclaw_clip,
    start_narrato_clip,
    start_moe_clip,
    get_clip_task_status,
)

# 字幕工具
from .subtitle_tools import (
    extract_subtitle,
    get_subtitle_styles,
    burn_subtitle,
)

# BGM 工具
from .bgm_tools import (
    list_bgm_tracks,
    add_bgm_to_video,
    upload_bgm,
)

# 爆款拆解工具
from .breaker_tools import (
    analyze_viral_content,
    get_breaker_task_status,
    generate_script,
)

from .image_tools import (
    list_image_backends,
    preview_image_generation_request,
    generate_image_asset,
    poll_image_generation_task,
)

from .image_prompt_reference_tools import (
    list_image_prompt_sources,
    search_image_prompt_references,
    get_image_prompt_reference,
    refresh_image_prompt_sources,
    save_image_prompt_reference_as_asset,
)

from .video_tools import (
    list_video_backends,
    preview_video_generation_request,
    generate_video_asset,
    poll_video_generation_task,
)

from .prompt_template_tools import (
    list_prompt_templates,
    get_prompt_template,
    preview_prompt_template_render,
    update_prompt_template,
)

from .ai_config_tools import (
    list_ai_connectors,
    get_ai_connector,
    list_provider_metadata,
    get_provider_metadata,
    upsert_provider_metadata,
    create_ai_connector,
    update_ai_connector,
    test_ai_connector,
    discover_connector_models,
)

from .skill_tools import (
    import_agent_skill_from_url,
    create_agent_skill_draft,
    list_agent_skill_drafts,
    list_agent_skill_packages,
    inspect_agent_run_skill_candidate,
    create_agent_skill_draft_from_run,
)

from .task_tools import (
    list_project_tasks,
    get_project_task,
    cancel_project_task,
    delete_project_task,
)

from .delegation_tools import delegate_agent_tasks
from .production_plan_tools import (
    analyze_creative_production_plan_impact,
    run_creative_production_plan,
    update_creative_production_plan,
)

from .novel_tools import (
    list_novel_sources,
    list_novel_bookshelf,
    search_novel_sources,
    get_novel_catalog,
    preview_novel_chapter,
)

from .download_tools import (
    parse_download_link,
    create_download_task,
    poll_download_task,
)

from .wechat_mp_tools import (
    list_wechat_mp_connections,
    search_wechat_mp_accounts,
    list_wechat_mp_articles,
    download_wechat_mp_article,
)

from .tts_tools import (
    preview_tts_request,
    generate_tts_audio,
)

from .ebook_tools import (
    create_ebook_from_folder,
    get_ebook_task,
    list_ebook_tasks,
)

from .semantic_search_tools import (
    semantic_search_assets,
    find_similar_assets,
    get_asset_embedding_info,
)

from .lineage_tools import (
    get_asset_lineage_graph,
    get_asset_upstream_lineage,
    get_asset_downstream_lineage,
    get_asset_lineage_stats,
    link_asset_lineage,
    find_asset_common_ancestor,
)

from .reader_tools import (
    browse_reader_documents,
    read_reader_document,
    read_reader_document_collection,
    delete_reader_document,
)

from .export_tools import (
    get_export_dataset_stats,
    export_asset_dataset,
    calculate_asset_quality,
    batch_calculate_asset_quality,
    find_duplicate_assets,
    merge_duplicate_assets,
)

from .platform_source_tools import (
    list_platform_source_options,
    list_platform_connections,
    search_platform_sources,
    search_platform_sources_enhanced,
    get_platform_note_detail,
    fetch_platform_no_watermark,
    import_platform_results_to_assets,
)

from .creative_project_tools import (
    list_creative_projects,
    inspect_creative_project,
    build_creative_project_context_pack_tool,
    list_creative_project_contents,
    get_creative_project_content,
    get_creative_production_plan,
    save_creative_production_plan,
    update_creative_project_content,
    list_creative_project_asset_links,
    link_creative_project_asset,
    match_creative_project_reference_assets,
    list_creative_project_generation_logs,
    get_creative_project_generation_log,
    sync_creative_project_bible,
    run_creative_project_pipeline,
    run_creative_writer_room,
)

from .fanqie_tools import (
    list_fanqie_my_books,
    get_fanqie_book_stats,
    get_fanqie_hot_list,
    preview_fanqie_project_publish,
    get_fanqie_project_publish_status,
    publish_fanqie_project_chapter,
)

from .canvas_tools import (
    list_creative_canvas_documents,
    get_creative_canvas_document,
    apply_creative_canvas_operations,
    get_project_canvas,
    save_project_canvas,
    add_project_canvas_node,
    connect_project_canvas_nodes,
    apply_project_canvas_operations,
)

from .character_tools import (
    list_characters,
    find_character_duplicate_candidates,
    inspect_character,
    preview_character_portrait_prompt,
    update_character_visual_profile,
)

# 工具列表（用于批量注册）
TOOLS = [
    # 素材工具
    search_assets,
    get_asset_detail,
    download_asset,
    add_asset_tag,
    delete_asset,
    # 剪辑工具
    start_cutclaw_clip,
    start_narrato_clip,
    start_moe_clip,
    get_clip_task_status,
    # 字幕工具
    extract_subtitle,
    get_subtitle_styles,
    burn_subtitle,
    # BGM 工具
    list_bgm_tracks,
    add_bgm_to_video,
    upload_bgm,
    # 爆款拆解工具
    analyze_viral_content,
    get_breaker_task_status,
    generate_script,
    # AI 图片工具
    list_image_backends,
    preview_image_generation_request,
    generate_image_asset,
    poll_image_generation_task,
    list_image_prompt_sources,
    search_image_prompt_references,
    get_image_prompt_reference,
    refresh_image_prompt_sources,
    save_image_prompt_reference_as_asset,
    # AI 视频工具
    list_video_backends,
    preview_video_generation_request,
    generate_video_asset,
    poll_video_generation_task,
    list_prompt_templates,
    get_prompt_template,
    preview_prompt_template_render,
    update_prompt_template,
    list_ai_connectors,
    get_ai_connector,
    list_provider_metadata,
    get_provider_metadata,
    upsert_provider_metadata,
    create_ai_connector,
    update_ai_connector,
    test_ai_connector,
    discover_connector_models,
    import_agent_skill_from_url,
    create_agent_skill_draft,
    list_agent_skill_drafts,
    list_agent_skill_packages,
    inspect_agent_run_skill_candidate,
    create_agent_skill_draft_from_run,
    list_project_tasks,
    get_project_task,
    cancel_project_task,
    delete_project_task,
    delegate_agent_tasks,
    list_novel_sources,
    list_novel_bookshelf,
    search_novel_sources,
    get_novel_catalog,
    preview_novel_chapter,
    parse_download_link,
    create_download_task,
    poll_download_task,
    list_wechat_mp_connections,
    search_wechat_mp_accounts,
    list_wechat_mp_articles,
    download_wechat_mp_article,
    preview_tts_request,
    generate_tts_audio,
    create_ebook_from_folder,
    get_ebook_task,
    list_ebook_tasks,
    semantic_search_assets,
    find_similar_assets,
    get_asset_embedding_info,
    get_asset_lineage_graph,
    get_asset_upstream_lineage,
    get_asset_downstream_lineage,
    get_asset_lineage_stats,
    link_asset_lineage,
    find_asset_common_ancestor,
    browse_reader_documents,
    read_reader_document,
    read_reader_document_collection,
    delete_reader_document,
    get_export_dataset_stats,
    export_asset_dataset,
    calculate_asset_quality,
    batch_calculate_asset_quality,
    find_duplicate_assets,
    merge_duplicate_assets,
    list_platform_source_options,
    list_platform_connections,
    search_platform_sources,
    search_platform_sources_enhanced,
    get_platform_note_detail,
    fetch_platform_no_watermark,
    import_platform_results_to_assets,
    list_creative_projects,
    inspect_creative_project,
    build_creative_project_context_pack_tool,
    list_creative_project_contents,
    get_creative_project_content,
    get_creative_production_plan,
    save_creative_production_plan,
    update_creative_project_content,
    list_creative_project_asset_links,
    link_creative_project_asset,
    match_creative_project_reference_assets,
    list_creative_project_generation_logs,
    get_creative_project_generation_log,
    sync_creative_project_bible,
    run_creative_project_pipeline,
    run_creative_writer_room,
    list_fanqie_my_books,
    get_fanqie_book_stats,
    get_fanqie_hot_list,
    preview_fanqie_project_publish,
    get_fanqie_project_publish_status,
    publish_fanqie_project_chapter,
    list_creative_canvas_documents,
    get_creative_canvas_document,
    apply_creative_canvas_operations,
    get_project_canvas,
    save_project_canvas,
    add_project_canvas_node,
    connect_project_canvas_nodes,
    apply_project_canvas_operations,
    # 角色工具
    list_characters,
    inspect_character,
    preview_character_portrait_prompt,
    update_character_visual_profile,
]

__all__ = [
    # 基类
    "ToolResult",
    # 素材工具
    "search_assets",
    "get_asset_detail",
    "download_asset",
    "add_asset_tag",
    "delete_asset",
    "clean_asset_provenance",
    # 剪辑工具
    "start_cutclaw_clip",
    "start_narrato_clip",
    "start_moe_clip",
    "get_clip_task_status",
    # 字幕工具
    "extract_subtitle",
    "get_subtitle_styles",
    "burn_subtitle",
    # BGM 工具
    "list_bgm_tracks",
    "add_bgm_to_video",
    "upload_bgm",
    # 爆款拆解工具
    "analyze_viral_content",
    "get_breaker_task_status",
    "generate_script",
    # AI 图片工具
    "list_image_backends",
    "preview_image_generation_request",
    "generate_image_asset",
    "poll_image_generation_task",
    "list_image_prompt_sources",
    "search_image_prompt_references",
    "get_image_prompt_reference",
    "refresh_image_prompt_sources",
    "save_image_prompt_reference_as_asset",
    # AI 视频工具
    "list_video_backends",
    "preview_video_generation_request",
    "generate_video_asset",
    "poll_video_generation_task",
    # 创作项目工具
    "list_prompt_templates",
    "get_prompt_template",
    "preview_prompt_template_render",
    "update_prompt_template",
    "list_ai_connectors",
    "get_ai_connector",
    "list_provider_metadata",
    "get_provider_metadata",
    "upsert_provider_metadata",
    "create_ai_connector",
    "update_ai_connector",
    "test_ai_connector",
    "discover_connector_models",
    "import_agent_skill_from_url",
    "create_agent_skill_draft",
    "list_agent_skill_drafts",
    "list_agent_skill_packages",
    "inspect_agent_run_skill_candidate",
    "create_agent_skill_draft_from_run",
    "list_project_tasks",
    "get_project_task",
    "cancel_project_task",
    "delete_project_task",
    "delegate_agent_tasks",
    "run_creative_production_plan",
    "analyze_creative_production_plan_impact",
    "update_creative_production_plan",
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
    "list_creative_projects",
    "inspect_creative_project",
    "build_creative_project_context_pack_tool",
    "list_creative_project_contents",
    "get_creative_project_content",
    "get_creative_production_plan",
    "save_creative_production_plan",
    "update_creative_project_content",
    "list_creative_project_asset_links",
    "link_creative_project_asset",
    "match_creative_project_reference_assets",
    "list_creative_project_generation_logs",
    "get_creative_project_generation_log",
    "sync_creative_project_bible",
    "run_creative_project_pipeline",
    "run_creative_writer_room",
    "list_fanqie_my_books",
    "get_fanqie_book_stats",
    "get_fanqie_hot_list",
    "preview_fanqie_project_publish",
    "get_fanqie_project_publish_status",
    "publish_fanqie_project_chapter",
    "list_creative_canvas_documents",
    "get_creative_canvas_document",
    "apply_creative_canvas_operations",
    "get_project_canvas",
    "save_project_canvas",
    "add_project_canvas_node",
    "connect_project_canvas_nodes",
    "apply_project_canvas_operations",
    # 角色工具
    "list_characters",
    "find_character_duplicate_candidates",
    "inspect_character",
    "preview_character_portrait_prompt",
    "update_character_visual_profile",
    # 工具列表
    "TOOLS",
]
