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
    
    # 让 Factory 使用 config 对象创建
    return PlatformClientFactory.create(platform, config)


async def search(
    platform: str,
    keyword: str,
    mode: str = "api",
    cookie: str = "",
    max_results: int = 20,
    search_type: str = "note",
    sort_by: str = "",
    page: int = 1,
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
        search_type: "note", "user", "article", "series", "bangumi", "movie", "live"
        sort_by: 排序方式（各平台自定义，如 B站：totalrank/click/pubdate/dm/stow）
        **kwargs: 平台特定参数，可包含 filters 字典
    
    Returns:
        搜索结果列表
    """
    # 展开 filters 字典到 kwargs（前端传来的筛选条件）
    filters = kwargs.pop('filters', None)
    if filters and isinstance(filters, dict):
        for key, value in filters.items():
            if value:  # 只添加非空值
                kwargs[key] = value
    
    # 分离配置参数和搜索参数
    # ClientConfig 只接受这些配置参数
    config_keys = {'timeout', 'proxy', 'headless', 'user_agent', 'debug'}
    config_kwargs = {k: v for k, v in kwargs.items() if k in config_keys}
    search_kwargs = {k: v for k, v in kwargs.items() if k not in config_keys}
    
    client = create_client(platform, mode, cookie, **config_kwargs)
    if not client:
        return []
    
    from .types import SearchParams, SearchType
    
    # 使用 from_string 支持自定义 search_type（如 bangumi/movie/live）
    params = SearchParams.from_string(
        keyword=keyword,
        max_results=max_results,
        search_type_str=search_type,
        sort_by=sort_by,
        page=page,
        extra=search_kwargs,
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
# 带连接ID的便捷函数（自动获取cookie）
# =============================================================================

async def search_with_conn_id(
    platform: str,
    keyword: str,
    conn_id: Optional[str] = None,
    **kwargs
) -> list[SearchResult]:
    """
    带连接ID的搜索（自动从DB获取cookie）
    
    Args:
        platform: 平台标识
        keyword: 搜索关键词
        conn_id: 连接ID（可选，不传则使用无cookie模式）
        **kwargs: 其他参数（同search函数）
    
    Returns:
        搜索结果列表
    """
    cookie = None
    
    if conn_id:
        try:
            from app.services.platform_connection.service import PlatformConnectionService
            from app.db.session import get_session
            
            async with get_session() as session:
                service = PlatformConnectionService(session)
                conn = service.get(conn_id)
                if conn:
                    cookie = service.get_raw_cookie(conn_id)
                    if cookie:
                        logger.debug(f"[platforms] Got cookie for conn_id: {conn_id[:8]}...")
        except Exception as e:
            logger.warning(f"[platforms] Failed to get cookie for conn_id {conn_id}: {e}")
    
    # 调用普通search函数，传入获取到的cookie
    return await search(platform, keyword, cookie=cookie or "", **kwargs)


async def get_detail_with_conn_id(
    platform: str,
    item_id: str,
    conn_id: Optional[str] = None,
    **kwargs
) -> Optional[NoteDetail]:
    """
    带连接ID的详情获取（自动从DB获取cookie）
    
    Args:
        platform: 平台标识
        item_id: 笔记/视频 ID
        conn_id: 连接ID（可选，不传则使用无cookie模式）
        **kwargs: 其他参数（同get_detail函数）
    
    Returns:
        详情对象 或 None
    """
    cookie = None
    
    if conn_id:
        try:
            from app.services.platform_connection.service import PlatformConnectionService
            from app.db.session import get_session
            
            async with get_session() as session:
                service = PlatformConnectionService(session)
                conn = service.get(conn_id)
                if conn:
                    cookie = service.get_raw_cookie(conn_id)
                    if cookie:
                        logger.debug(f"[platforms] Got cookie for conn_id: {conn_id[:8]}...")
        except Exception as e:
            logger.warning(f"[platforms] Failed to get cookie for conn_id {conn_id}: {e}")
    
    # 调用普通get_detail函数，传入获取到的cookie
    return await get_detail(platform, item_id, cookie=cookie or "", **kwargs)


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
    
    # 带连接ID的便捷函数
    "search_with_conn_id",
    "get_detail_with_conn_id",
]
