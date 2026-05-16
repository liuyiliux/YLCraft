"""
YLCraft — 素材采集服务
使用新的 platforms 模块进行多平台视频/图文素材搜索与采集
支持平台：小红书、B站、抖音、快手、微博、知乎
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from pydantic import BaseModel, Field

from app.services.crawler.models import NoteDetail, SearchFilter, SearchEnhancedRequest, NoteDetailResponse, FetchNoWatermarkRequest

logger = logging.getLogger("ylcraft.crawler")

# =============================================================================
# 数据模型
# =============================================================================

class CrawlerPlatform:
    """支持的平台列表"""
    # 国内平台
    XHS = "xhs"      # 小红书
    DOUYIN = "dy"     # 抖音
    KUAISHOU = "ks"  # 快手
    BILIBILI = "bili" # B站
    WEIBO = "wb"      # 微博
    ZHIHU = "zhihu"   # 知乎

class SearchRequest(BaseModel):
    """搜索请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks/bili/wb/zhihu")
    keyword: str = Field(..., description="搜索关键词")
    max_results: int = Field(20, description="最大结果数", ge=1, le=100)
    crawl_type: str = Field("search", description="采集类型")

class CrawlerResult(BaseModel):
    """采集结果项"""
    id: str = Field(..., description="内容ID")
    platform: str = Field(..., description="平台")
    title: str = Field("", description="标题")
    desc: Optional[str] = Field(None, description="描述")
    cover: str = Field("", description="封面图URL")
    video_url: str = Field("", description="视频URL")
    author: str = Field("", description="作者")
    author_id: str = Field("", description="作者ID")
    likes: int = Field(0, description="点赞数")
    comments: int = Field(0, description="评论数")
    shares: int = Field(0, description="分享数")
    url: str = Field("", description="原文链接")
    create_time: str = Field("", description="发布时间")
    raw_data: dict = Field(default_factory=dict, description="原始数据")

class CrawlerTaskResponse(BaseModel):
    """采集任务响应"""
    task_id: str
    status: str = "pending"
    message: str = ""
    results: list[CrawlerResult] = []
    total: int = 0
    created_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None

# =============================================================================
# 缓存任务存储（生产环境应使用 Redis）
# =============================================================================

_crawler_tasks: dict[str, dict] = {}


# =============================================================================
# 核心服务类
# =============================================================================

