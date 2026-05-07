"""
YLCraft — 素材采集 API
集成 MediaCrawler 核心功能

GET  /api/v1/crawler/platforms    — 获取支持的平台列表
GET  /api/v1/crawler/options     — 获取配置选项
POST /api/v1/crawler/search      — 搜索视频/图文素材
POST /api/v1/crawler/import      — 将采集结果导入素材库
GET  /api/v1/crawler/tasks/{id} — 查询采集任务状态（异步）
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.services.crawler import (
    CrawlerService,
    CrawlerResult,
    SearchRequest,
    CrawlerTaskResponse,
    get_crawler_service,
)

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
