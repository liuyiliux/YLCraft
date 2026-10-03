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
        "twitter",
        "fanqie",
        # ⚠️ 知乎（zhihu）已移除（2026-10-01 用户要求）。
        # 它从来只有登记（cookies/detector + yt-dlp 降级），没有真实采集客户端，
        # 属于"假支持"：选了只会走 yt-dlp 兜底，结果不可靠。
        # youtube（2026-10-01）：VPN 通了之后用 yt-dlp 实现的采集客户端
        # （搜索/详情/频道），见 platforms/youtube/ 的实测记录。
        "youtube",
        # telegram（2026-10-01）：A 方案免登录抓公开频道（含频道内
        # `?q=` 关键词搜索）+ B 方案 MTProto 登录（全局搜索/我的频道）。
        # 见 platforms/telegram/ 的实测记录。
        "telegram",
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

def supported_platforms() -> set[str]:
    """已注册（**真正实现**）的平台名，含别名。

    ⚠️ **用来区分"没实现"和"没搜到"**（2026-09-29）

    前端下拉里可能有平台可选，但后端没客户端 ——
    这时必须**显式报错**，不能静默返回空列表
    （用户会把"没实现"理解成"没搜到"，属假阴性）。

    见 `docs/platform/ADDING_A_PLATFORM.md` 的铁律第 2 条。
    """
    _auto_discover_platforms()
    return PlatformClientFactory.supported()


def create_client(
    platform: str,
    mode: str = "api",
    cookie: str = "",
    **kwargs
) -> Optional[BasePlatformClient]:
    """
    创建平台客户端（便捷函数）
    
    Args:
        platform: 平台标识 (xhs, bili, dy, ks, wb)
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
    conn_id: str = "",
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
        conn_id: 平台连接 ID。用于缓存键与浏览器会话复用
            （不同账号结果不同，必须区分）
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
    # conn_id 单独传：它属于 ClientConfig，供缓存键/会话复用使用
    if conn_id:
        config_kwargs['conn_id'] = conn_id
    
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

    # ==========================================================================
    # 搜索结果缓存（2026-09-29 加）
    # ==========================================================================
    #
    # 用户反馈"切换分页再切回来时候不用重新查询"。
    #
    # 实测各平台单次搜索：B站 ~2s / 小红书 ~2s / 抖音 ~4s /
    # **X ~15s / 微博 ~21s**（后者要开浏览器）。
    # 翻页、切回、重复搜同一关键词每次都重跑 —— 微博/X 尤其痛。
    #
    # 缓存放**这个共享入口**，所有平台的 api/patchright 路径都受益
    # （和 base._init_patchright 只覆盖部分路径的教训一致）。
    from .cache import get_search_cache

    cache = get_search_cache()
    # ⚠️ 游标必须进缓存键（2026-10-03 修）
    #
    # `dialogs` / `saved`（我的频道 / 我的收藏）**不用页码翻页**，
    # 而是用 MTProto 游标 `offset_id`（"取比它更旧的"）。
    # 而缓存键里只有 `page` —— 于是"首次"和"带游标的下一页"
    # 算出**同一个键**，第二次直接命中首次的缓存，
    # 实测两页返回**完全一样的 10 条**（假翻页）。
    _cursor = search_kwargs.get("offset_id") or 0
    cache_key = cache.make_key(
        platform=platform,
        keyword=keyword,
        page=page,
        size=max_results,
        search_type=search_type,
        conn_id=conn_id,
        sort_by=sort_by,
        # 游标不同的请求必须是不同的缓存项
        extra=f"cur{_cursor}" if _cursor else "",
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    async with client:
        results = await client.search(params)

    # ⚠️ **只缓存非空结果** —— 空结果可能来自限流/风控
    # （抖音实测：连续请求返回空，等 60 秒又好）。
    # 缓存空结果会让"稍后重试"也拿不到数据。
    if results:
        cache.set(cache_key, results)
    return results


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
