"""
B站专属接口（字幕、弹幕、评论、视频投稿等 B站特有功能）

功能列表：
- 弹幕获取
- 评论管理（获取/发送）
- 视频信息获取
- 视频搜索
- 视频上传（投稿预检查 + 分片上传）
- 专栏发布
- 动态发布
- 作品数据统计
- 素材采集（视频搜索+下载+字幕）
- 字幕下载（已有）
"""
from typing import List, Dict, Optional, Any

from fastapi import APIRouter, HTTPException, Query, Depends, Form, UploadFile, File as FastAPIFile, Body
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
from sqlmodel import Session

import httpx
from app.db.database import get_session
from app.services.platform_connection import PlatformConnectionService

router = APIRouter()
logger = __import__("logging").getLogger("ylcraft.api.bilibili")

# =============================================================================
# B站 API 基础配置
# =============================================================================

BILI_API = "https://api.bilibili.com"
BILI_MEMBER = "https://member.bilibili.com"


# =============================================================================
# 响应模型
# =============================================================================

class BaseResponse(BaseModel):
    success: bool = True
    data: List[Dict] = []
    message: str = ""


class SubtitleListResponse(BaseModel):
    """字幕列表响应"""
    success: bool
    data: List[Dict] = []
    message: str = ""


class VideoInfoResponse(BaseModel):
    """视频信息响应"""
    success: bool
    data: Dict = {}
    message: str = ""


class CommentListResponse(BaseModel):
    """评论列表响应"""
    success: bool
    data: Dict = {}
    message: str = ""


class SearchResponse(BaseModel):
    """搜索结果响应"""
    success: bool
    data: Dict = {}
    message: str = ""


class PublishResultResponse(BaseModel):
    """发布结果响应"""
    success: bool
    data: Dict = {}
    message: str = ""


# =============================================================================
# Cookie 辅助函数
# =============================================================================

def get_bili_cookie(session, conn_id: str = "") -> str:
    cookie = ""
    if conn_id:
        try:
            service = PlatformConnectionService(session)
            conn = service.get(conn_id)
            if conn and conn.cookie_content:
                cookie = conn.cookie_content
        except Exception as e:
            logger.warning(f"Failed to get cookie from connection: {e}")
    return cookie


def get_headers(cookie: str = "") -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
        **({"Cookie": cookie} if cookie else {}),
    }


async def get_csrf_from_cookie(session, conn_id: str) -> str:
    cookie = get_bili_cookie(session, conn_id)
    for item in cookie.split(";"):
        item = item.strip()
        if item.startswith("bili_jct="):
            return item.split("=")[1]
    return ""


# ======================================================================================================================================
# 1️⃣ 弹幕获取
# ======================================================================================================================================

@router.get("/danmaku", summary="获取弹幕", response_model=BaseResponse)
async def get_danmaku(
    bvid: str = Query(..., description="B站视频 BV 号"),
    cid: int = Query(0, description="分P ID，多P视频必填"),
    session: Session = Depends(get_session),
):
    """获取视频弹幕列表（XML 格式）"""
    try:
        # 先获取视频详情拿到 cid
        async with httpx.AsyncClient(timeout=30) as client:
            view_resp = await client.get(
                f"{BILI_API}/x/web-interface/view",
                params={"bvid": bvid},
                headers=get_headers(),
            )
            view_data = view_resp.json()
            if view_data.get("code") != 0:
                raise HTTPException(status_code=400, detail=f"视频不存在或接口错误: {view_data.get('message')}")

            pages = view_data["data"].get("pages", [])
            target_cid = cid or (pages[0]["cid"] if pages else None)
            if not target_cid:
                return {"success": False, "data": [], "message": "无法获取 cid"}

        # 获取弹幕
        async with httpx.AsyncClient(timeout=30) as client:
            danmaku_url = f"{BILI_API}/x/v1/dm/list.so"
            resp = await client.get(danmaku_url, params={"oid": target_cid}, headers=get_headers())
            if resp.status_code == 200 and resp.content:
                import re
                xml_text = resp.text
                # 解析 XML 弹幕
                pattern = r'<d p="([^"]+)">([^<]+)</d>'
                matches = re.findall(pattern, xml_text)
                danmaku_list = []
                for p, text in matches:
                    parts = p.split(",")
                    if len(parts) >= 8:
                        danmaku_list.append({
                            "time": float(parts[0]),
                            "type": int(parts[1]),
                            "font_size": int(parts[2]),
                            "color": parts[3],
                            "timestamp": parts[4],
                            "pool": int(parts[5]),
                            "user_id": parts[6],
                            "dmid": parts[7],
                            "text": text,
                        })
                return {
                    "success": True,
                    "data": danmaku_list,
                    "message": f"共 {len(danmaku_list)} 条弹幕",
                }

        return {"success": False, "data": [], "message": "弹幕内容为空"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_danmaku] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取弹幕失败: {str(e)}")


