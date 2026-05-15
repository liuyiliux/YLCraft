"""
YLCraft — 平台爬虫统一入口
调用新的 platforms 模块，支持 API 和 Patchright 模式切换
已弃用：不再直接依赖 MediaCrawler
"""
from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.platforms import BasePlatformClient

logger = logging.getLogger("ylcraft.crawler_wrapper")


# =============================================================================
# 统一爬虫入口（推荐使用）
# =============================================================================

async def search_platform(
    platform: str,
    keyword: str,
    cookie: str = "",
    mode: str = "api",
    max_results: int = 20,
    search_type: str = "note",
    **kwargs
) -> List[Dict[str, Any]]:
    """
    统一搜索入口
    
    Args:
        platform: 平台标识 (xhs, bili, dy, ks, wb, zhihu)
        keyword: 搜索关键词
        cookie: Cookie 字符串
        mode: "api" 或 "patchright"
        max_results: 最大结果数
        search_type: "note", "user", "article", "series"
        **kwargs: 平台特定参数
    
    Returns:
        搜索结果列表（字典格式，兼容旧接口）
    """
    from app.services.platforms import SearchType, SearchParams
    from app.services.platforms import create_client
    
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
    
    client = create_client(platform=platform, mode=mode, cookie=cookie)
    if not client:
        logger.error(f"Failed to create client for platform: {platform}")
        return []
    
    async with client:
        results = await client.search(params)
        
        # 转换为字典格式（兼容旧接口）
        return [_result_to_dict(r) for r in results]


async def get_platform_detail(
    platform: str,
    item_id: str,
    cookie: str = "",
    mode: str = "api",
    **kwargs
) -> Dict[str, Any]:
    """
    统一详情获取入口
    
    Args:
        platform: 平台标识
        item_id: 笔记/视频 ID
        cookie: Cookie 字符串
        mode: "api" 或 "patchright"
        **kwargs: 其他参数
    
    Returns:
        详情字典（兼容旧接口）
    """
    from app.services.platforms import create_client
    
    client = create_client(platform=platform, mode=mode, cookie=cookie)
    if not client:
        logger.error(f"Failed to create client for platform: {platform}")
        return {}
    
    async with client:
        detail = await client.get_detail(item_id, **kwargs)
        
        # 转换为字典格式（兼容旧接口）
        return _detail_to_dict(detail)


# =============================================================================
# 兼容旧接口（MediaCrawlerWrapper 兼容层）
# =============================================================================

class MediaCrawlerWrapper:
    """
    兼容层：保持旧接口不变
    内部调用新的 platforms 模块
    """
    
    def __init__(self, mediacrawler_path: str = ""):
        """
        初始化
        mediacrawler_path 参数保留以兼容旧代码，但不再使用
        """
        logger.warning(
            "MediaCrawlerWrapper is deprecated. "
            "Use search_platform() and get_platform_detail() instead."
        )
    
    async def search_notes(
        self,
        platform: str,
        keyword: str,
        cookie: str = "",
        max_results: int = 20,
        search_type: str = "note",
    ) -> List[Dict[str, Any]]:
        """搜索笔记/用户（兼容旧接口）"""
        return await search_platform(
            platform=platform,
            keyword=keyword,
            cookie=cookie,
            mode="api",  # 默认 API 模式
            max_results=max_results,
            search_type=search_type,
        )
    
    async def get_note_detail(
        self,
        platform: str,
        note_id: str,
        cookie: str = "",
    ) -> Dict[str, Any]:
        """获取笔记详情（兼容旧接口）"""
        return await get_platform_detail(
            platform=platform,
            item_id=note_id,
            cookie=cookie,
            mode="api",
        )


# =============================================================================
# 工具函数：转换数据格式（兼容旧接口）
# =============================================================================

def _result_to_dict(result: Any) -> Dict[str, Any]:
    """将 SearchResult 转换为字典（兼容旧接口）"""
    if hasattr(result, '__dict__'):
        # dataclass
        data = {
            'id': result.id,
            'title': result.title,
            'desc': result.desc if hasattr(result, 'desc') else '',
            'author': result.author,
            'author_id': result.author_id,
            'cover': result.cover,
            'url': result.url,
            'platform': result.platform,
            'type': result.type,
            'likes': result.likes,
            'comments': result.comments,
            'shares': result.shares if hasattr(result, 'shares') else 0,
            'views': result.views if hasattr(result, 'views') else 0,
            'create_time': result.create_time,
            'raw_data': result.raw_data if hasattr(result, 'raw_data') else {},
        }
        return data
    elif isinstance(result, dict):
        return result
    else:
        return {}


def _detail_to_dict(detail: Any) -> Dict[str, Any]:
    """将 NoteDetail 转换为字典（兼容旧接口）"""
    if hasattr(detail, '__dict__'):
        # dataclass
        data = {
            'id': detail.id,
            'title': detail.title,
            'desc': detail.desc,
            'author': detail.author,
            'author_id': detail.author_id,
            'platform': detail.platform,
            'type': detail.type,
            'images': detail.images if hasattr(detail, 'images') else [],
            'video': detail.video if hasattr(detail, 'video') else '',
            'video_cover': detail.video_cover if hasattr(detail, 'video_cover') else '',
            'likes': detail.likes,
            'comments': detail.comments,
            'shares': detail.shares if hasattr(detail, 'shares') else 0,
            'collects': detail.collects if hasattr(detail, 'collects') else 0,
            'views': detail.views if hasattr(detail, 'views') else 0,
            'tags': detail.tags if hasattr(detail, 'tags') else [],
            'create_time': detail.create_time,
            'location': detail.location if hasattr(detail, 'location') else None,
            'raw_data': detail.raw_data if hasattr(detail, 'raw_data') else {},
        }
        return data
    elif isinstance(detail, dict):
        return detail
    else:
        return {}


# =============================================================================
# 获取 wrapper 实例（兼容旧代码）
# =============================================================================

def get_mediacrawler_wrapper(mediacrawler_path: str = "") -> MediaCrawlerWrapper:
    """
    获取 MediaCrawlerWrapper 实例（兼容旧代码）
    新代码请直接使用 search_platform() 和 get_platform_detail()
    """
    return MediaCrawlerWrapper(mediacrawler_path)
