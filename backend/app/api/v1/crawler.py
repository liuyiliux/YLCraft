"""
YLCraft — 素材采集 API
集成 MediaCrawler 核心功能

GET  /api/v1/crawler/platforms    — 获取支持的平台列表
GET  /api/v1/crawler/options     — 获取配置选项
POST /api/v1/crawler/search      — 搜索视频/图文素材
POST /api/v1/crawler/import      — 将采集结果导入素材库
GET  /api/v1/crawler/tasks/{id} — 查询采集任务状态（异步）
POST /api/v1/crawler/search-enhanced — 增强搜索（支持笔记/用户）
GET  /api/v1/crawler/note-detail  — 获取笔记详情（无水印）
POST /api/v1/crawler/fetch-no-watermark — 批量获取无水印资源
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List

from app.services.crawler import (
    CrawlerService,
    CrawlerResult,
    SearchRequest,
    CrawlerTaskResponse,
    get_crawler_service,
)
from app.services.crawler.models import NoteDetail, SearchFilter, SearchEnhancedRequest, NoteDetailResponse, FetchNoWatermarkRequest

router = APIRouter()
logger = logging.getLogger("ylcraft.api.crawler")

# 内存任务存储（生产环境应使用 Redis）
_crawler_tasks: dict[str, dict] = {}


# =============================================================================
# 平台配置
# =============================================================================

PLATFORMS = [
    {"value": "xhs",   "label": "小红书",   "icon": "book",        "color": "#fe2c55"},
    {"value": "dy",    "label": "抖音",     "icon": "video",       "color": "#000000"},
    {"value": "ks",    "label": "快手",     "icon": "play-circle", "color": "#ff5000"},
    {"value": "bili",  "label": "B站",     "icon": "tv",          "color": "#00aeec"},
    {"value": "wb",    "label": "微博",     "icon": "message",     "color": "#ff8200"},
    {"value": "zhihu", "label": "知乎",     "icon": "question",    "color": "#0066ff"},
]

CRAWLER_TYPES = [
    {"value": "search",   "label": "关键词搜索"},
    {"value": "detail",   "label": "指定内容ID"},
    {"value": "creator",  "label": "创作者主页"},
]


# =============================================================================
# 请求/响应模型
# =============================================================================

class SearchResponse(BaseModel):
    """搜索响应"""
    success: bool
    results: list[CrawlerResult] = []
    total: int = 0
    message: str = ""
    using: str = ""  # 使用的搜索引擎


class ImportRequest(BaseModel):
    """导入请求"""
    results: list[dict] = Field(..., description="要导入的采集结果列表")


class ImportResponse(BaseModel):
    """导入响应"""
    success: bool
    imported_count: int = 0
    asset_ids: list[str] = []
    message: str = ""


# =============================================================================
# 增强搜索模型
# =============================================================================

class SearchEnhancedRequest(BaseModel):
    """增强搜索请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks/bili/wb/zhihu")
    keyword: str = Field(..., description="搜索关键词")
    search_type: str = Field("note", description="搜索类型: note/user/article/bangumi/movie/live")
    max_results: int = Field(20, description="每页结果数", ge=1, le=100)
    sort_by: str = Field("", description="排序方式")
    order_sort: int = Field(0, description="排序方向：0=高到低，1=低到高（仅bili用户搜索有效）")
    filters: dict = Field(default_factory=dict, description="筛选条件")
    page: int = Field(1, description="页码", ge=1)


class NoteDetailResponse(BaseModel):
    """笔记详情响应"""
    success: bool
    data: Optional[NoteDetail] = None
    message: str = ""