@router.get("/danmaku/download", summary="下载弹幕文件")
async def download_danmaku(
    bvid: str = Query(..., description="B站视频 BV 号"),
    format: str = Query("json", description="格式: json / ass"),
    session: Session = Depends(get_session),
):
    """下载弹幕文件"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            view_resp = await client.get(
                f"{BILI_API}/x/web-interface/view",
                params={"bvid": bvid},
                headers=get_headers(),
            )
            view_data = view_resp.json()
            pages = view_data["data"].get("pages", [])
            target_cid = pages[0]["cid"] if pages else 0
            if not target_cid:
                raise HTTPException(status_code=404, detail="无法获取 cid")

            danmaku_url = f"{BILI_API}/x/v1/dm/list.so"
            resp = await client.get(danmaku_url, params={"oid": target_cid}, headers=get_headers())

            if format == "ass":
                import re
                matches = re.findall(r'<d p="([^"]+)">([^<]+)</d>', resp.text or "")
                lines = ["[Script Info]", "Title: Danmaku ASS", "ScriptType: v4.00+", "",
                         "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                         "Style: Default,Sans,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1",
                         "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
                for p, text in matches:
                    parts = p.split(",")
                    t = float(parts[0])
                    h = int(t // 3600)
                    m = int((t % 3600) // 60)
                    s = t % 60
                    lines.append(f'Dialogue: 0,{h}:{m:02d}:{s:06.3f},{h}:{m:02d}:{s+5:06.3f},Default,,0,0,0,,{text}')
                content = "\n".join(lines)
                ct = "text/x-ass; charset=utf-8"
            elif format == "json":
                import re
                matches = re.findall(r'<d p="([^"]+)">([^<]+)</d>', resp.text or "")
                result = []
                for p, text in matches:
                    parts = p.split(",")
                    if len(parts) >= 8:
                        result.append({"time": float(parts[0]), "text": text})
                import json
                content = json.dumps(result, ensure_ascii=False, indent=2)
                ct = "application/json; charset=utf-8"
            else:
                content = resp.text or ""
                ct = "text/xml"

            filename = f"{bvid}_danmaku.{format}"
            return PlainTextResponse(
                content=content,
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "Content-Type": ct,
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[download_danmaku] Error: {e}")
        raise HTTPException(status_code=500, detail=f"下载弹幕失败: {str(e)}")


# ======================================================================================================================================
# 2️⃣ 视频投稿（预检查 / 分片上传 / 提交）
# ======================================================================================================================================

@router.post("/video/precheck", summary="视频投稿预检查")
async def video_precheck(
    title: str = Form(...),
    filename: str = Form(...),
    file_size: int = Form(...),
    conn_id: str = Form(default=""),
    session: Session = Depends(get_session),
):
    """
    视频投稿第一步：预上传检查，返回上传地址和 auth_code。

    调用流程：
      1. POST precheck → 拿到 upload_url + auth_code
      2. PUT upload_url → 上传视频文件
      3. POST submit → 提交投稿信息
    """
    csrf = await get_csrf_from_cookie(session, conn_id)
    cookie = get_bili_cookie(session, conn_id)

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://member.bilibili.com/",
        **({"Cookie": cookie} if cookie else {}),
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BILI_MEMBER}/x/web-front/upload/video/preupload",
                data={"name": filename, "size": file_size, "title": title[:80], "csrf": csrf},
                headers=headers,
            )
            data = resp.json()
            if data.get("code") == 0:
                info = data["data"]
                return {"success": True, "data": info}
            return {"success": False, "data": {}, "message": data.get("message", "预上传失败")}
    except Exception as e:
        logger.error(f"[video_precheck] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/video/upload/{auth_code}", summary="上传视频文件")
async def video_upload(
    auth_code: str,
    file: UploadFile = FastAPIFile(...),
    upload_url: str = Query(...),
    conn_id: str = Query(default=""),
):
    """视频投稿第二步：分片上传视频文件"""
    cookie = get_bili_cookie(None, conn_id)

    headers = {
        "User-Agent": "Mozilla/5.0",
        "X-Auth-Code": auth_code,
        "Content-Type": "application/octet-stream",
        **({"Cookie": cookie} if cookie else {}),
    }
    try:
        content = await file.read()
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.put(upload_url, content=content, headers=headers)
            if resp.status_code in [200, 201]:
                return {"success": True, "data": {}, "message": "上传成功"}
            return {"success": False, "data": {}, "message": f"上传失败: {resp.status_code}"}
    except Exception as e:
        logger.error(f"[video_upload] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class VideoSubmitBody(BaseModel):
    title: str
    desc: str = ""
    tags: List[str] = []
    tid: int = 0          # 分区 ID
    copyright: int = 1    # 1=自制 2=转载
    source: str = ""      # 转载来源
    cover: str = ""       # 封面图 URL


@router.post("/video/submit", summary="提交视频投稿信息")
async def video_submit(body: VideoSubmitBody, conn_id: str = Query(""), session: Session = Depends(get_session)):
    """视频投稿第三步：提交投稿元信息"""
    csrf = await get_csrf_from_cookie(session, conn_id)
    cookie = get_bili_cookie(session, conn_id)

    payload = body.dict(exclude_none=True)
    payload["tag"] = ",".join(body.tags[:12]) if body.tags else ""
    payload["csrf"] = csrf

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://member.bilibili.com/",
        **({"Cookie": cookie} if cookie else {}),
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BILI_MEMBER}/x/web-front/submit/video",
                json=payload,
                headers=headers,
            )
            data = resp.json()
            if data.get("code") == 0:
                aid = data.get("data", {}).get("aid", "")
                return {
                    "success": True,
                    "data": {"aid": aid, "url": f"https://www.bilibili.com/video/av{aid}" if aid else ""},
                    "message": "投稿成功",
                }
            return {"success": False, "data": {}, "message": data.get("message", "投稿失败")}
    except Exception as e:
        logger.error(f"[video_submit] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================================================================================
# 3️⃣ 专栏发布
# ======================================================================================================================================

class ArticleSubmitBody(BaseModel):
    title: str
    content: str       # Markdown 正文
    summary: str = ""   # 摘要
    tags: List[str] = []
    category: int = 0   # 分区
    image_urls: List[str] = []


@router.post("/article/publish", summary="发布专栏文章")
async def article_publish(body: ArticleSubmitBody, conn_id: str = Query(""), session: Session = Depends(get_session)):
    """发布 B站专栏文章"""
    csrf = await get_csrf_from_cookie(session, conn_id)
    cookie = get_bili_cookie(session, conn_id)

    payload = {
        "title": body.title[:80],
        "content": body.content,
        "summary": body.summary[:200],
        "tags": ",".join(body.tags[:10]) if body.tags else "",
        "category": body.category,
        "csrf": csrf,
        "image_urls": ",".join(body.image_urls) if body.image_urls else "",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://member.bilibili.com/",
        **({"Cookie": cookie} if cookie else {}),
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BILI_MEMBER}/x/web-front/creative/article",
                json=payload,
                headers=headers,
            )
            data = resp.json()
            if data.get("code") == 0:
                cv_id = data.get("data", {}).get("id", "")
                return {
                    "success": True,
                    "data": {"cv_id": cv_id, "url": f"https://www.bilibili.com/read/cv{cv_id}" if cv_id else ""},
                    "message": "专栏发布成功",
                }
            return {"success": False, "data": {}, "message": data.get("message", "专栏发布失败")}
    except Exception as e:
        logger.error(f"[article_publish] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================================================================================
# 4️⃣ 动态发布
# ======================================================================================================================================

class DynamicSubmitBody(BaseModel):
    content: str              # 动态正文
    images: List[str] = []     # 图片 URL 列表（最多9张）
    type: int = 4             # 4=文字动态 8=转发动态


@router.post("/dynamic/publish", summary="发布动态")
async def dynamic_publish(body: DynamicSubmitBody, conn_id: str = Query(""), session: Session = Depends(get_session)):
    """发布 B站动态"""
    csrf = await get_csrf_from_cookie(session, conn_id)
    cookie = get_bili_cookie(session, conn_id)

    payload = {
        "type": body.type,
        "content": body.content,
        "csrf": csrf,
        "at_uids": "",
        "ctrl": "",
        "scene": "",
        "like": False,
        "repost": False,
    }
    if body.images:
        import json
        payload["pictures"] = json.dumps([{"img_src": url} for url in body.images[:9]])

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://t.bilibili.com/",
        **({"Cookie": cookie} if cookie else {}),
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BILI_API}/x/polymer/web-dynamic/v1/post",
                data=payload,
                headers=headers,
            )
            data = resp.json()
            if data.get("code") == 0:
                dynamic_id = data.get("data", {}).get("dynamic_id", "")
                return {
                    "success": True,
                    "data": {"dynamic_id": dynamic_id},
                    "message": "动态发布成功",
                }
            return {"success": False, "data": {}, "message": data.get("message", "动态发布失败")}
    except Exception as e:
        logger.error(f"[dynamic_publish] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================================================================================
# 5️⃣ 作品数据统计
# ======================================================================================================================================

@router.get("/stats", summary="获取作品数据", response_model=BaseResponse)
async def get_stats(
    bvid: Optional[str] = Query("", description="BV 号"),
    aid: Optional[int] = Query(0, description="AV 号"),
    session: Session = Depends(get_session),
):
    """
    获取视频作品数据（播放量/点赞/投币/收藏/评论/分享/弹幕数）。
    需要传入 bvid 或 aid 其中之一。
    """
    try:
        if not bvid and not aid:
            raise HTTPException(status_code=400, detail="必须提供 bvid 或 aid")

        params = {}
        if bvid:
            params["bvid"] = bvid
        if aid:
            params["aid"] = aid

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BILI_API}/x/web-interface/view",
                params=params,
                headers=get_headers(get_bili_cookie(session)),
            )
            data = resp.json()

            if data.get("code") != 0:
                raise HTTPException(status_code=404, detail=data.get("message", "视频不存在"))

            info = data["data"]
            stat = info.get("stat", {})
            owner = info.get("owner", {})

            return {
                "success": True,
                "data": [{
                    "bvid": info.get("bvid", ""),
                    "aid": info.get("aid", ""),
                    "title": info.get("title", ""),
                    "description": info.get("desc", "")[:200],
                    "owner_name": owner.get("name", ""),
                    "owner_mid": owner.get("mid", ""),
                    "duration_seconds": info.get("duration", 0),
                    "pubdate": info.get("pubdate", 0),
                    "stat": {
                        "view": stat.get("view", 0),         # 播放量
                        "like": stat.get("like", 0),         # 点赞数
                        "coin": stat.get("coin", 0),         # 投币数
                        "favorite": stat.get("favorite", 0), # 收藏数
                        "reply": stat.get("reply", 0),       # 评论数
                        "share": stat.get("share", 0),       # 分享数
                        "danmaku": stat.get("danmaku", 0),   # 弹幕数
                    },
                }],
                "message": "",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_stats] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================================================================================
# 6️⃣ 评论管理
# ======================================================================================================================================

@router.get("/comments", summary="获取评论列表", response_model=CommentListResponse)
async def get_comments(
    bvid: str = Query(..., description="BV 号"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页条数"),
    sort: int = Query(0, description="排序: 0=最热 1=最新 2=最早"),
    session: Session = Depends(get_session),
):
    """获取视频评论列表（支持热评/最新/最早排序）"""
    try:
        # 先拿 cid
        async with httpx.AsyncClient(timeout=15) as client:
            view_resp = await client.get(
                f"{BILI_API}/x/web-interface/view",
                params={"bvid": bvid},
                headers=get_headers(get_bili_cookie(session)),
            )
            view_data = view_resp.json()
            if view_data.get("code") != 0:
                raise HTTPException(status_code=404, detail=view_data.get("message", "视频不存在"))

            pages = view_data["data"].get("pages", [])
            target_cid = pages[0]["cid"] if pages else 0

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BILI_API}/x/v2/reply/main",
                params={
                    "type": 1,
                    "oid": target_cid,
                    "pn": page,
                    "ps": page_size,
                    "sort": sort,
                },
                headers=get_headers(get_bili_cookie(session)),
            )
            data = resp.json()
            if data.get("code") == 0:
                replies = data.get("data", {})
                comments = []
                for r in replies.get("replies", []):
                    member = r.get("member", {})
                    c = r.get("content", {})
                    comments.append({
                        "rpid": r.get("rpid"),
                        "user_name": member.get("uname", ""),
                        "user_avatar": member.get("avatar", ""),
                        "mid": member.get("mid"),
                        "message": c.get("message", ""),
                        "like_count": r.get("like_count", 0),
                        "ctime": r.get("ctime"),
                        "replies_count": r.get("rcount", 0),
                    })
                return {
                    "success": True,
                    "data": {
                        "total": replies.get("total", 0),
                        "page": page,
                        "page_size": page_size,
                        "comments": comments,
                    },
                    "message": f"共 {replies.get('total', 0)} 条评论",
                }

            return {"success": False, "data": {}, "message": data.get("message", "获取失败")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_comments] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CommentPostBody(BaseModel):
    bvid: str
    message: str           # 评论内容
    parent: int = 0        # 回复的评论ID（0=一级评论）
    root: int = 0          # 根评论ID


@router.post("/comment/send", summary="发送评论")
async def send_comment(body: CommentPostBody, conn_id: str = Query(""), session: Session = Depends(get_session)):
    """发送评论（需要登录态）"""
    csrf = await get_csrf_from_cookie(session, conn_id)
    cookie = get_bili_cookie(session, conn_id)

    if not csrf:
        raise HTTPException(status_code=400, detail="缺少有效的 B站 Cookie（需包含 bili_jct）")

    try:
        # 拿 cid
        async with httpx.AsyncClient(timeout=15) as client:
            view_resp = await client.get(
                f"{BILI_API}/x/web-interface/view",
                params={"bvid": body.bvid},
                headers=get_headers(cookie),
            )
            view_data = view_resp.json()
            pages = view_data["data"].get("pages", [])
            oid = pages[0]["cid"] if pages else 0

        payload = {
            "type": 1,
            "oid": oid,
            "message": body.message,
            "csrf_token": csrf,
            "csrf": csrf,
        }
        if body.parent > 0:
            payload["parent"] = body.parent
        if body.root > 0:
            payload["root"] = body.root

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.bilibili.com/",
            "Cookie": cookie,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{BILI_API}/x/v2/reply/add", data=payload, headers=headers)
            data = resp.json()
            if data.get("code") == 0:
                return {"success": True, "data": {"rpid": data.get("data", {}).get("rpid", -1)}, "message": "评论成功"}
            return {"success": False, "data": {}, "message": data.get("message", "评论失败")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[send_comment] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================================================================================
# 7️⃣ 视频搜索（素材采集入口）
# ======================================================================================================================================

@router.get("/search", summary="B站视频搜索", response_model=SearchResponse)
async def search_videos(
    keyword: str = Query(..., description="搜索关键词"),
    order: str = Query("totalrank", description="排序: totalrank / click / pubdate / dm / stow / scores"),
    page: int = Query(1, ge=1, le=50),
    page_size: int = Query(20, ge=1, le=50),
    duration: str = Query("all", description="时长筛选: all / short / medium / long"),
    search_type: str = Query("video", description="类型: video / user / article / series"),
    conn_id: str = Query("", description="平台连接ID（用于登录态搜索）"),
    session: Session = Depends(get_session),
):
    """
    B站综合搜索（支持视频/用户/专栏/合集），可配合素材采集使用。

    排序说明：
    - totalrank: 综合排序
    - click:     最多播放
    - pubdate:   最新发布
    - dm:        最多弹幕
    - stow:      最多收藏
    - scores:    最多评论

    时长筛选：
    - all:    全部
    - short:  10分钟以下
    - medium: 10~30分钟
    - long:   30分钟以上
    """
    type_map = {"video": "video", "user": "bili_user", "article": "article", "series": "series"}
    search_type_val = type_map.get(search_type, "video")

    dur_map = {"all": 0, "short": 1, "medium": 2, "long": 3}
    duration_val = dur_map.get(duration, 0)

    params = {
        "keyword": keyword,
        "search_type": search_type_val,
        "order": order,
        "page": page,
        "page_size": page_size,
    }
    if duration_val > 0:
        params["duration"] = duration_val

    headers = get_headers(get_bili_cookie(session, conn_id))

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BILI_API}/x/web-interface/wbi/search/type",
                params=params,
                headers=headers,
            )
            data = resp.json()

            if data.get("code") != 0:
                return {"success": False, "data": {}, "message": data.get("message", "搜索失败")}

            results = data.get("data", {}).get("result", []) or []

            formatted = []
            for v in results:
                item = {
                    "bvid": v.get("bvid", ""),
                    "title": v.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", ""),
                    "author": v.get("author", ""),
                    "mid": v.get("mid", ""),
                    "play": v.get("play", 0),
                    "danmaku": v.get("video_review", 0),
                    "favorites": v.get("favorites", 0),
                    "likes": v.get("like", 0),
                    "comment": v.get("review", 0),
                    "share": v.get("share", 0),
                    "duration": v.get("duration", ""),
                    "pubdate_str": v.get("pubdate_str", ""),
                    "cover": v.get("pic", ""),
                    "description": v.get("description", "")[:150],
                }
                formatted.append(item)

            return {
                "success": True,
                "data": {
                    "total": data.get("data", {}).get("numResults", 0) if isinstance(data.get("data"), dict) else len(formatted),
                    "page": page,
                    "results": formatted,
                    "search_type": search_type,
                },
                "message": f"找到 {len(formatted)} 个结果",
            }

    except Exception as e:
        logger.error(f"[search_videos] Error: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


# ======================================================================================================================================
# 8️⃣ 视频信息获取
# ======================================================================================================================================

@router.get("/video/info", summary="获取视频详细信息", response_model=VideoInfoResponse)
async def get_video_info(
    bvid: str = Query(..., description="BV 号"),
    session: Session = Depends(get_session),
):
    """获取视频完整信息（含分P列表、UP主信息、标签等）"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BILI_API}/x/web-interface/view",
                params={"bvid": bvid},
                headers=get_headers(get_bili_cookie(session)),
            )
            data = resp.json()

            if data.get("code") != 0:
                raise HTTPException(status_code=404, detail=data.get("message", "视频不存在"))

            info = data["data"]
            owner = info.get("owner", {})
            stat = info.get("stat", {})

            return {
                "success": True,
                "data": {
                    "basic": {
                        "bvid": info.get("bvid", ""),
                        "aid": info.get("aid", ""),
                        "title": info.get("title", ""),
                        "desc": info.get("desc", ""),
                        "pic": info.get("pic", ""),
                        "pubdate": info.get("pubdate", 0),
                        "duration": info.get("duration", 0),
                        "owner": {
                            "mid": owner.get("mid", ""),
                            "name": owner.get("name", ""),
                            "face": owner.get("face", ""),
                        },
                        "tid": info.get("tid", ""),
                        "tname": info.get("tname", ""),
                    },
                    "pages": [
                        {
                            "cid": p.get("cid"),
                            "part": p.get("part"),
                            "duration": p.get("duration"),
                        } for p in info.get("pages", [])
                    ],
                    "tags": [
                        {"tag_id": t.get("tag_id", 0), "tag_name": t.get("tag_name", "")}
                        for t in info.get("tag", []) or []
                    ],
                    "stat": stat,
                },
                "message": "",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_video_info] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================================================================================
