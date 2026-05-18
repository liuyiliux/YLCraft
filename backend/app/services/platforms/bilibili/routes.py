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
# Cookie 获取（统一接口，不重复查询）
# =============================================================================

def get_raw_cookie(conn_id: str) -> str:
    """
    获取原始格式 Cookie（用于 HTTP Header）
    使用统一的 PlatformConnectionService，直接返回 raw 格式

    Args:
        conn_id: 平台连接 ID

    Returns:
        原始格式 "key=value; key2=value2"，失败返回空字符串
    """
    if not conn_id:
        return ""

    try:
        from app.db.database import SessionLocal
        from app.services.platform_connection import PlatformConnectionService

        session = SessionLocal()
        try:
            service = PlatformConnectionService(session=session)
            cookie = service.get_raw_cookie(conn_id)
            if cookie:
                logger.debug(f"[bili/get_raw_cookie] Got cookie for {conn_id}, length={len(cookie)}")
            else:
                logger.warning(f"[bili/get_raw_cookie] No cookie for {conn_id}")
            return cookie or ""
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"[bili/get_raw_cookie] Failed to get cookie from connection {conn_id}: {e}")
    return ""


def extract_bili_jct(cookie: str) -> str:
    """
    从 Cookie 中提取 bili_jct (CSRF token)

    Args:
        cookie: 原始 Cookie 字符串

    Returns:
        bili_jct 值，失败返回空字符串
    """
    if not cookie:
        return ""
    try:
        import re
        match = re.search(r'bili_jct=([^;]+)', cookie)
        if match:
            return match.group(1)
    except Exception as e:
        logger.warning(f"[bili/extract_bili_jct] Failed to extract bili_jct: {e}")
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


class BilibiliSendCommentRequest(BaseModel):
    bvid: str
    message: str
    parent: int = 0
    root: int = 0


class BilibiliSendCommentResponse(BaseModel):
    success: bool = True
    rpid: int = 0
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
        cookie = get_raw_cookie(conn_id) if conn_id else ""
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
        cookie = get_raw_cookie(conn_id) if conn_id else ""
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
    offset: str = Query("", description="游标偏移值，用于加载更多（从响应的 next_offset 获取）"),
    conn_id: str = Query("", description="平台连接 ID"),
):
    """
    获取B站视频评论列表
    """
    try:
        from app.services.platforms import create_client
        cookie = get_raw_cookie(conn_id) if conn_id else ""
        async with create_client("bili", mode="api", cookie=cookie) as client:
            result = await client.get_comments_paged(bvid, page, page_size, sort, offset)
            return BilibiliCommentsResponse(
                success=True,
                data=result,
                message=f"共 {result.get('total', 0)} 条评论",
            )
    except Exception as e:
        logger.error(f"[bili/comments] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BilibiliSubtitleDownloadResponse(BaseModel):
    success: bool = True
    data: str = ""
    message: str = ""


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
        cookie = get_raw_cookie(conn_id) if conn_id else ""
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


@router.get("/subtitle/download", summary="下载B站字幕文件")
async def download_subtitle(
    bvid: str = Query(..., description="B站视频 BV 号"),
    lan: str = Query(..., description="字幕语言标识"),
    format: str = Query("srt", description="输出格式: srt / ass"),
    conn_id: str = Query("", description="平台连接 ID"),
):
    """
    下载B站字幕文件，返回指定格式（SRT/ASS）的文本内容
    """
    try:
        from app.services.platforms import create_client
        cookie = get_raw_cookie(conn_id) if conn_id else ""
        async with create_client("bili", mode="api", cookie=cookie) as client:
            # 1. 获取字幕列表，找到对应语言的 subtitle_url
            subtitles = await client.get_subtitles(bvid)
            target_subtitle = None
            for sub in subtitles:
                sub_lan = sub.get("lan", "")
                if sub_lan == lan:
                    target_subtitle = sub
                    break

            if not target_subtitle:
                raise HTTPException(status_code=404, detail=f"未找到语言为 '{lan}' 的字幕，可用语言: {[s.get('lan') for s in subtitles]}")

            subtitle_url = target_subtitle.get("subtitle_url", "")
            if not subtitle_url:
                raise HTTPException(status_code=404, detail=f"字幕 '{lan}' 没有可用的下载地址")

            # 2. 下载并转换格式
            content = await client.download_subtitle(subtitle_url, format)
            if not content:
                raise HTTPException(status_code=500, detail=f"字幕内容为空或解析失败")

            # 3. 返回文本文件
            from fastapi.responses import Response
            media_type = "text/plain" if format == "srt" else "text/x-ssa"
            ext = format.lower()
            filename = f"{bvid}_{lan}.{ext}"
            return Response(
                content=content,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[bili/subtitle/download] Error: {e}")
        raise HTTPException(status_code=500, detail=f"下载字幕失败: {str(e)}")


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
        cookie = get_raw_cookie(conn_id) if conn_id else ""
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


@router.post("/comment/send", summary="发送B站评论", response_model=BilibiliSendCommentResponse)
async def send_comment(
    request: BilibiliSendCommentRequest,
    conn_id: str = Query("", description="平台连接 ID"),
):
    """
    发送B站视频评论
    """
    try:
        from app.services.platforms import create_client
        cookie = get_raw_cookie(conn_id) if conn_id else ""
        if not cookie:
            raise HTTPException(status_code=400, detail="需要提供有效的平台连接")
        
        csrf = extract_bili_jct(cookie)
        if not csrf:
            raise HTTPException(status_code=400, detail="Cookie 中缺少 bili_jct (CSRF token)")
        
        async with create_client("bili", mode="api", cookie=cookie) as client:
            result = await client.send_comment(
                request.bvid,
                request.message,
                request.parent,
                request.root,
                csrf
            )
            return BilibiliSendCommentResponse(
                success=result.get("success", False),
                rpid=result.get("rpid", 0),
                message=result.get("message", "")
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[bili/comment/send] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