class FetchNoWatermarkRequest(BaseModel):
    """批量获取无水印资源请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks")
    note_ids: list[str] = Field(..., description="笔记ID列表")


# =============================================================================
# API 端点
# =============================================================================

@router.get("/platforms", summary="获取支持的平台列表")
async def get_platforms():
    """返回所有支持的平台"""
    return {"platforms": PLATFORMS}


@router.get("/options", summary="获取采集配置选项")
async def get_options():
    """返回采集类型和配置选项"""
    return {
        "crawler_types": CRAWLER_TYPES,
        "platforms": PLATFORMS,
    }


@router.post("/search", summary="搜索视频/图文素材", response_model=SearchResponse)
async def search_materials(req: SearchRequest):
    """
    搜索素材
    优先使用 MediaCrawler，失败则降级到 yt-dlp
    """
    logger.info(f"[search] platform={req.platform} keyword={req.keyword} max={req.max_results}")

    try:
        service = get_crawler_service()
        results = await service.search_videos(
            platform=req.platform,
            keyword=req.keyword,
            max_results=req.max_results,
        )

        return SearchResponse(
            success=True,
            results=results,
            total=len(results),
            message=f"找到 {len(results)} 条结果",
            using="MediaCrawler" if service.use_mediacrawler else "yt-dlp",
        )
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.error(f"[search] Error: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.post("/import", summary="导入到素材库", response_model=ImportResponse)
async def import_to_assets(req: ImportRequest):
    """
    将采集结果导入到 YLCraft 素材库
    """
    logger.info(f"[import] Importing {len(req.results)} results to asset library")

    try:
        # 转换 dict 到 CrawlerResult
        from app.services.crawler import CrawlerResult
        results = [CrawlerResult(**r) for r in req.results]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"数据格式错误: {str(e)}")

    try:
        service = get_crawler_service()
        asset_ids = await service.import_to_asset_library(results)

        return ImportResponse(
            success=True,
            imported_count=len(asset_ids),
            asset_ids=asset_ids,
            message=f"成功导入 {len(asset_ids)} 条素材到素材库",
        )
    except Exception as e:
        logger.error(f"[import] Error: {e}")
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.get("/tasks/{task_id}", summary="查询采集任务状态")
async def get_task_status(task_id: str):
    """查询异步采集任务状态"""
    task_data = _crawler_tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="任务不存在")

    return task_data


# =============================================================================
# 新增：增强搜索 & 笔记详情端点
# =============================================================================


@router.post("/search-enhanced", summary="增强搜索（支持笔记/用户）", response_model=SearchResponse)
async def search_enhanced(req: SearchEnhancedRequest):
    """
    增强搜索：支持搜索笔记和用户
    - search_type: "note" = 搜索笔记, "user" = 搜索用户, "article" = 搜索专栏
    - sort_by: 排序方式（各平台自定义）
    - filters: 可选筛选条件
    """
    logger.info(f"[search_enhanced] platform={req.platform} keyword={req.keyword} type={req.search_type} sort={req.sort_by}")

    service = get_crawler_service()

    # ===== 普通搜索模式 =====
    try:
        using = "platforms"
        results = await service.search_videos(
            platform=req.platform,
            keyword=req.keyword,
            max_results=req.max_results,
            search_type=req.search_type,
            sort_by=req.sort_by,
            order_sort=req.order_sort,
            page=req.page,
            filters=req.filters,
        )

        if not results:
            logger.warning(f"[search_enhanced] No results via platforms module for {req.platform}")

        # 从第一个结果的 raw_data 中提取平台返回的真实总条数
        total = len(results)
        if results and results[0].raw_data.get("_total"):
            total = results[0].raw_data["_total"]

        return SearchResponse(
            success=True,
            results=results,
            total=total,
            message=f"找到 {total} 条结果",
            using=using,
        )
    except Exception as e:
        logger.error(f"[search_enhanced] Error: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.get("/note-detail", summary="获取笔记详情（无水印）", response_model=NoteDetailResponse)
async def get_note_detail(platform: str, note_id: str, conn_id: str = ""):
    """
    获取笔记详情（无水印图片 & 视频）
    - platform: 平台（xhs/dy/ks）
    - note_id: 笔记ID
    - conn_id: 可选，使用指定连接的 Cookie
    """
    logger.info(f"[get_note_detail] platform={platform} note_id={note_id}")

    # 获取 Cookie
    cookie = ""
    if conn_id:
        try:
            from app.services.platform_connection import get_platform_connection_service
            service = get_platform_connection_service()
            conn = await service.get_by_id(conn_id)
            if conn and conn.cookie_content:
                cookie = conn.cookie_content
        except Exception as e:
            logger.warning(f"[get_note_detail] Failed to get cookie from connection: {e}")

    try:
        service = get_crawler_service()
        detail = await service.get_note_detail(platform, note_id, cookie)

        if not detail:
            raise HTTPException(status_code=404, detail="笔记不存在或获取失败")

        # 转换 dict 到 NoteDetail 模型
        from app.services.crawler.models import NoteDetail
        note_detail = NoteDetail(**detail)

        return NoteDetailResponse(
            success=True,
            data=note_detail,
            message="获取成功",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_note_detail] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取笔记详情失败: {str(e)}")


@router.post("/fetch-no-watermark", summary="批量获取无水印资源")
async def fetch_no_watermark(req: FetchNoWatermarkRequest):
    """
    批量获取无水印图片/视频
    输入：平台 + 笔记ID列表
    输出：下载链接列表
    """
    logger.info(f"[fetch_no_watermark] platform={req.platform} note_count={len(req.note_ids)}")

    try:
        service = get_crawler_service()
        results = []

        for note_id in req.note_ids:
            try:
                detail = await service.get_note_detail(req.platform, note_id, "")
                if detail:
                    results.append({
                        "note_id": note_id,
                        "images": detail.get("images", []),
                        "video": detail.get("video", ""),
                        "title": detail.get("title", ""),
                    })
            except Exception as e:
                logger.error(f"[fetch_no_watermark] Failed for {note_id}: {e}")
                continue

        return {
            "success": True,
            "results": results,
            "total": len(results),
            "message": f"成功获取 {len(results)} 条笔记的无水印资源",
        }
    except Exception as e:
        logger.error(f"[fetch_no_watermark] Error: {e}")
        raise HTTPException(status_code=500, detail=f"批量获取失败: {str(e)}")

    
# =========================================================================
# 字幕下载端点
# =========================================================================

@router.get("/subtitles", summary="获取字幕列表", response_model=SubtitleListResponse)
async def get_subtitles(platform: str, item_id: str):
    """
    获取视频的字幕列表
    - platform: 平台（目前仅支持 bili）
    - item_id: 视频ID（bvid）
    """
    logger.info(f"[get_subtitles] platform={platform} item_id={item_id}")
    
    if platform != "bili":
        raise HTTPException(status_code=400, detail="该平台不支持字幕下载")
    
    try:
        from app.services.platforms import create_client
        async with create_client(platform, mode="api") as client:
            subtitles = await client.get_subtitles(item_id)
            return {
                "success": True,
                "data": subtitles,
                "message": f"找到 {len(subtitles)} 个字幕"
            }
    except Exception as e:
        logger.error(f"[get_subtitles] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取字幕列表失败: {str(e)}")


@router.get("/subtitle/download", summary="下载字幕文件")
async def download_subtitle(platform: str, item_id: str, lan: str = "zh-CN", format: str = "srt"):
    """
    下载字幕文件（SRT/ASS 格式）
    - platform: 平台（目前仅支持 bili）
    - item_id: 视频ID（bvid）
    - lan: 字幕语言（如 zh-CN, en-US）
    - format: 格式（srt 或 ass）
    """
    logger.info(f"[download_subtitle] platform={platform} item_id={item_id} lan={lan} format={format}")
    
    if platform != "bili":
        raise HTTPException(status_code=400, detail="该平台不支持字幕下载")
    
    if format not in ["srt", "ass"]:
        raise HTTPException(status_code=400, detail="格式仅支持 srt 或 ass")
    
    try:
        from app.services.platforms import create_client
        from fastapi.responses import PlainTextResponse
        
        async with create_client(platform, mode="api") as client:
            # 1. 获取字幕列表
            subtitles = await client.get_subtitles(item_id)
            subtitle = next((s for s in subtitles if s.get("lan") == lan), None)
            
            if not subtitle:
                raise HTTPException(status_code=404, detail=f"未找到 {lan} 语言的字幕")
            
            # 2. 下载并转换
            content = await client.download_subtitle(subtitle.get("subtitle_url"), format)
            
            if not content:
                raise HTTPException(status_code=500, detail="字幕内容为空")
            
            # 3. 返回文件
            filename = f"{item_id}_{lan}.{format}"
            return PlainTextResponse(
                content=content,
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "Content-Type": "text/plain; charset=utf-8"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[download_subtitle] Error: {e}")
        raise HTTPException(status_code=500, detail=f"下载字幕失败: {str(e)}")


class SubtitleListResponse(BaseModel):
    """字幕列表响应"""
    success: bool
    data: List[Dict] = []
    message: str = ""