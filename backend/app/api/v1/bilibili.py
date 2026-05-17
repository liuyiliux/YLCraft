"""
B站专属接口（字幕、弹幕等 B站特有功能）
"""
from typing import List, Dict

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.db.database import get_session
from app.services.platform_connection import PlatformConnectionService
from app.services.platforms import create_client

router = APIRouter()
logger = __import__("logging").getLogger("ylcraft.api.bilibili")


class SubtitleListResponse(BaseModel):
    """字幕列表响应"""
    success: bool
    data: List[Dict] = []
    message: str = ""


@router.get("/subtitles", summary="获取字幕列表", response_model=SubtitleListResponse)
async def get_subtitles(
    bvid: str = Query(..., description="B站视频 BV 号"),
    conn_id: str = Query("", description="平台连接 ID（用于获取登录 Cookie）"),
    session: Session = Depends(get_session),
):
    """获取视频的字幕列表（AI 生成字幕）

    注意：B站字幕需要登录态，请先在【平台管理】中配置 B站 Cookie，
    然后传入对应的 conn_id。
    """
    # 获取 Cookie
    cookie = ""
    if conn_id:
        try:
            service = PlatformConnectionService(session)
            conn = service.get(conn_id)
            if conn and conn.cookie_content:
                cookie = conn.cookie_content
                logger.info(f"[get_subtitles] Using cookie from conn_id={conn_id}, len={len(cookie)}")
            elif conn:
                logger.warning(f"[get_subtitles] conn_id={conn_id} has empty cookie_content")
        except Exception as e:
            logger.warning(f"[get_subtitles] Failed to get cookie from connection: {e}")

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
    """下载字幕文件（SRT / ASS 格式）

    注意：B站字幕需要登录态，请先在【平台管理】中配置 B站 Cookie，
    然后传入对应的 conn_id。
    """
    if format not in ("srt", "ass"):
        raise HTTPException(status_code=400, detail="格式仅支持 srt 或 ass")

    # 获取 Cookie
    cookie = ""
    if conn_id:
        try:
            service = PlatformConnectionService(session)
            conn = service.get(conn_id)
            if conn and conn.cookie_content:
                cookie = conn.cookie_content
                logger.info(f"[download_subtitle] Using cookie from conn_id={conn_id}, len={len(cookie)}")
            elif conn:
                logger.warning(f"[download_subtitle] conn_id={conn_id} has empty cookie_content")
        except Exception as e:
            logger.warning(f"[download_subtitle] Failed to get cookie from connection: {e}")

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
