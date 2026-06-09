"""
B站专属 API 路由

提供 B站 平台的专属功能接口：
- 弹幕获取
- 作品数据统计
- 评论获取
- 字幕获取
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import List, Dict, Optional, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Path
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

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


class BilibiliLoginHealthItem(BaseModel):
    key: str
    label: str
    ok: bool = False
    status: str = "fail"
    message: str = ""
    reason: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class BilibiliLoginHealthResponse(BaseModel):
    success: bool = False
    conn_id: str = ""
    bvid: str = ""
    checked_at: int = 0
    checks: Dict[str, BilibiliLoginHealthItem] = Field(default_factory=dict)
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


class WatchHistoryResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    message: str = ""


class FollowingsResponse(BaseModel):
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
    logger.debug(f"[bili/_get_bili_client] conn_id={conn_id}, cookie len={len(cookie) if cookie else 0}, preview={cookie[:80] if cookie else 'NONE'!r}")
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


def _health_item(
    key: str,
    label: str,
    ok: bool,
    message: str,
    *,
    status: Optional[str] = None,
    reason: str = "",
    data: Optional[Dict[str, Any]] = None,
) -> BilibiliLoginHealthItem:
    return BilibiliLoginHealthItem(
        key=key,
        label=label,
        ok=ok,
        status=status or ("ok" if ok else "fail"),
        message=message,
        reason=reason or ("" if ok else message),
        data=data or {},
    )


def _bili_api_reason(response: Any, fallback: str) -> str:
    if isinstance(response, dict):
        code = response.get("code")
        msg = response.get("message") or response.get("msg") or fallback
        return f"B站返回 code={code}: {msg}"
    return fallback


async def _bili_health_get_view(client: Any, bvid: str) -> tuple[Optional[Dict[str, Any]], str]:
    from urllib.parse import urlencode
    from app.services.platforms.bilibili.apis import BASE_URL

    if not bvid:
        return None, "未提供 BV 号，无法检测需要具体视频的能力"

    view_url = f"{BASE_URL}/x/web-interface/view?{urlencode({'bvid': bvid})}"
    try:
        view_resp = await client.request("GET", view_url)
    except Exception as e:
        return None, f"视频信息接口请求失败: {str(e)}"

    if not (isinstance(view_resp, dict) and view_resp.get("code") == 0):
        return None, _bili_api_reason(view_resp, "视频信息接口返回异常")

    data = view_resp.get("data") or {}
    if not isinstance(data, dict):
        return None, "视频信息接口未返回 data"
    return data, ""


async def _bili_health_check_subtitles(client: Any, view_data: Dict[str, Any]) -> BilibiliLoginHealthItem:
    from app.services.platforms.bilibili.apis import BASE_URL

    aid = view_data.get("aid")
    pages = view_data.get("pages") or []
    cid = pages[0].get("cid") if pages and isinstance(pages[0], dict) else view_data.get("cid")
    if not aid or not cid:
        return _health_item("subtitles", "字幕", False, "无法从视频信息中取得 aid/cid")

    params = {
        "aid": aid,
        "cid": cid,
        "isGaiaAvoided": "false",
        "web_location": "1315873",
        "dm_img_list": "[]",
        "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ==",
        "dm_cover_img_str": "QU5HTEUgKE5WSURJQSk=",
        "dm_img_inter": '{"ds":[],"wh":[1920,1080,24],"of":[0,0,0]}',
    }

    try:
        query_string = await client._sign_params(params)
        player_resp = await client.request("GET", f"{BASE_URL}/x/player/wbi/v2?{query_string}")
    except Exception as e:
        return _health_item("subtitles", "字幕", False, f"字幕接口请求失败: {str(e)}")

    if not (isinstance(player_resp, dict) and player_resp.get("code") == 0):
        return _health_item(
            "subtitles",
            "字幕",
            False,
            _bili_api_reason(player_resp, "字幕接口返回异常"),
        )

    subtitle_info = (player_resp.get("data") or {}).get("subtitle") or {}
    subtitles = subtitle_info.get("subtitles") or []
    count = len(subtitles) if isinstance(subtitles, list) else 0
    return _health_item(
        "subtitles",
        "字幕",
        True,
        f"字幕接口可访问，当前视频字幕 {count} 个" if count else "字幕接口可访问，当前视频暂无字幕",
        data={"count": count},
    )


async def _bili_health_check_comments(client: Any, view_data: Dict[str, Any]) -> BilibiliLoginHealthItem:
    from app.services.platforms.bilibili.apis import BASE_URL

    aid = view_data.get("aid")
    if not aid:
        return _health_item("comments", "评论", False, "无法从视频信息中取得 aid")

    params = {
        "type": 1,
        "oid": aid,
        "mode": 3,
        "pagination_str": '{"offset":""}',
        "ps": 1,
    }

    try:
        query_string = await client._sign_params(params)
        reply_resp = await client.request("GET", f"{BASE_URL}/x/v2/reply/wbi/main?{query_string}")
    except Exception as e:
        return _health_item("comments", "评论", False, f"评论接口请求失败: {str(e)}")

    if not (isinstance(reply_resp, dict) and reply_resp.get("code") == 0):
        return _health_item(
            "comments",
            "评论",
            False,
            _bili_api_reason(reply_resp, "评论接口返回异常"),
        )

    data = reply_resp.get("data") or {}
    cursor = data.get("cursor") or {}
    total = cursor.get("all_count") or cursor.get("all_total") or data.get("total") or 0
    return _health_item(
        "comments",
        "评论",
        True,
        f"评论接口可访问，当前视频评论约 {total} 条",
        data={"total": total},
    )


# =============================================================================
# API 端点
# =============================================================================

@router.get("/login-health", summary="B站登录态体检", response_model=BilibiliLoginHealthResponse)
async def check_login_health(
    conn_id: str = Query("", description="平台连接 ID"),
    bvid: str = Query("", description="可选：用于检测字幕/评论能力的 BV 号"),
):
    """
    一键检查 B站登录态和素材采集相关能力。

    - Cookie / bili_jct：直接检查连接中保存的 Cookie
    - 登录态：调用 B站 nav 接口确认 Cookie 是否仍然有效
    - 字幕 / 评论：需要 BV 号，会对当前视频做只读接口探测
    - 发评论：只做非破坏性检查，不会真实发送评论
    """
    from app.services.platforms import create_client
    from app.services.platforms.bilibili.apis import BASE_URL

    checks: Dict[str, BilibiliLoginHealthItem] = {}

    cookie = get_raw_cookie(conn_id) if conn_id else ""
    checks["cookie"] = _health_item(
        "cookie",
        "Cookie",
        bool(cookie),
        f"已获取 Cookie，长度 {len(cookie)}" if cookie else "未获取到 Cookie，请先选择或重新登录 B站连接",
        data={"length": len(cookie)},
    )

    csrf = extract_bili_jct(cookie)
    checks["bili_jct"] = _health_item(
        "bili_jct",
        "bili_jct",
        bool(csrf),
        "Cookie 中包含 bili_jct" if csrf else "Cookie 中缺少 bili_jct，发评论等需要 CSRF 的接口不可用",
    )

    if not cookie:
        checks["login"] = _health_item("login", "登录态", False, "没有 Cookie，无法确认 B站登录态")
        checks["subtitles"] = _health_item("subtitles", "字幕", False, "没有 Cookie，无法检测字幕接口")
        checks["comments"] = _health_item("comments", "评论", False, "没有 Cookie，无法检测评论接口")
        checks["post_comment"] = _health_item("post_comment", "发评论", False, "没有 Cookie，无法发送评论")
    else:
        view_data: Optional[Dict[str, Any]] = None
        view_error = ""

        async with create_client("bili", mode="api", cookie=cookie) as client:
            try:
                nav_resp = await client.request("GET", f"{BASE_URL}/x/web-interface/nav")
                nav_data = (nav_resp.get("data") or {}) if isinstance(nav_resp, dict) else {}
                is_login = bool(nav_data.get("isLogin"))
                checks["login"] = _health_item(
                    "login",
                    "登录态",
                    is_login,
                    f"B站已识别登录用户：{nav_data.get('uname') or nav_data.get('mid') or '未知账号'}"
                    if is_login else _bili_api_reason(nav_resp, "B站未识别为已登录"),
                    data={
                        "mid": nav_data.get("mid"),
                        "uname": nav_data.get("uname"),
                        "is_login": is_login,
                    },
                )
            except Exception as e:
                checks["login"] = _health_item("login", "登录态", False, f"登录态接口请求失败: {str(e)}")

            if bvid:
                view_data, view_error = await _bili_health_get_view(client, bvid)

            if not bvid:
                checks["subtitles"] = _health_item(
                    "subtitles",
                    "字幕",
                    False,
                    "请打开或勾选一个 B站视频后再检测字幕接口",
                    status="skipped",
                )
                checks["comments"] = _health_item(
                    "comments",
                    "评论",
                    False,
                    "请打开或勾选一个 B站视频后再检测评论接口",
                    status="skipped",
                )
            elif view_error:
                checks["subtitles"] = _health_item("subtitles", "字幕", False, f"无法检测字幕：{view_error}")
                checks["comments"] = _health_item("comments", "评论", False, f"无法检测评论：{view_error}")
            else:
                checks["subtitles"] = await _bili_health_check_subtitles(client, view_data or {})
                checks["comments"] = await _bili_health_check_comments(client, view_data or {})

        if not csrf:
            checks["post_comment"] = _health_item(
                "post_comment",
                "发评论",
                False,
                "缺少 bili_jct，无法发送评论",
            )
        elif not checks.get("login", _health_item("login", "登录态", False, "")).ok:
            checks["post_comment"] = _health_item(
                "post_comment",
                "发评论",
                False,
                "B站未确认登录态，发评论不可用",
            )
        elif not bvid:
            checks["post_comment"] = _health_item(
                "post_comment",
                "发评论",
                False,
                "请打开或勾选一个 B站视频后再检测发评论目标",
                status="skipped",
            )
        elif view_error:
            checks["post_comment"] = _health_item("post_comment", "发评论", False, f"目标视频不可访问：{view_error}")
        else:
            checks["post_comment"] = _health_item(
                "post_comment",
                "发评论",
                True,
                "凭据齐全且目标视频可访问；体检不会实际发送测试评论",
            )

    failed = [item for item in checks.values() if not item.ok and item.status != "skipped"]
    skipped = [item for item in checks.values() if item.status == "skipped"]
    success = not failed and not skipped
    if success:
        message = "B站登录态体检通过"
    elif failed:
        message = f"B站登录态体检发现 {len(failed)} 项问题"
    else:
        message = "Cookie 基础检查通过，视频能力待选择 BV 号后检测"

    return BilibiliLoginHealthResponse(
        success=success,
        conn_id=conn_id,
        bvid=bvid,
        checked_at=int(time.time()),
        checks=checks,
        message=message,
    )


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


@router.get("/up/{uid}/favorites", summary="获取UP主公开收藏夹列表", response_model=FavoriteListResponse)
async def get_up_favorite_list(
    uid: str = Path(..., description="UP主UID"),
    conn_id: str = Query("", description="B站连接ID（可选）"),
):
    """
    获取UP主的公开收藏夹列表
    - 不需要登录也可以获取公开收藏夹
    """
    logger.info(f"[up_favorites] uid={uid}")

    async with bili_client(conn_id) as client:
        try:
            favorites = await client.get_favorite_list(user_id=uid)

            return FavoriteListResponse(
                success=True,
                data=favorites,
                message=f"获取到 {len(favorites)} 个公开收藏夹",
            )

        except Exception as e:
            logger.error(f"[up_favorites] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取收藏夹失败: {str(e)}")


@router.get("/favorites/{media_id}", summary="获取收藏夹详情", response_model=FavoriteDetailResponse)
async def get_favorite_detail(
    media_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页数量"),
    conn_id: str = Query("", description="B站连接ID（可选，公开收藏夹不需要）"),
):
    """
    获取收藏夹内的视频列表
    - 公开收藏夹不需要登录
    - 私有收藏夹需要登录
    """
    logger.info(f"[favorite_detail] media_id={media_id}, page={page}")

    async with bili_client(conn_id) as client:
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


# =============================================================================
# 历史观看记录 - API 端点
# =============================================================================

@router.get("/history", summary="获取历史观看记录（游标浏览）", response_model=WatchHistoryResponse)
async def get_watch_history(
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
    ps: int = Query(20, ge=1, le=50, description="每页数量"),
    max: int = Query(0, description="游标：上一页最后一条记录的 oid（首次请求传0）"),
    view_at: int = Query(0, description="游标：上一页最后一条记录的 view_at 时间戳（首次请求传0）"),
    type: str = Query("all", description="类型（all=全部, archive=视频, live=直播, article=专栏）"),
):
    """
    获取当前登录用户的历史观看记录（游标分页浏览）
    - 必须提供有效的 B站连接（包含 Cookie）
    - 使用游标分页：首次请求 max=0&view_at=0，后续请求使用返回的 cursor 值
    - type 参数可按类型筛选：all/archive/live/article
    """
    logger.info(f"[history] conn_id={conn_id}, ps={ps}, max={max}, view_at={view_at}, type={type}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法访问历史记录")

        try:
            result = await client.get_watch_history(
                max_results=ps,
                max_oid=max,
                view_at=view_at,
                history_type=type,
            )

            return WatchHistoryResponse(
                success=True,
                data=result,
                message=f"获取到 {len(result.get('list', []))} 条记录",
            )

        except Exception as e:
            logger.error(f"[history] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取历史记录失败: {str(e)}")


@router.get("/history/search", summary="搜索历史观看记录（时间筛选）", response_model=WatchHistoryResponse)
async def search_watch_history(
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
    business: str = Query("archive", description="业务类型（archive=视频, live=直播, article=专栏）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页数量"),
    keyword: str = Query("", description="搜索关键词"),
    add_time_start: int = Query(0, description="起始时间戳（秒），0=不限"),
    add_time_end: int = Query(0, description="结束时间戳（秒），0=不限"),
):
    """
    搜索历史观看记录（支持时间筛选和关键词搜索）
    - 必须提供有效的 B站连接（包含 Cookie）
    - 支持按类型（视频/直播/专栏）和时间范围筛选
    - 时间筛选示例：今天=add_time_start=今天0点时间戳, 昨天=start=昨天0点&end=今天0点-1
    """
    logger.info(f"[history_search] conn_id={conn_id}, business={business}, page={page}, keyword={keyword}, start={add_time_start}, end={add_time_end}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法访问历史记录")

        try:
            result = await client.search_watch_history(
                business=business,
                page=page,
                page_size=page_size,
                keyword=keyword,
                add_time_start=add_time_start,
                add_time_end=add_time_end,
            )

            return WatchHistoryResponse(
                success=True,
                data=result,
                message=f"获取到 {len(result.get('list', []))} 条记录",
            )

        except Exception as e:
            logger.error(f"[history_search] Error: {e}")
            raise HTTPException(status_code=500, detail=f"搜索历史记录失败: {str(e)}")


# =============================================================================
# 关注列表 - API 端点
# =============================================================================

@router.get("/followings", summary="获取关注列表", response_model=FollowingsResponse)
async def get_followings(
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
    vmid: int = Query(0, description="用户UID（0=当前登录用户自己）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页数量"),
    order_type: str = Query("desc", description="排序方式（desc=最近关注在前, asc=最早关注在前）"),
):
    """
    获取当前登录用户的关注列表（关注的 UP 主）
    - 必须提供有效的 B站连接（包含 Cookie）
    - vmid=0 表示获取自己的关注列表
    - 支持分页和排序
    """
    logger.info(f"[followings] conn_id={conn_id}, vmid={vmid}, page={page}, page_size={page_size}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法访问关注列表")

        try:
            result = await client.get_followings(
                vmid=vmid,
                page=page,
                page_size=page_size,
                order_type=order_type,
            )

            return FollowingsResponse(
                success=True,
                data=result,
                message=f"获取到 {len(result.get('list', []))} 条关注",
            )

        except Exception as e:
            logger.error(f"[followings] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取关注列表失败: {str(e)}")


# =============================================================================
# 付费课程（芝士课堂）- Response Models
# =============================================================================

class PaidCoursesResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    message: str = ""


class PaidCourseDetailResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    message: str = ""


class PaidCoursePlayurlResponse(BaseModel):
    success: bool = True
    data: Optional[Dict[str, Any]] = None
    message: str = ""


class PaidCourseDownloadTaskRequest(BaseModel):
    conn_id: str
    ep_id: int = 0
    aid: int = 0
    cid: int = 0
    qn: int = 80
    title: str = ""
    episode_index: int = 0
    episodes: List[Dict[str, Any]] = Field(default_factory=list)
    download_extras: bool = True
    season_id: int = 0
    course_title: str = ""
    course_cover: str = ""
    course_desc: str = ""
    course_author: str = ""
    ep_count: int = 0
    update_info: str = ""


_paid_course_download_tasks: dict[str, dict[str, Any]] = {}


def _update_paid_course_task(task_id: str, **updates: Any) -> None:
    task = _paid_course_download_tasks.get(task_id, {})
    task.update(updates)
    task["updated_at"] = time.time()
    _paid_course_download_tasks[task_id] = task


async def _run_paid_course_download_task(task_id: str, req: PaidCourseDownloadTaskRequest) -> None:
    is_full_course = bool(req.episodes)
    _update_paid_course_task(
        task_id,
        status="DOWNLOADING",
        progress=5,
        progress_message="开始下载全课程" if is_full_course else "开始下载",
        total_count=len(req.episodes) if is_full_course else 1,
        finished_count=0,
        skipped_count=0,
    )
    try:
        async with bili_client(req.conn_id) as client:
            if not client.config.cookie:
                raise ValueError("B站连接未包含 Cookie，无法下载付费课程")

            from app.services.download.bilibili_paid_course import (
                download_paid_course_episode as download_course_episode_file,
                download_paid_course_episode_extras,
                register_paid_course_asset,
            )

            def report(progress: int, message: str) -> None:
                _update_paid_course_task(task_id, progress=progress, progress_message=message)

            output_path = None
            skipped_count = 0
            downloaded_count = 0

            if is_full_course:
                total = len(req.episodes)
                for idx, episode in enumerate(req.episodes):
                    ep_id = int(episode.get("ep_id") or episode.get("id") or 0)
                    if not ep_id:
                        continue
                    aid = int(episode.get("aid") or 0)
                    cid = int(episode.get("cid") or 0)

                    episode_index = int(episode.get("episode_index") or episode.get("index") or idx + 1)
                    title = episode.get("download_title") or " - ".join(
                        str(part) for part in [episode.get("section_title"), episode.get("title")] if part
                    )
                    title = title or f"ep_{ep_id}"
                    current_no = idx + 1

                    def episode_report(progress: int, message: str, current_no: int = current_no, title: str = title) -> None:
                        overall = min(98, int(((current_no - 1) + progress / 100) / max(total, 1) * 95) + 3)
                        _update_paid_course_task(
                            task_id,
                            progress=overall,
                            progress_message=f"{current_no}/{total} {title}: {message}",
                            current_episode=title,
                            finished_count=current_no - 1,
                        )

                    output_path = await download_course_episode_file(
                        client=client,
                        ep_id=ep_id,
                        aid=aid,
                        cid=cid,
                        qn=req.qn,
                        title=title,
                        episode_index=episode_index,
                        season_id=req.season_id,
                        course_title=req.course_title,
                        course_cover=req.course_cover,
                        course_desc=req.course_desc,
                        course_author=req.course_author,
                        ep_count=req.ep_count or total,
                        update_info=req.update_info,
                        progress_callback=episode_report,
                    )

                    media_message = _paid_course_download_tasks.get(task_id, {}).get("progress_message", "")
                    if req.download_extras:
                        await download_paid_course_episode_extras(
                            client=client,
                            ep_id=ep_id,
                            aid=aid,
                            cid=cid,
                            title=title,
                            episode_index=episode_index,
                            season_id=req.season_id,
                            course_title=req.course_title,
                            course_cover=req.course_cover,
                            course_desc=req.course_desc,
                            course_author=req.course_author,
                            ep_count=req.ep_count or total,
                            update_info=req.update_info,
                            progress_callback=episode_report,
                        )

                    if "已跳过" in media_message:
                        skipped_count += 1
                    else:
                        downloaded_count += 1

                    _update_paid_course_task(
                        task_id,
                        finished_count=current_no,
                        skipped_count=skipped_count,
                        downloaded_count=downloaded_count,
                    )
                    if current_no < total:
                        await asyncio.sleep(1.5)
            else:
                if not req.ep_id:
                    raise ValueError("需要提供章节ID")

                output_path = await download_course_episode_file(
                    client=client,
                    ep_id=req.ep_id,
                    aid=req.aid,
                    cid=req.cid,
                    qn=req.qn,
                    title=req.title,
                    episode_index=req.episode_index,
                    season_id=req.season_id,
                    course_title=req.course_title,
                    course_cover=req.course_cover,
                    course_desc=req.course_desc,
                    course_author=req.course_author,
                    ep_count=req.ep_count,
                    update_info=req.update_info,
                    progress_callback=report,
                )
                if req.download_extras:
                    await download_paid_course_episode_extras(
                        client=client,
                        ep_id=req.ep_id,
                        aid=req.aid,
                        cid=req.cid,
                        title=req.title,
                        episode_index=req.episode_index,
                        season_id=req.season_id,
                        course_title=req.course_title,
                        course_cover=req.course_cover,
                        course_desc=req.course_desc,
                        course_author=req.course_author,
                        ep_count=req.ep_count,
                        update_info=req.update_info,
                        progress_callback=report,
                    )
            asset_id = await register_paid_course_asset(
                season_id=req.season_id,
                course_title=req.course_title,
                course_cover=req.course_cover,
                course_desc=req.course_desc,
                course_author=req.course_author,
                ep_count=req.ep_count,
                update_info=req.update_info,
            )
            _update_paid_course_task(
                task_id,
                status="DONE",
                progress=100,
                progress_message=(
                    f"全课程补全完成，新增视频 {downloaded_count} 个，跳过视频 {skipped_count} 个，已更新素材库"
                    if is_full_course else "下载完成，已加入素材库"
                ),
                file_path=str(output_path) if output_path else "",
                asset_id=asset_id,
                completed_at=time.time(),
            )
    except Exception as e:
        logger.error(f"[paid_course_download_task] Error: {e}", exc_info=True)
        _update_paid_course_task(
            task_id,
            status="FAILED",
            progress_message=f"下载失败: {str(e)[:80]}",
            error=str(e),
            completed_at=time.time(),
        )


# =============================================================================
# 付费课程（芝士课堂）- API 端点
# =============================================================================

@router.get("/paid-courses", summary="获取付费课程列表", response_model=PaidCoursesResponse)
async def get_paid_courses(
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
):
    """
    获取当前登录用户购买的付费课程列表（芝士课堂）
    - 必须提供有效的 B站连接（包含 Cookie）
    - 支持分页
    """
    logger.info(f"[paid_courses] conn_id={conn_id}, page={page}, page_size={page_size}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法访问付费课程")

        try:
            result = await client.get_paid_courses(
                page=page,
                page_size=page_size,
            )

            return PaidCoursesResponse(
                success=True,
                data=result,
                message=f"获取到 {len(result.get('list', []))} 门付费课程",
            )

        except Exception as e:
            logger.error(f"[paid_courses] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取付费课程失败: {str(e)}")


@router.get("/paid-course/detail", summary="获取付费课程详情和章节列表", response_model=PaidCourseDetailResponse)
async def get_paid_course_detail(
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
    season_id: int = Query(..., description="课程ID（season_id）"),
    pay_gid: int = Query(0, description="支付订单ID（备用）"),
):
    """
    获取付费课程的详细信息和章节列表
    - 必须提供有效的 B站连接（包含 Cookie）
    """
    logger.info(f"[paid_course_detail] conn_id={conn_id}, season_id={season_id}, pay_gid={pay_gid}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法访问付费课程")

        try:
            # 先尝试使用 season_id
            result = await client.get_paid_course_detail(season_id=season_id)
            
            # 如果没有获取到章节，尝试使用 pay_gid
            if not result.get("episodes") and pay_gid:
                logger.info(f"[paid_course_detail] No episodes with season_id, trying pay_gid={pay_gid}")
                result = await client.get_paid_course_detail(season_id=pay_gid)

            return PaidCourseDetailResponse(
                success=True,
                data=result,
                message=f"获取课程详情成功",
            )

        except Exception as e:
            logger.error(f"[paid_course_detail] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取课程详情失败: {str(e)}")


@router.get("/paid-course/playurl", summary="获取付费课程视频播放地址", response_model=PaidCoursePlayurlResponse)
async def get_paid_course_playurl(
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
    ep_id: int = Query(..., description="章节ID（ep_id）"),
    qn: int = Query(80, description="画质质量（80=高清1080P, 64=高清720P, 32=清晰480P, 16=流畅360P）"),
):
    """
    获取付费课程视频的播放地址（用于下载）
    - 必须提供有效的 B站连接（包含 Cookie）
    - 需要用户已购买该课程
    """
    logger.info(f"[paid_course_playurl] conn_id={conn_id}, ep_id={ep_id}, qn={qn}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法获取播放地址")

        try:
            result = await client.get_paid_course_playurl(ep_id=ep_id, qn=qn)

            return PaidCoursePlayurlResponse(
                success=True,
                data=result,
                message="获取播放地址成功",
            )

        except Exception as e:
            logger.error(f"[paid_course_playurl] Error: {e}")
            raise HTTPException(status_code=500, detail=f"获取播放地址失败: {str(e)}")


@router.post("/paid-course/download-task", summary="创建付费课程章节下载任务")
async def create_paid_course_download_task(
    req: PaidCourseDownloadTaskRequest,
    background: BackgroundTasks,
):
    if not req.conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")
    if not req.ep_id and not req.episodes:
        raise HTTPException(status_code=400, detail="需要提供章节ID（ep_id）或章节列表（episodes）")

    task_id = uuid.uuid4().hex[:12]
    is_full_course = bool(req.episodes)
    _paid_course_download_tasks[task_id] = {
        "task_id": task_id,
        "task_type": "bilibili_paid_course_full_download" if is_full_course else "bilibili_paid_course_download",
        "status": "PENDING",
        "progress": 0,
        "progress_message": "等待下载全课程" if is_full_course else "等待下载",
        "file_path": "",
        "asset_id": "",
        "error": "",
        "total_count": len(req.episodes) if is_full_course else 1,
        "finished_count": 0,
        "skipped_count": 0,
        "downloaded_count": 0,
        "created_at": time.time(),
        "updated_at": time.time(),
        "completed_at": None,
    }
    background.add_task(_run_paid_course_download_task, task_id, req)
    return {
        "success": True,
        "task_id": task_id,
        "status": "PENDING",
        "progress": 0,
        "progress_message": "等待下载全课程" if is_full_course else "等待下载",
        "total_count": len(req.episodes) if is_full_course else 1,
    }


@router.get("/paid-course/download-task/{task_id}", summary="查询付费课程章节下载任务")
async def get_paid_course_download_task(task_id: str):
    task = _paid_course_download_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "success": True,
        **task,
    }


@router.get("/paid-course/download", summary="下载付费课程章节")
async def download_paid_course_episode(
    conn_id: str = Query(..., description="B站连接ID（必填，需要登录）"),
    ep_id: int = Query(..., description="章节ID（ep_id）"),
    qn: int = Query(80, description="画质质量（80=高清1080P, 64=高清720P, 32=清晰480P, 16=流畅360P）"),
    title: str = Query("", description="下载文件名"),
    episode_index: int = Query(0, description="章节序号"),
    season_id: int = Query(0, description="课程ID（season_id）"),
    course_title: str = Query("", description="课程标题"),
    course_cover: str = Query("", description="课程封面 URL"),
):
    """
    后端代理下载付费课程章节，避免浏览器直连 B站 CDN 时缺 Cookie/Referer。
    DASH 音视频分离流会先下载再用 ffmpeg 合并为 MP4。
    """
    logger.info(f"[paid_course_download] conn_id={conn_id}, ep_id={ep_id}, qn={qn}")

    if not conn_id:
        raise HTTPException(status_code=400, detail="需要提供 B站连接ID（conn_id）")

    async with bili_client(conn_id) as client:
        if not client.config.cookie:
            raise HTTPException(status_code=401, detail="B站连接未包含 Cookie，无法下载付费课程")

        try:
            from app.services.download.bilibili_paid_course import (
                download_paid_course_episode as download_course_episode_file,
            )

            output_path = await download_course_episode_file(
                client=client,
                ep_id=ep_id,
                qn=qn,
                title=title,
                episode_index=episode_index,
                season_id=season_id,
                course_title=course_title,
                course_cover=course_cover,
            )

            return FileResponse(
                path=output_path,
                media_type="video/mp4",
                filename=output_path.name,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[paid_course_download] Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"下载付费课程失败: {str(e)}")