class CrawlerService:
    """
    素材采集服务
    使用新的 platforms 模块，降级到 yt-dlp
    """

    def __init__(self):
        logger.info(f"[CrawlerService] Initialized (using platforms module)")

    async def search_videos(
        self,
        platform: str,
        keyword: str,
        max_results: int = 20,
        search_type: str = "note",
        sort_by: str = "",
        page: int = 1,
        **kwargs,
    ) -> list[CrawlerResult]:
        """
        搜索视频/图文素材
        优先使用 platforms 模块，失败则降级到 yt-dlp
        """
        # 1. 尝试新的 platforms 模块
        try:
            return await self._search_via_platforms(platform, keyword, max_results, search_type, sort_by, page, **kwargs)
        except Exception as e:
            logger.warning(f"[search_videos] platforms module failed: {e}, falling back to yt-dlp")

        # 2. 降级方案：使用 yt-dlp 搜索
        return await self._search_via_ytdlp(platform, keyword, max_results)

    async def _search_via_platforms(
        self,
        platform: str,
        keyword: str,
        max_results: int = 20,
        search_type: str = "note",
        sort_by: str = "",
        page: int = 1,
        **kwargs,
    ) -> list[CrawlerResult]:
        """通过新的 platforms 模块搜索"""
        try:
            from app.services.platforms import create_client, search as platform_search
            from app.services.platforms.types import SearchResult as PlatformSearchResult

            logger.info(f"[{self.__class__.__name__}] Searching {platform}: {keyword} (type={search_type}, sort={sort_by})")

            # 调用 platforms 模块的搜索功能
            results = await platform_search(
                platform=platform,
                keyword=keyword,
                mode="api",
                max_results=max_results,
                search_type=search_type,
                sort_by=sort_by,
                page=page,
                **kwargs,
            )

            if not results:
                logger.warning(f"[_search_via_platforms] No results from platforms module for {platform}")
                return []

            # 提取总条数（B站等平台会在第一个结果的 raw_data._total 中存放）
            total_from_platform = results[0].raw_data.get("_total") if results else None

            # 转换为 CrawlerResult
            crawler_results = []
            for idx, item in enumerate(results):
                try:
                    raw_data = dict(item.raw_data)
                    # 把总条数放到第一个结果的 raw_data 中，方便上层读取
                    if idx == 0 and total_from_platform:
                        raw_data["_total"] = total_from_platform
                    result = CrawlerResult(
                        id=item.id,
                        platform=item.platform,
                        title=item.title,
                        desc=item.desc if item.desc else None,
                        cover=item.cover,
                        video_url=item.url,
                        author=item.author,
                        author_id=item.author_id,
                        likes=item.likes,
                        comments=item.comments,
                        shares=item.shares,
                        url=item.url,
                        create_time=item.create_time,
                        raw_data=raw_data,
                    )
                    crawler_results.append(result)
                except Exception as e:
                    logger.error(f"[_search_via_platforms] Error converting result: {e}")
                    continue

            logger.info(f"[_search_via_platforms] Found {len(crawler_results)} results for {platform}: {keyword}")
            return crawler_results

        except ImportError:
            logger.warning("[_search_via_platforms] platforms module not available")
            return []
        except Exception as e:
            logger.error(f"[_search_via_platforms] Error: {e}")
            return []

    async def _search_via_ytdlp(
        self,
        platform: str,
        keyword: str,
        max_results: int,
    ) -> list[CrawlerResult]:
        """通过 yt-dlp 搜索（降级方案）"""
        import yt_dlp

        # yt-dlp 搜索语法：ytsearchN:"keyword"
        search_url = f"ytsearch{max_results}:\"{keyword}\""

        # 根据平台调整搜索前缀
        platform_search_map = {
            # 国内平台
            "bili": f"ytsearch{max_results}:\"{keyword} site:bilibili.com\"",
            "dy": f"ytsearch{max_results}:\"{keyword} site:douyin.com\"",
            "ks": f"ytsearch{max_results}:\"{keyword} site:kuaishou.com\"",
            "wb": f"ytsearch{max_results}:\"{keyword} site:weibo.com\"",
            "xhs": f"ytsearch{max_results}:\"{keyword} site:xiaohongshu.com\"",
            "zhihu": f"ytsearch{max_results}:\"{keyword} site:zhihu.com\"",
        }

        actual_url = platform_search_map.get(platform, search_url)

        def _fetch():
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": "in_playlist",  # 只提取列表，不下载
                "no_check_certificate": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                "default_search": "ytsearch",
                "format": "best",
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(actual_url, download=False)
                    if not info or "entries" not in info:
                        logger.warning(f"[_search_via_ytdlp] No results for {platform}: {keyword}")
                        return []

                    results = []
                    for entry in info["entries"][:max_results]:
                        if not entry:
                            continue
                        result = CrawlerResult(
                            id=entry.get("id", ""),
                            platform=platform,
                            title=entry.get("title", ""),
                            desc=entry.get("description", ""),
                            cover=entry.get("thumbnail", ""),
                            video_url=entry.get("url", "") or entry.get("webpage_url", ""),
                            author=entry.get("uploader", "") or entry.get("channel", ""),
                            author_id=entry.get("channel_id", ""),
                            likes=entry.get("like_count", 0) or 0,
                            comments=entry.get("comment_count", 0) or 0,
                            shares=entry.get("repost_count", 0) or 0,
                            url=entry.get("webpage_url", ""),
                            create_time=str(entry.get("timestamp", "")),
                            raw_data=entry,
                        )
                        results.append(result)
                    logger.info(f"[_search_via_ytdlp] Found {len(results)} results for {platform}: {keyword}")
                    return results
            except Exception as e:
                logger.error(f"[_search_via_ytdlp] Error searching {platform}: {e}")
                return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch)

    async def search_notes(
        self,
        platform: str,
        keyword: str,
        max_results: int = 20,
        search_type: str = "note",  # "note" or "user"
        filters: dict = {},
    ) -> list[CrawlerResult]:
        """
        搜索笔记或用户
        search_type: "note" = 搜索笔记, "user" = 搜索用户
        filters: 可选筛选条件（排序、时间范围等）
        """
        # 使用 platforms 模块搜索
        try:
            return await self._search_via_platforms(platform, keyword, max_results)
        except Exception as e:
            logger.warning(f"[search_notes] platforms module failed: {e}, falling back to yt-dlp")

        # 降级方案：使用 yt-dlp 搜索
        return await self._search_via_ytdlp(platform, keyword, max_results)

    async def get_note_detail(
        self,
        platform: str,
        note_id: str,
        cookie: str = "",
    ) -> dict:
        """
        获取笔记详情（无水印）
        返回包含无水印图片/视频 URL 的字典
        """
        try:
            from app.services.platforms import create_client
            from app.services.platforms.types import NoteDetail as PlatformNoteDetail

            client = create_client(platform, mode="api", cookie=cookie)
            if not client:
                logger.error(f"[get_note_detail] Failed to create client for {platform}")
                return {}

            detail = await client.get_detail(note_id)

            if not detail:
                logger.warning(f"[get_note_detail] No detail found for {note_id}")
                return {}

            # 转换为字典
            return {
                "id": detail.id,
                "platform": detail.platform,
                "title": detail.title,
                "desc": detail.desc,
                "images": detail.images if hasattr(detail, 'images') else [],
                "video": detail.video if hasattr(detail, 'video') else "",
                "author": detail.author,
                "author_id": detail.author_id,
                "likes": detail.likes,
                "comments": detail.comments,
                "shares": detail.shares,
                "collects": detail.collects if hasattr(detail, 'collects') else 0,
                "views": detail.views if hasattr(detail, 'views') else 0,
            }

        except Exception as e:
            logger.error(f"[get_note_detail] Error: {e}")
            return {}

    async def import_to_asset_library(self, results: list[CrawlerResult]) -> list[str]:
        """
        将采集结果导入到 YLCraft 素材库
        返回导入的素材 ID 列表
        """
        from app.db.database import get_session
        from app.db.models.asset import Asset
        from app.services.asset.service import AssetService

        asset_ids = []
        async with get_session() as db_session:
            asset_service = AssetService(db_session)
            for result in results:
                try:
                    # 检查是否已存在
                    existing = await asset_service.get_by_url(result.url)
                    if existing:
                        asset_ids.append(existing.id)
                        continue

                    # 创建新素材记录
                    asset_type = "video"
                    asset = await asset_service.create(
                        asset_type=asset_type,
                        title=result.title or "未命名素材",
                        source_url=result.url,
                        platform=result.platform,
                        author=result.author,
                        cover_url=result.cover,
                        status="parsed",
                        metadata={
                            "crawler": True,
                            "likes": result.likes,
                            "comments": result.comments,
                            "shares": result.shares,
                            "author_id": result.author_id,
                        },
                    )
                    asset_ids.append(asset.id)
                except Exception as e:
                    logger.error(f"[import_to_asset_library] Failed to import {result.id}: {e}")

        return asset_ids


# =============================================================================
# 全局服务实例
# =============================================================================

_crawler_service: Optional[CrawlerService] = None


def get_crawler_service() -> CrawlerService:
    global _crawler_service
    if _crawler_service is None:
        _crawler_service = CrawlerService()
    return _crawler_service
