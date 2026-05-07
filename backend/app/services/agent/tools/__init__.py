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
    # 工具列表
    "TOOLS",
]
