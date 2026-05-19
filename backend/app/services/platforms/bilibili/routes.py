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
from typing import List, Dict, Optional, Any

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
# UP主分析 & 个人中心 - Response Models
# =============================================================================

class UpProfileResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    message: str = ""


class UpVideosResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    message: str = ""


class FavoriteListResponse(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]] = []
    message: str = ""


class FavoriteDetailResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    message: str = ""


class SeriesListResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    message: str = ""


# =============================================================================
# UP主分析 & 个人中心 - 辅助函数
# =============================================================================

async def _get_bili_client(conn_id: str = "") -> "BilibiliClient":
    """获取 B站客户端实例（内部初始化 http client）"""
    from app.services.platforms.types import ClientConfig, ClientMode

    cookie = get_raw_cookie(conn_id) if conn_id else ""
    config = ClientConfig(
        platform="bili",
        mode=ClientMode.API,
        cookie=cookie,
    )
    from app.services.platforms.bilibili.client import BilibiliClient
    client = BilibiliClient(config)
    await client._init_http_client()
    return client


class BilibiliClientContext:
    """B站客户端上下文管理器，自动关闭资源"""

    def __init__(self, conn_id: str = ""):
        self.conn_id = conn_id
        self.client = None

    async def __aenter__(self) -> "BilibiliClient":
        self.client = await _get_bili_client(self.conn_id)
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client and self.client._http_client:
            await self.client._http_client.aclose()
        return False


def bili_client(conn_id: str = ""):
    """创建 B站客户端上下文管理器"""
    return BilibiliClientContext(conn_id)


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


# =============================================================================
# UP主分析 & 个人中心 - API 端点
# =============================================================================

@router.get("/up/profile", summary="获取UP主信息", response_model=UpProfileResponse)
async def get_up_profile(
    uid: str = Query(..., description="UP主 UID"),
    conn_id: str = Query("", description="B站连接ID（可选，用于需要登录的接口）"),
):
    """
    获取UP主的基本信息
    - uid: UP主的数字ID（不是用户名）
    """
    logger.info(f"[up_profile] uid={uid}")

    async with bili_client(conn_id) as client:
        try:
            profile = await client.get_user_profile(uid)

            if not profile.name:
                return UpProfileResponse(
                    success=False,
                    data=None,
                    message="UP主不存在或获取失败",
                )

            card = profile.raw_data.get("card", {}) if profile.raw_data else {}
            level_info = card.get("level_info", {}) or {}
            vip_info = card.get("vip", {}) or {}

            return UpProfileResponse(
                success=True,
                data={
                    "uid": profile.id,
                    "name": profile.name,
                    "avatar": profile.avatar,
                    "sign": profile.desc,
                    "fans": profile.followers,
                    "following": profile.following,
                    "likes": profile.total_likes,
                    "archive_count": card.get("archive_count") or profile.total_videos or 0,
                    "article_count": card.get("article_count", 0),
                    "level": level_info.get("current_level", 0),
                    "vip_status": vip_info.get("status", 0),
                    "vip_label": vip_info.get("label", {}).get("text", ""),
                    "official_verify": card.get("official_verify", {}),
                    "sex": card.get("sex", ""),
                    "fans_badge": card.get("fans_badge", False),
                    "raw_data": profile.raw_data,
                },
                message="获取成功",
            )

        except Exception as e:
            logger.error(f"[up_profile] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取UP主信息失败: {str(e)}")


