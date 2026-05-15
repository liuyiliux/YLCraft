"""
YLCraft — 平台爬虫工厂
统一入口，支持动态加载平台客户端
"""
from __future__ import annotations

import logging
from typing import Optional, Type, Dict, Any

from .base import BasePlatformClient, PlatformClientFactory, ClientConfig, ClientMode
from .types import SearchResult, NoteDetail, UserProfile, SeriesInfo, SearchParams

logger = logging.getLogger("ylcraft.platforms")


# =============================================================================
# 自动导入并注册所有平台
# =============================================================================

def _auto_discover_platforms():
    """自动发现并导入平台模块"""
    import importlib
    
    platform_modules = [
        "xiaohongshu",
        "bilibili",
        "douyin",
        "kuaishou",
        "weibo",
        "zhihu",
    ]
    
    for module_name in platform_modules:
        try:
            importlib.import_module(f"app.services.platforms.{module_name}")
            logger.info(f"Auto-discovered platform: {module_name}")
        except ImportError as e:
            logger.debug(f"Platform {module_name} not available: {e}")
        except Exception as e:
            logger.warning(f"Error loading platform {module_name}: {e}")


# 调用自动发现
_auto_discover_platforms()


# =============================================================================
# 便捷函数
# =============================================================================

def create_client(
    platform: str,
    mode: str = "api",
    cookie: str = "",
    **kwargs
) -> Optional[BasePlatformClient]:
    """
    创建平台客户端（便捷函数）
    
    Args:
        platform: 平台标识 (xhs, bili, dy, ks, wb, zhihu)
        mode: "api" 或 "patchright"
        cookie: Cookie 字符串
        **kwargs: 其他配置（timeout, proxy, etc.）
    
    Returns:
        BasePlatformClient 实例 或 None
    """
    # 将字符串转换为 ClientMode 枚举
    if isinstance(mode, str):
        mode_lower = mode.lower()
        if mode_lower == "api":
            mode_enum = ClientMode.API
        elif mode_lower in ("patchright", "playwright"):
            mode_enum = ClientMode.PATCHRIGHT
        else:
            logger.error(f"Invalid mode: {mode}. Use 'api' or 'patchright'")
            return None
    else:
        mode_enum = mode  # 已经是枚举类型
    
    config = ClientConfig(
        platform=platform,
        mode=mode_enum,
        cookie=cookie,
        **kwargs
    )
    
    return PlatformClientFactory.create(platform, config)


async def search(
    platform: str,
    keyword: str,
    mode: str = "api",
    cookie: str = "",
    max_results: int = 20,
    search_type: str = "note",
    **kwargs
) -> list[SearchResult]:
    """
    搜索（便捷函数）
    
    Args:
        platform: 平台标识
        keyword: 搜索关键词
        mode: "api" 或 "patchright"
        cookie: Cookie 字符串
        max_results: 最大结果数
        search_type: "note", "user", "article", "series"
        **kwargs: 平台特定参数
    
    Returns:
        搜索结果列表
    """
    client = create_client(platform, mode, cookie, **kwargs)
    if not client:
        return []
    
    from .types import SearchParams, SearchType
    
    try:
        search_type_enum = SearchType(search_type)
    except ValueError:
        search_type_enum = SearchType.NOTE
    
    params = SearchParams(
        keyword=keyword,
        max_results=max_results,
        search_type=search_type_enum,
        extra=kwargs,
    )
    
    async with client:
        return await client.search(params)


async def get_detail(
    platform: str,
    item_id: str,
    mode: str = "api",
    cookie: str = "",
    **kwargs
) -> Optional[NoteDetail]:
    """
    获取详情（便捷函数）
    
    Args:
        platform: 平台标识
        item_id: 笔记/视频 ID
        mode: "api" 或 "patchright"
        cookie: Cookie 字符串
        **kwargs: 其他参数
    
    Returns:
        详情对象 或 None
    """
    client = create_client(platform, mode, cookie, **kwargs)
    if not client:
        return None
    
    async with client:
        return await client.get_detail(item_id, **kwargs)


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 基类
    "BasePlatformClient",
    "PlatformClientFactory",
    "ClientConfig",
    "ClientMode",
    
    # 数据类型
    "SearchResult",
    "NoteDetail",
    "UserProfile",
    "SeriesInfo",
    "SearchParams",
    
    # 便捷函数
    "create_client",
    "search",
    "get_detail",
]
