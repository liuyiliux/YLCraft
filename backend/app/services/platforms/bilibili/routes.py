"""
B站专属 API 路由

提供 B站 平台的专属功能接口：
- 弹幕获取
- 作品数据统计
- 评论获取
- 字幕获取
"""

from __future__ import annotations

import logging
from typing import List, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("ylcraft.api.bilibili")


# =============================================================================
# Router 实例
# =============================================================================

router = APIRouter(tags=["Bilibili"])


# =============================================================================
# 辅助函数
# =============================================================================

def _get_conn_cookie(conn_id: str) -> str:
    """从 conn_id 获取 Cookie"""
    if not conn_id:
        return ""
    try:
        from app.db.database import SessionLocal
        from app.services.platform_connection import PlatformConnectionService
        session = SessionLocal()
        try:
            service = PlatformConnectionService(session=session)
            conn = service.get(conn_id)
            if conn and conn.cookie_content:
                return conn.cookie_content
            # 降级：尝试从 credentials 获取 raw cookie
            if conn and conn.get_credentials():
                creds = conn.get_credentials()
                return creds.get("raw", "") or ""
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Failed to get cookie from connection {conn_id}: {e}")
    return ""


# =============================================================================
# Response Models
# =============================================================================

class BilibiliDanmakuResponse(BaseModel):
    success: bool = True
    data: List[Dict] = []
    message: str = ""


class BilibiliStatsResponse(BaseModel):
    success: bool = True
    data: Dict = {}
    message: str = ""


class BilibiliCommentsResponse(BaseModel):
    success: bool = True
    data: Dict = {}
    message: str = ""


class BilibiliSubtitlesResponse(BaseModel):
    success: bool = True
    data: List[Dict] = []
    message: str = ""


class BilibiliVideoInfoResponse(BaseModel):
    success: bool = True
    data: Dict = {}
    message: str = ""


# =============================================================================
# API 端点
# =============================================================================

@router.get("/danmaku", summary="获取B站弹幕", response_model=BilibiliDanmakuResponse)
async def get_danmaku(
    bvid: str = Query(..., description="B站视频 BV 号"),
    cid: int = Query(0, description="分P ID"),
    conn_id: str = Query("", description="平台连接 ID"),
):
    """
    获取B站视频弹幕列表
    """
    try:
        from app.services.platforms import create_client
        cookie = _get_conn_cookie(conn_id) if conn_id else ""
        async with create_client("bili", mode="api", cookie=cookie) as client:
            danmaku_list = await client.get_danmaku(bvid, cid)
            return BilibiliDanmakuResponse(
                success=True,
                data=danmaku_list,
                message=f"共 {len(danmaku_list)} 条弹幕",
            )
    except Exception as e:
        logger.error(f"[bili/danmaku] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取弹幕失败: {str(e)}")


@router.get("/stats", summary="获取B站作品数据", response_model=BilibiliStatsResponse)
async def get_stats(
    bvid: str = Query("", description="BV 号"),
    aid: int = Query(0, description="AV 号"),
    conn_id: str = Query("", description="平台连接 ID"),
):
    """
    获取B站视频作品数据（播放/点赞/投币/收藏/评论/分享/弹幕数）
    """
    try:
        if not bvid and not aid:
            raise HTTPException(status_code=400, detail="必须提供 bvid 或 aid")

        from app.services.platforms import create_client
        cookie = _get_conn_cookie(conn_id) if conn_id else ""
        async with create_client("bili", mode="api", cookie=cookie) as client:
            stats = await client.get_stats(bvid, aid)
            return BilibiliStatsResponse(
                success=bool(stats),
                data=stats or {},
                message="" if stats else "获取失败",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[bili/stats] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments", summary="获取B站评论", response_model=BilibiliCommentsResponse)
async def get_comments(
    bvid: str = Query(..., description="BV 号"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    sort: int = Query(0, description="排序: 0=最热 1=最新 2=最早"),
    conn_id: str = Query("", description="平台连接 ID"),
):
    """
    获取B站视频评论列表
    """
    try:
        from app.services.platforms import create_client
        cookie = _get_conn_cookie(conn_id) if conn_id else ""
        async with create_client("bili", mode="api", cookie=cookie) as client:
            result = await client.get_comments_paged(bvid, page, page_size, sort)
            return BilibiliCommentsResponse(
                success=True,
                data=result,
                message=f"共 {result.get('total', 0)} 条评论",
            )
    except Exception as e:
        logger.error(f"[bili/comments] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subtitles", summary="获取B站字幕", response_model=BilibiliSubtitlesResponse)
async def get_subtitles(
    bvid: str = Query(..., description="B站视频 BV 号"),
    conn_id: str = Query("", description="平台连接 ID"),
):
    """
    获取B站视频字幕列表
    """
    try:
        from app.services.platforms import create_client
        cookie = _get_conn_cookie(conn_id) if conn_id else ""
        async with create_client("bili", mode="api", cookie=cookie) as client:
            subtitles = await client.get_subtitles(bvid)
            return BilibiliSubtitlesResponse(
                success=True,
                data=subtitles,
                message=f"找到 {len(subtitles)} 个字幕" if subtitles else "暂无字幕",
            )
    except Exception as e:
        logger.error(f"[bili/subtitles] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取字幕失败: {str(e)}")


@router.get("/video/info", summary="获取B站视频信息", response_model=BilibiliVideoInfoResponse)
async def get_video_info(
    bvid: str = Query(..., description="B站视频 BV 号"),
    conn_id: str = Query("", description="平台连接 ID"),
):
    """
    获取B站视频详细信息（标题、描述、作者、统计数据等）
    """
    try:
        from app.services.platforms import create_client
        cookie = _get_conn_cookie(conn_id) if conn_id else ""
        async with create_client("bili", mode="api", cookie=cookie) as client:
            info = await client.get_video_info(bvid)
            return BilibiliVideoInfoResponse(
                success=bool(info),
                data=info or {},
                message=info.get("title", "") if info else "",
            )
    except Exception as e:
        logger.error(f"[bili/video/info] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频信息失败: {str(e)}")