# 🔟 字幕功能（保留原有逻辑）
# ======================================================================================================================================

@router.get("/subtitles", summary="获取字幕列表", response_model=SubtitleListResponse)
async def get_subtitles(
    bvid: str = Query(..., description="B站视频 BV 号"),
    conn_id: str = Query("", description="平台连接 ID（用于获取登录 Cookie）"),
    session: Session = Depends(get_session),
):
    """获取视频的字幕列表（AI 生成字幕）"""
    from app.services.platforms import create_client
    cookie = get_bili_cookie(session, conn_id)

    try:
        async with create_client("bili", mode="api", cookie=cookie) as client:
            subtitles = await client.get_subtitles(bvid)
            return {
                "success": True,
                "data": subtitles,
                "message": f"找到 {len(subtitles)} 个字幕",
            }
    except Exception as e:
        logger.error(f"[get_subtitles] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取字幕列表失败: {str(e)}")


@router.get("/subtitle/download", summary="下载字幕文件")
async def download_subtitle(
    bvid: str = Query(..., description="B站视频 BV 号"),
    lan: str = Query("ai-zh", description="字幕语言"),
    format: str = Query("srt", description="格式: srt / ass"),
    conn_id: str = Query("", description="平台连接 ID（用于获取登录 Cookie）"),
    session: Session = Depends(get_session),
):
    """下载字幕文件（SRT / ASS 格式）"""
    from app.services.platforms import create_client
    cookie = get_bili_cookie(session, conn_id)

    if format not in ("srt", "ass"):
        raise HTTPException(status_code=400, detail="格式仅支持 srt 或 ass")

    try:
        async with create_client("bili", mode="api", cookie=cookie) as client:
            subtitles = await client.get_subtitles(bvid)
            subtitle = next((s for s in subtitles if s.get("lan") == lan), None)
            if not subtitle:
                raise HTTPException(status_code=404, detail=f"未找到语言 {lan} 的字幕")
            content = await client.download_subtitle(subtitle.get("subtitle_url"), format)
            if not content:
                raise HTTPException(status_code=500, detail="字幕内容为空")
            filename = f"{bvid}_{lan}.{format}"
            return PlainTextResponse(
                content=content,
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[download_subtitle] Error: {e}")
        raise HTTPException(status_code=500, detail=f"下载字幕失败: {str(e)}")
