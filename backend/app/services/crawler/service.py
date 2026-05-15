"""
YLCraft — 素材采集服务
集成 MediaCrawler 核心功能，支持多平台视频/图文素材搜索与采集

支持平台：小红书、抖音、快手、B站、微博、知乎
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Literal
from datetime import datetime

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
    # 国际平台
    TWITTER = "twitter"      # Twitter/X
    TIKTOK = "tiktok"        # TikTok
    INSTAGRAM = "instagram"   # Instagram
    THREADS = "threads"       # Threads
    YOUTUBE = "youtube"       # YouTube


class SearchRequest(BaseModel):
    """搜索请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks/bili/wb/zhihu")
    keyword: str = Field(..., description="搜索关键词")
    max_results: int = Field(20, description="最大结果数", ge=1, le=100)
    crawl_type: Literal["search", "detail", "creator"] = Field("search", description="采集类型")


class CrawlerResult(BaseModel):
    """采集结果项"""
    id: str = Field(..., description="内容ID")
    platform: str = Field(..., description="平台")
    title: str = Field("", description="标题")
    desc: str = Field("", description="描述")
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
    """素材采集服务"""

    def __init__(self):
        self.mediacrawler_path = self._find_mediacrawler()
        self.use_mediacrawler = bool(self.mediacrawler_path)
        self._wrapper = None

        if self.use_mediacrawler:
            try:
                from app.services.crawler.mediacrawler_wrapper import get_mediacrawler_wrapper
                self._wrapper = get_mediacrawler_wrapper()
                logger.info(f"[CrawlerService] MediaCrawler wrapper initialized")
            except Exception as e:
                logger.warning(f"[CrawlerService] Failed to initialize MediaCrawler wrapper: {e}")
                self.use_mediacrawler = False

        if self.use_mediacrawler:
            logger.info(f"[CrawlerService] MediaCrawler found at: {self.mediacrawler_path}")
        else:
            logger.warning("[CrawlerService] MediaCrawler not found, using yt-dlp fallback")

    def _find_mediacrawler(self) -> Optional[str]:
        """查找 MediaCrawler 安装路径"""
        # 检查常见位置
        possible_paths = [
            "F:/PycharmProjects/MediaCrawler",
            "F:/MediaCrawler",
            os.path.expanduser("~/MediaCrawler"),
            os.path.join(os.getcwd(), "MediaCrawler"),
        ]
        for path in possible_paths:
            main_py = os.path.join(path, "main.py")
            if os.path.exists(main_py):
                return path
        return None

    async def search_videos(
        self,
        platform: str,
        keyword: str,
        max_results: int = 20,
    ) -> list[CrawlerResult]:
        """
        搜索视频/图文素材
        优先使用 MediaCrawler，失败则降级到 yt-dlp
        """
        if self.use_mediacrawler:
            try:
                return await self._search_via_mediacrawler(platform, keyword, max_results)
            except Exception as e:
                logger.warning(f"[search_videos] MediaCrawler failed: {e}, falling back to yt-dlp")

        # 降级方案：使用 yt-dlp 搜索
        return await self._search_via_ytdlp(platform, keyword, max_results)

    async def _search_via_mediacrawler(
        self,
        platform: str,
        keyword: str,
        max_results: int,
    ) -> list[CrawlerResult]:
        """通过 MediaCrawler 搜索"""
        if not self.mediacrawler_path:
            return []

        # MediaCrawler 使用命令行方式调用
        # 这里我们创建一个临时配置并运行
        config = {
            "platform": platform,
            "lt": "qrcode",  # 登录方式
            "type": "search",
            "keywords": [keyword],
            "max_count": max_results,
            "enable_get_comments": False,
            "save_data_option": "json",
        }

        # 写入临时配置
        config_path = os.path.join(self.mediacrawler_path, "config", "base_config.py")
        logger.info(f"[search_via_mediacrawler] Config path: {config_path}")

        # 由于 MediaCrawler 需要交互式登录，我们这里简化处理
        # 实际生产环境应该先完成登录并保存 cookie
        raise NotImplementedError(
            "MediaCrawler integration requires pre-login. "
            "Please run MediaCrawler manually first to cache login state."
        )

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
            # 国际平台
            "twitter": f"ytsearch{max_results}:\"{keyword} site:twitter.com OR site:x.com\"",
            "tiktok": f"ytsearch{max_results}:\"{keyword} site:tiktok.com\"",
            "instagram": f"ytsearch{max_results}:\"{keyword} site:instagram.com\"",
            "threads": f"ytsearch{max_results}:\"{keyword} site:threads.net\"",
            "youtube": f"ytsearch{max_results}:\"{keyword} site:youtube.com\"",
        }

        actual_url = platform_search_map.get(platform, search_url)

        def _fetch():
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": "in_playlist",  # 只提取列表，不下载
                "nocheckcertificate": True,
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
                        logger.warning(f"[search_via_ytdlp] No results for {platform}: {keyword}")
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
                    logger.info(f"[search_via_ytdlp] Found {len(results)} results for {platform}: {keyword}")
                    return results
            except Exception as e:
                logger.error(f"[search_via_ytdlp] Error searching {platform}: {e}")
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
        if self._wrapper:
            try:
                results = await self._wrapper.search_notes(
                    platform=platform,
                    keyword=keyword,
                    cookie="",  # TODO: 从 PlatformConnection 获取
                    max_results=max_results,
                    search_type=search_type,
                )
                return self._parse_mediacrawler_results(results, platform)
            except Exception as e:
                logger.warning(f"[search_notes] MediaCrawler failed: {e}, falling back to yt-dlp")

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
        if self._wrapper:
            try:
                detail = await self._wrapper.get_note_detail(platform, note_id, cookie)
                return detail
            except Exception as e:
                logger.error(f"[get_note_detail] MediaCrawler failed: {e}")
                return {}

        logger.warning("[get_note_detail] MediaCrawler not available")
        return {}

    def _parse_mediacrawler_results(self, results: list[dict], platform: str) -> list[CrawlerResult]:
        """解析 MediaCrawler 返回的结果"""
        crawler_results = []
        for item in results:
            try:
                result = CrawlerResult(
                    id=item.get("note_id", "") or item.get("id", ""),
                    platform=platform,
                    title=item.get("title", ""),
                    desc=item.get("desc", "") or item.get("description", ""),
                    cover=item.get("cover", "") or item.get("thumbnail", ""),
                    video_url=item.get("video_url", "") or item.get("url", ""),
                    author=item.get("nickname", "") or item.get("author", ""),
                    author_id=item.get("user_id", "") or item.get("author_id", ""),
                    likes=item.get("liked_count", 0) or item.get("likes", 0),
                    comments=item.get("comment_count", 0) or item.get("comments", 0),
                    shares=item.get("share_count", 0) or item.get("shares", 0),
                    url=item.get("note_url", "") or item.get("url", ""),
                    create_time=str(item.get("time", "") or item.get("create_time", "")),
                    raw_data=item,
                )
                crawler_results.append(result)
            except Exception as e:
                logger.error(f"[_parse_mediacrawler_results] Error parsing item: {e}")
                continue

        return crawler_results

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