@router.get("/up/videos", summary="获取UP主视频列表", response_model=UpVideosResponse)
async def get_up_videos(
    uid: str = Query(..., description="UP主 UID"),
    order: str = Query("pubdate", description="排序: pubdate/shadow/stow/click"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页数量"),
    conn_id: str = Query("", description="B站连接ID"),
):
    """
    获取UP主发布的视频列表
    - order: pubdate(最新)/shadows(最多收藏)/stow(最近收藏)/click(最多播放)
    """
    logger.info(f"[up_videos] uid={uid}, order={order}, page={page}")

    async with bili_client(conn_id) as client:
        try:
            videos_data = await client.get_user_videos(uid, max_results=page_size, order=order, page=page)
            videos = videos_data.get("list", [])
            total_count = videos_data.get("total", len(videos))

            result = []
            for v in videos:
                result.append({
                    "bvid": v.id,
                    "title": v.title,
                    "desc": v.desc,
                    "cover": v.cover,
                    "author": v.author,
                    "author_id": v.author_id,
                    "url": v.url,
                    "duration": v.duration,
                    "pubdate": v.create_time,
                    "stat": {
                        "view": v.views,
                        "like": v.likes,
                        "coin": v.coins,
                        "favorite": v.collects,
                        "reply": v.comments,
                        "share": v.shares,
                    },
                    "raw_data": v.raw_data,
                })

            return UpVideosResponse(
                success=True,
                data={
                    "list": result,
                    "total": total_count,
                    "page": page,
                    "page_size": page_size,
                },
                message=f"获取到 {len(result)} 个视频",
            )

        except Exception as e:
            logger.error(f"[up_videos] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取UP主视频失败: {str(e)}")


@router.get("/up/series", summary="获取UP主合集列表", response_model=SeriesListResponse)
async def get_up_series(
    uid: str = Query(..., description="UP主 UID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页数量"),
    conn_id: str = Query("", description="B站连接ID"),
):
    """
    获取UP主的合集列表
    """
    logger.info(f"[up_series] uid={uid}, page={page}")

    async with bili_client(conn_id) as client:
        try:
            result = await client.get_user_series_list(uid, page=page, page_size=page_size)

            return SeriesListResponse(
                success=True,
                data=result,
                message=f"获取到 {len(result.get('list', []))} 个合集",
            )

        except Exception as e:
            logger.error(f"[up_series] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取UP主合集失败: {str(e)}")


@router.get("/up/ranking", summary="获取UP主热门视频排行", response_model=UpVideosResponse)
async def get_up_ranking(
    uid: str = Query(..., description="UP主 UID"),
    limit: int = Query(10, ge=1, le=30, description="返回数量"),
    conn_id: str = Query("", description="B站连接ID"),
):
    """
    获取UP主的热门视频排行（按播放量排序）
    """
    logger.info(f"[up_ranking] uid={uid}, limit={limit}")

    async with bili_client(conn_id) as client:
        try:
            videos_data = await client.get_user_videos(uid, max_results=limit, order="click", page=1)
            videos = videos_data.get("list", [])

            sorted_videos = sorted(videos, key=lambda x: x.views or 0, reverse=True)

            result = []
            for i, v in enumerate(sorted_videos[:limit], 1):
                result.append({
                    "rank": i,
                    "bvid": v.id,
                    "title": v.title,
                    "cover": v.cover,
                    "url": v.url,
                    "duration": v.duration,
                    "pubdate": v.create_time,
                    "stat": {
                        "view": v.views,
                        "like": v.likes,
                        "coin": v.coins,
                        "favorite": v.collects,
                        "reply": v.comments,
                    },
                })

            return UpVideosResponse(
                success=True,
                data={
                    "list": result,
                    "total": len(result),
                },
                message=f"获取到 {len(result)} 个热门视频",
            )

        except Exception as e:
            logger.error(f"[up_ranking] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取热门视频失败: {str(e)}")


@router.get("/favorites", summary="获取我的收藏夹列表", response_model=FavoriteListResponse)
async def get_favorite_list(
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
):
    """
    获取当前登录用户的收藏夹列表
    - 必须提供有效的 B站连接（包含 Cookie）
    """
    logger.info(f"[favorites] conn_id={conn_id}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法访问收藏夹")

        try:
            favorites = await client.get_favorite_list()

            return FavoriteListResponse(
                success=True,
                data=favorites,
                message=f"获取到 {len(favorites)} 个收藏夹",
            )

        except Exception as e:
            logger.error(f"[favorites] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取收藏夹失败: {str(e)}")


@router.get("/favorites/{media_id}", summary="获取收藏夹详情", response_model=FavoriteDetailResponse)
async def get_favorite_detail(
    media_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页数量"),
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
):
    """
    获取收藏夹内的视频列表
    - 必须提供有效的 B站连接（包含 Cookie）
    """
    logger.info(f"[favorite_detail] media_id={media_id}, page={page}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法访问收藏夹")

        try:
            result = await client.get_favorite_detail(media_id, page=page, page_size=page_size)

            return FavoriteDetailResponse(
                success=True,
                data=result,
                message=f"获取到 {len(result.get('list', []))} 个视频",
            )

        except Exception as e:
            logger.error(f"[favorite_detail] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取收藏夹详情失败: {str(e)}")


@router.get("/series/{series_id}", summary="获取合集详情", response_model=SeriesListResponse)
async def get_series_detail(
    series_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页数量"),
    conn_id: str = Query("", description="B站连接ID"),
):
    """
    获取合集内的视频列表
    """
    logger.info(f"[series_detail] series_id={series_id}, page={page}")

    async with bili_client(conn_id) as client:
        try:
            series = await client.get_series(series_id)

            videos = []
            for i, bvid in enumerate(series.video_ids[:page_size], 0):
                if (i // page_size) + 1 != page:
                    continue
                try:
                    info = await client.get_video_info(bvid)
                    if info:
                        videos.append({
                            "bvid": bvid,
                            "title": info.get("title", ""),
                            "desc": info.get("desc", ""),
                            "cover": client._fix_bili_url(info.get("pic", "")),
                            "author": info.get("owner", {}).get("name", ""),
                            "author_id": str(info.get("owner", {}).get("mid", "")),
                            "url": f"https://www.bilibili.com/video/{bvid}",
                            "duration": info.get("duration", 0),
                            "pubdate": info.get("pubdate", 0),
                            "stat": info.get("stat", {}),
                        })
                except Exception as e:
                    logger.warning(f"[series] Failed to get video {bvid}: {e}")

            return SeriesListResponse(
                success=True,
                data={
                    "id": series.id,
                    "title": series.title,
                    "cover": series.cover,
                    "author": series.author,
                    "author_id": series.author_id,
                    "total_videos": series.total_videos,
                    "videos": videos,
                    "page": page,
                    "page_size": page_size,
                    "raw_data": series.raw_data,
                },
                message=f"获取到合集: {series.title}",
            )

        except Exception as e:
            logger.error(f"[series_detail] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取合集详情失败: {str(e)}")
