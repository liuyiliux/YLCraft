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
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

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


# =============================================================================
# 辅助函数
# =============================================================================

def _get_conn_cookie(conn_id: str) -> str:
    """从 conn_id 获取 Cookie"""
    if not conn_id:
        return ""
    try:
        from app.services.platform_connection import PlatformConnectionService
        service = PlatformConnectionService()
        conn = service.get(conn_id)
        if conn and conn.cookie_content:
            return conn.cookie_content
    except Exception as e:
        logger.warning(f"Failed to get cookie from connection {conn_id}: {e}")
    return ""


# =============================================================================
# Response Models
# =============================================================================

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
    {"value": "wechat_mp", "label": "微信公众号", "icon": "wechat", "color": "#07C160"},
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

    # ===== 微信公众号特殊处理 =====
    if req.platform == "wechat_mp":
        return await _search_wechat_mp(req)

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
    - platform: 平台（xhs/dy/ks/bili/wechat_mp）
    - note_id: 笔记ID
    - conn_id: 可选，使用指定连接的 Cookie
    """
    logger.info(f"[get_note_detail] platform={platform} note_id={note_id}")

    # 微信公众号特殊处理：公众号账号没有"笔记详情"概念，返回空结果
    # 前端会直接使用搜索结果中的数据显示详情
    if platform == "wechat_mp":
        return NoteDetailResponse(
            success=True,
            data={
                "id": note_id,
                "platform": "wechat_mp",
                "title": "",
                "desc": "",
                "images": [],
                "video": "",
                "video_cover": "",
                "video_duration": 0,
                "author": "",
                "author_id": "",
                "author_avatar": "",
                "like_count": 0,
                "comment_count": 0,
                "share_count": 0,
                "view_count": 0,
                "create_time": "",
                "tags": [],
                "raw_data": {},
            },
            message="微信公众号详情由前端直接展示",
        )

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


# =============================================================================
# 微信公众号搜索（专用处理）
# =============================================================================

async def _search_wechat_mp(req: SearchEnhancedRequest) -> SearchResponse:
    """
    微信公众号搜索：根据 search_type 不同执行不同操作
    - "account": 搜索公众号
    - "article": 拉取文章列表（需在 filters 中传 fake_id）
    """
    from app.services.wechat_mp import get_wechat_mp_service
    from app.db.models.platform_connection import PlatformConnection, PlatformType
    from app.services.platform_connection.service import PlatformConnectionService

    service = get_wechat_mp_service()

    # 从请求中获取 conn_id
    conn_id = req.filters.get("conn_id", "") if req.filters else ""

    # 从数据库获取连接的 Cookie / Token。
    # cookie_content 是 Netscape 文件格式，不能直接放进 HTTP Cookie header；
    # 这里统一通过 PlatformConnectionService 提取原始 "k=v; ..." 格式。
    cookie = ""
    token = ""
    db_session = None
    try:
        from app.db.database import SessionLocal

        db_session = SessionLocal()
        conn_service = PlatformConnectionService(db_session)
        conn: PlatformConnection | None = None
        if conn_id:
            conn = conn_service.get(conn_id)
        else:
            conn = conn_service.get_active(PlatformType.WECHAT_MP)
            conn_id = conn.id if conn else ""

        if conn:
            cookie = conn_service.get_raw_cookie(conn.id) or ""
            credentials = conn.get_credentials()
            token = (
                str(credentials.get("token") or "")
                or str(conn.account_id or "")
            )
            logger.info(
                "[_search_wechat_mp] using conn=%s, cookie=%s, token=%s",
                conn.id,
                "yes" if cookie else "no",
                "yes" if token else "no",
            )
    except Exception as e:
        logger.warning(f"[_search_wechat_mp] 获取凭证失败: {e}")
    finally:
        if db_session is not None:
            db_session.close()

    if not cookie or not token:
        raise HTTPException(
            status_code=400,
            detail="微信公众号连接缺少 Cookie 或 token，请先在账号中心完成扫码登录",
        )

    if req.search_type == "account":
        # 搜索公众号
        result = await service.search_accounts(
            conn_id=conn_id,
            keyword=req.keyword,
            cookie=cookie,
            token=token,
            page=req.page,
            page_size=req.max_results,
        )
        accounts = result.get("list", [])

        # 转换为 CrawlerResult 格式
        from app.services.crawler.service import CrawlerResult
        results = []
        for acc in accounts:
            results.append(CrawlerResult(
                id=acc.get("fake_id", ""),
                platform="wechat_mp",
                title=acc.get("nickname", ""),
                desc=acc.get("signature", ""),
                cover=acc.get("round_head_img", ""),
                author=acc.get("nickname", ""),
                author_id=acc.get("fake_id", ""),
                url=f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={acc.get('fake_id', '')}",
                # 公众号账号本身没有"发布时间"，用空字符串
                create_time="",
                # 公众号没有粉丝数/文章数
                followers=0,
                videos=0,
                raw_data=acc,
            ))
        return SearchResponse(
            success=True,
            results=results,
            total=result.get("total", 0),
            message=f"找到 {result.get('total', 0)} 个公众号",
            using="wechat_mp_api",
        )

    elif req.search_type == "article":
        # 拉取文章列表
        fake_id = req.filters.get("fake_id", "") if req.filters else ""
        if not fake_id:
            raise HTTPException(status_code=400, detail="缺少 fake_id 参数")

        result = await service.get_articles(
            conn_id=conn_id,
            fake_id=fake_id,
            cookie=cookie,
            token=token,
            begin=(req.page - 1) * req.max_results,
            count=min(req.max_results, 5),
        )

        if result.get("error"):
            raise HTTPException(status_code=500, detail=f"拉取文章列表失败: {result.get('error')}")

        articles = result.get("list", [])
        from app.services.crawler.service import CrawlerResult
        results = []
        for art in articles:
            results.append(CrawlerResult(
                id=art.get("aid", ""),
                platform="wechat_mp",
                title=art.get("title", ""),
                desc=art.get("digest", ""),
                cover=art.get("cover", ""),
                author="",
                author_id="",
                url=art.get("link", ""),
                create_time=datetime.fromtimestamp(art.get("create_time", 0)).isoformat() if art.get("create_time") else "",
                raw_data=art,
            ))
        return SearchResponse(
            success=True,
            results=results,
            total=result.get("total_count", 0),
            message=f"已获取 {len(articles)} 篇文章（共约 {result.get('total_count', 0)} 篇）",
            using="wechat_mp_api",
        )

    else:
        raise HTTPException(status_code=400, detail=f"微信公众号不支持 search_type={req.search_type}，请使用 account 或 article")
