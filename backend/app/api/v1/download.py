"""
YLCraft — 视频下载解析 API

POST /api/v1/download/parse — 解析视频链接，返回元数据 + 多清晰度下载链接
POST /api/v1/download/download — 通过 yt-dlp 真正下载视频文件
POST /api/v1/download/tasks — 创建后台下载任务
GET  /api/v1/download/tasks/{task_id} — 查询后台任务状态
"""

from __future__ import annotations

import asyncio
import os
import re
import logging
import uuid
import time
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "vendor"))

import yt_dlp
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, StreamingResponse, Response

from app.services.breaker.service import parse_video_url
from app.services.video.parser import get_cookie_manager, _detect_platform
from app.core.config import ensure_download_path, get_ffmpeg_path

router = APIRouter()
logger = logging.getLogger("ylcraft.download")

# 浏览器 UA
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class VideoQuality(BaseModel):
    quality: str
    resolution: str
    filesize: str
    url: str


class ParseResponse(BaseModel):
    success: bool
    title: str = ""
    author: str = ""
    platform: str = ""
    cover_url: str = ""
    duration: int = 0
    duration_str: str = ""
    video_url: str = ""
    qualities: list[VideoQuality] = []
    audio_url: str = ""
    page_url: str = ""   # 原始分享页 URL（yt-dlp 下载用）
    error: str = ""


class ParseRequest(BaseModel):
    url: str = Field(..., description="视频链接")


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


async def _get_qualities(url: str, title: str, platform: str) -> list[VideoQuality]:
    """用 yt-dlp 获取多清晰度信息"""

    def _fetch() -> list[VideoQuality]:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "noplaylist": True,
            "format": "bestvideo+bestaudio/best",
            "http_headers": {"User-Agent": _BROWSER_UA},
        }
        cookie_path = get_cookie_manager().get_cookie_path_for_url(url)
        if cookie_path:
            ydl_opts["cookiefile"] = str(cookie_path)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []
            formats = info.get("formats") or []
            duration = info.get("duration", 0)
            qualities = []
            seen_resolutions = set()
            for f in formats:
                vcodec = f.get("vcodec") or ""
                if vcodec == "none" or not f.get("url"):
                    continue
                height = f.get("height") or 0
                resolution = f.get("resolution") or (f"{height}p" if height else "")
                ext = f.get("ext") or "mp4"
                tbr = f.get("tbr") or 0
                filesize = f.get("filesize") or 0

                if height > 0:
                    if height in seen_resolutions:
                        continue
                    seen_resolutions.add(height)

                if height >= 2160:
                    quality = "4K"
                elif height >= 1440:
                    quality = "2K"
                elif height >= 1080:
                    quality = "1080P"
                elif height >= 720:
                    quality = "720P"
                elif height >= 480:
                    quality = "480P"
                elif height >= 360:
                    quality = "360P"
                elif height > 0:
                    quality = f"{height}P"
                else:
                    quality = ext

                size_str = "未知"
                if filesize and filesize > 0:
                    size_str = f"{filesize / 1024 / 1024:.1f}MB"
                elif tbr and tbr > 0 and duration > 0:
                    # 正确估算：tbr (kbps) * duration (秒) / 8 / 1024 = MB
                    estimated_size = tbr * duration / 8 / 1024
                    size_str = f"~{estimated_size:.1f}MB"

                qualities.append(VideoQuality(
                    quality=quality,
                    resolution=resolution or ext,
                    filesize=size_str,
                    url=f.get("url") or "",
                ))

            quality_order = {"4K": 6, "2K": 5, "1080P": 4, "720P": 3, "480P": 2, "360P": 1}
            qualities.sort(key=lambda q: (quality_order.get(q.quality, 0), q.resolution), reverse=True)
            return qualities

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch)
    except Exception:
        return []


@router.post("/parse", response_model=ParseResponse, summary="解析视频链接")
async def parse_download_url(req: ParseRequest):
    """解析视频链接，返回元数据 + 多清晰度列表"""
    url = req.url
    try:
        info = await parse_video_url(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")

    logger.info(f"[parse] parse_video_url returned | title={info.get('title','**EMPTY**')} | video_url={info.get('video_url','**EMPTY**')[:60]} | parse_method={info.get('parse_method','?')}")

    title = info.get("title", "未知标题")
    author_name = info.get("author", {})
    if isinstance(author_name, dict):
        author_name = author_name.get("name", "未知作者")
    else:
        author_name = str(author_name)

    platform = info.get("platform", "unknown")
    cover_url = info.get("cover_url", "")
    video_url = info.get("video_url", "")
    duration = info.get("duration", 0) or 0
    duration_str = _format_duration(duration)

    # 检查解析是否真的成功！
    is_valid = bool(video_url) or bool(info.get("images"))
    if not is_valid:
        logger.warning(f"[parse] 解析结果无效（无 video_url 和 images），返回失败: url={url[:80]}")
        return ParseResponse(
            success=False,
            title=title,
            author=author_name,
            platform=platform,
            error="未找到视频数据，请检查链接是否正确，或尝试使用其他平台的视频链接"
        )

    qualities: list[VideoQuality] = []
    if url:
        qualities = await _get_qualities(url, title, platform)
        if not qualities:
            video_url = video_url or url

    # 解析完成后，在素材库创建一条 PARSED 状态记录
    from app.db.database import get_async_session
    from app.db.models.asset import AssetType, AssetStatus
    from app.services.asset.service import AssetService

    # 从 info 中提取 width/height
    width = 0
    height = 0
    if info and isinstance(info, dict):
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)

    try:
        async with get_async_session() as db_session:
            asset_service = AssetService(db_session)
            asset = await asset_service.create_from_parse(
                source_url=url,
                title=title,
                platform=platform,
                author=author_name,
                cover_url=cover_url,
                duration=duration,
                metadata=info,
            )
            # 更新 width/height/thumbnail
            if width and asset.width == 0:
                asset.width = width
            if height and asset.height == 0:
                asset.height = height
            if cover_url and not asset.thumbnail_path:
                asset.thumbnail_path = cover_url
            if asset.duration == 0 and duration:
                asset.duration = duration
            await db_session.commit()
            await db_session.refresh(asset)
            logger.info(f"[parse] asset tracked | id={asset.id} | platform={platform}")
    except Exception as e:
        logger.warning(f"[parse] asset tracking failed (non-blocking): {e}")

    # page_url：原始分享页 URL，用于 yt-dlp 下载（不是 CDN 直链）
    page_url = info.get("original_url", "") or url

    return ParseResponse(
        success=True,
        title=title,
        author=author_name,
        platform=platform,
        cover_url=cover_url,
        duration=duration,
        duration_str=duration_str,
        video_url=video_url,
        qualities=qualities,
        page_url=page_url,
    )


# =============================================================================
# 真正下载
# =============================================================================

class DownloadRequest(BaseModel):
    url: str = Field(..., description="视频链接")
    quality: str | None = Field(None, description="清晰度：1080P/720P/480P/360P，默认最佳")
    title: str | None = Field(None, description="文件名（不含扩展名）")
    page_url: str | None = Field(None, description="原始分享页URL（用于yt-dlp格式枚举）")
    is_audio: bool = Field(False, description="是否仅下载音频（mp3/m4a）")


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()[:200]


def _ytdlp_download(url: str, quality_label: str | None, title: str | None, page_url: str | None = None, is_audio: bool = False) -> str:
    """用 yt-dlp 下载视频，由 run_in_executor 调用（同步阻塞）"""
    savedir = ensure_download_path()
    logger.info(f"[download] start | url={url[:80]} | quality={quality_label} | is_audio={is_audio}")

    effective_url = page_url if page_url else url

    if is_audio:
        format_str = "bestaudio/best"
    elif quality_label:
        ql = quality_label.lower()
        if "1080" in ql:
            format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        elif "720" in ql:
            format_str = "bestvideo[height<=720]+bestaudio/best[height<=720]"
        elif "480" in ql:
            format_str = "bestvideo[height<=480]+bestaudio/best[height<=480]"
        elif "360" in ql:
            format_str = "bestvideo[height<=360]+bestaudio/best[height<=360]"
        else:
            format_str = "bestvideo+bestaudio/best"
    else:
        format_str = "bestvideo+bestaudio/best"

    outtmpl = str(savedir / f"ytdlp_{hash(effective_url) & 0xFFFFFFFF}_%(title)s.%(ext)s")

    ydl_opts = {
        "format": format_str,
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "noplaylist": True,
        "restrict_filenames": True,
        "keepvideo": False,
        "http_headers": {"User-Agent": _BROWSER_UA},
    }

    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = str(ffmpeg_path)

    cookie_path = get_cookie_manager().get_cookie_path_for_url(effective_url)
    if cookie_path:
        ydl_opts["cookiefile"] = str(cookie_path)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"[download] yt-dlp extracting info for {effective_url[:80]}")
        info = ydl.extract_info(effective_url, download=True)
        if not info:
            raise HTTPException(status_code=500, detail="yt-dlp 未能获取视频信息")

        output_path = info.get("_filename") or ydl.prepare_filename(info)
        if output_path and os.path.exists(output_path):
            logger.info(f"[download] success | path={output_path}")
            return output_path

        candidates = [
            os.path.join(savedir, f)
            for f in os.listdir(savedir)
            if f.startswith(f"ytdlp_{hash(effective_url) & 0xFFFFFFFF}_") and f.endswith((".mp4", ".m4a", ".mp3", ".wav"))
        ]
        if candidates:
            latest = max(candidates, key=os.path.getmtime)
            logger.info(f"[download] fallback found | path={latest}")
            return latest

    raise HTTPException(status_code=500, detail="yt-dlp 下载失败，未找到输出文件")


@router.post("/download", summary="通过 yt-dlp 下载视频（返回文件流）")
async def download_video(req: DownloadRequest):
    """调用 yt-dlp 下载视频，以流式响应返回"""
    loop = asyncio.get_running_loop()
    
    # 先解析视频获取 width/height/thumbnail
    video_info = None
    try:
        from app.services.video import parser
        video_info = await parser.parse(req.url)
    except Exception:
        pass
    
    try:
        filepath = await asyncio.wait_for(
            loop.run_in_executor(
                None, _ytdlp_download, req.url, req.quality, req.title, req.page_url, req.is_audio
            ),
            timeout=1800,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="下载超时（30分钟），请尝试更低清晰度")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {e}")

    filename = os.path.basename(filepath)
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in ("mp3", "mpeg"):
        media_type = "audio/mpeg"
    elif ext in ("m4a", "aac"):
        media_type = "audio/mp4"
    elif ext == "wav":
        media_type = "audio/wav"
    else:
        media_type = "video/mp4"

    effective_url = req.page_url if req.page_url else req.url
    file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    
    width = video_info.width if video_info else 0
    height = video_info.height if video_info else 0
    duration = video_info.duration if video_info else 0
    thumbnail_path = video_info.cover_url if video_info else ""

    from app.db.database import get_async_session
    from app.db.models.asset import Asset, AssetType, AssetStatus
    from app.services.asset.service import AssetService

    # 构建下载元数据
    download_metadata = {
        "quality": req.quality or "best",
        "is_audio": req.is_audio,
        "page_url": req.page_url or "",
    }

    async with get_async_session() as db_session:
        asset_service = AssetService(db_session)
        existing = await asset_service.get_by_url(effective_url)
        platform = _detect_platform(effective_url)
        if existing:
            await asset_service.mark_ready(existing, file_path=filepath, file_size=file_size, mime_type=media_type)
            if width: existing.width = width
            if height: existing.height = height
            if duration: existing.duration = duration
            if thumbnail_path and not existing.thumbnail_path:
                existing.thumbnail_path = thumbnail_path
            # 合并下载元数据到已有 metadata
            if existing.metadata_json:
                try:
                    import json as _json
                    existing_meta = _json.loads(existing.metadata_json)
                    existing_meta.update(download_metadata)
                    existing.metadata_json = _json.dumps(existing_meta, ensure_ascii=False)
                except Exception:
                    existing.metadata_json = json.dumps(download_metadata, ensure_ascii=False)
            else:
                existing.metadata_json = json.dumps(download_metadata, ensure_ascii=False)
            await db_session.commit()
            await db_session.refresh(existing)
            asset_id = existing.id
        else:
            asset_type = AssetType.AUDIO if req.is_audio else AssetType.VIDEO
            new_asset = await asset_service.create(
                asset_type=asset_type,
                title=req.title or filename,
                source_url=effective_url,
                platform=platform,
                file_path=filepath,
                file_size=file_size,
                mime_type=media_type,
                status=AssetStatus.READY,
                width=width,
                height=height,
                duration=duration,
                thumbnail_path=thumbnail_path,
                metadata_json=json.dumps(download_metadata, ensure_ascii=False),
            )
            asset_id = new_asset.id

    from urllib.parse import quote
    safe_path = quote(filepath, safe=":/\\")

    chunk_size = 1024 * 1024

    async def file_iterator():
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}",
            "X-File-Path": safe_path,
            "X-Asset-ID": asset_id,
            "Accept-Ranges": "none",
        },
    )


# =============================================================================
# 后台下载任务（解决大文件 XHR 超时）
# =============================================================================

_download_tasks: dict[str, dict] = {}


class DownloadTask:
    def __init__(self, task_id: str, url: str, quality: str | None,
                 title: str | None, page_url: str | None, is_audio: bool):
        self.task_id = task_id
        self.url = url
        self.quality = quality
        self.title = title
        self.page_url = page_url
        self.is_audio = is_audio
        self.status = "pending"
        self.progress = 0
        self.progress_message = ""
        self.file_path: str | None = None
        self.asset_id: str | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self.started_at: float | None = None
        self.completed_at: float | None = None


def _is_douyin_direct_url(url: str) -> bool:
    """判断 URL 是否为抖音 direct CDN URL（可直接用 httpx 下载，跳过 yt-dlp）"""
    return bool(url and ("douyinvod.com" in url or "amemv.com" in url))


def _httpx_download(url: str, quality_label: str | None, title: str | None, is_audio: bool = False) -> str:
    """直接用 httpx 下载抖音 CDN URL，绕过 yt-dlp。返回保存的文件路径。"""
    import httpx, hashlib, time as _time

    savedir = ensure_download_path()
    logger.info(f"[httpx_download] start | url={url[:80]} | quality={quality_label} | is_audio={is_audio}")

    # 生成文件名：直接用标题，去掉前缀和 hash
    ext = "m4a" if is_audio else "mp4"
    safe_title = _sanitize_filename(title) if title else "video"
    filename = f"{safe_title}.{ext}"
    filepath = savedir / filename

    # 发送请求（带重定向跟随）
    req_headers = {
        "User-Agent": _BROWSER_UA,
        "Referer": "https://www.douyin.com/",
    }

    total_size = 0
    downloaded_size = 0

    with httpx.stream("GET", url, headers=req_headers, follow_redirects=True, timeout=60.0) as resp:
        resp.raise_for_status()
        total_size = int(resp.headers.get("content-length", 0))
        content_type = resp.headers.get("content-type", "")
        logger.info(f"[httpx_download] status={resp.status_code} | size={total_size} | ct={content_type}")

        with open(filepath, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    # 不在这里更新 progress（BackgroundTask 中不方便）

    logger.info(f"[httpx_download] done | path={filepath} | size={downloaded_size}")
    return str(filepath)


async def _run_download_task(task: DownloadTask):
    task.status = "downloading"
    task.started_at = time.time()
    _download_tasks[task.task_id] = task.__dict__

    try:
        # 抖音 direct CDN URL → 直接用 httpx 下载，跳过 yt-dlp
        if _is_douyin_direct_url(task.url):
            loop = asyncio.get_running_loop()
            filepath = await asyncio.wait_for(
                loop.run_in_executor(None, _httpx_download,
                    task.url, task.quality, task.title, task.is_audio
                ),
                timeout=1800,
            )
        else:
            loop = asyncio.get_running_loop()
            filepath = await asyncio.wait_for(
                loop.run_in_executor(None, _ytdlp_download,
                    task.url, task.quality, task.title, task.page_url, task.is_audio
                ),
                timeout=1800,
            )

        task.progress = 90
        task.progress_message = "下载完成，准备文件..."
        _download_tasks[task.task_id] = task.__dict__

        filename = os.path.basename(filepath)
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in ("mp3", "mpeg"):
            media_type = "audio/mpeg"
        elif ext in ("m4a", "aac"):
            media_type = "audio/mp4"
        elif ext == "wav":
            media_type = "audio/wav"
        else:
            media_type = "video/mp4"

        effective_url = task.page_url if task.page_url else task.url
        file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0

        from app.db.database import get_async_session
        from app.db.models.asset import AssetType, AssetStatus
        from app.services.asset.service import AssetService

        # 构建下载元数据
        download_metadata = {
            "quality": task.quality or "best",
            "is_audio": task.is_audio,
            "page_url": task.page_url or "",
        }

        async with get_async_session() as db_session:
            asset_service = AssetService(db_session)
            existing = await asset_service.get_by_url(effective_url)
            platform = _detect_platform(effective_url)
            if existing:
                await asset_service.mark_ready(existing, file_path=filepath, file_size=file_size, mime_type=media_type)
                # 合并下载元数据到已有 metadata
                if existing.metadata_json:
                    try:
                        import json as _json
                        existing_meta = _json.loads(existing.metadata_json)
                        existing_meta.update(download_metadata)
                        existing.metadata_json = _json.dumps(existing_meta, ensure_ascii=False)
                    except Exception:
                        existing.metadata_json = json.dumps(download_metadata, ensure_ascii=False)
                else:
                    existing.metadata_json = json.dumps(download_metadata, ensure_ascii=False)
                task.asset_id = existing.id
            else:
                asset_type = AssetType.AUDIO if task.is_audio else AssetType.VIDEO
                new_asset = await asset_service.create(
                    asset_type=asset_type,
                    title=task.title or filename,
                    source_url=effective_url,
                    platform=platform,
                    file_path=filepath,
                    file_size=file_size,
                    mime_type=media_type,
                    status=AssetStatus.READY,
                    metadata_json=json.dumps(download_metadata, ensure_ascii=False),
                )
                task.asset_id = new_asset.id

        task.file_path = filepath
        task.status = "done"
        task.progress = 100
        task.progress_message = "完成"
        task.completed_at = time.time()
        _download_tasks[task.task_id] = task.__dict__

    except asyncio.TimeoutError:
        task.status = "failed"
        task.error = "下载超时（30分钟），请尝试更低清晰度"
        task.completed_at = time.time()
        _download_tasks[task.task_id] = task.__dict__
    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        task.completed_at = time.time()
        _download_tasks[task.task_id] = task.__dict__


class TaskCreateRequest(BaseModel):
    url: str = Field(..., description="视频链接")
    quality: str | None = Field(None, description="清晰度")
    title: str | None = Field(None, description="文件名")
    page_url: str | None = Field(None, description="原始分享页URL")
    is_audio: bool = Field(False, description="是否仅下载音频")


@router.post("/tasks", summary="创建下载任务（后台，后台轮询）")
async def create_download_task(req: TaskCreateRequest, background: BackgroundTasks):
    """创建后台下载任务，立即返回 task_id，前端轮询状态"""
    task_id = str(uuid.uuid4())[:12]
    task = DownloadTask(
        task_id=task_id,
        url=req.url,
        quality=req.quality,
        title=req.title,
        page_url=req.page_url,
        is_audio=req.is_audio,
    )
    _download_tasks[task_id] = task.__dict__
    background.add_task(_run_download_task, task)

    return JSONResponse({
        "success": True,
        "task_id": task_id,
        "status": "pending",
        "message": "下载任务已创建，请在 /downloads/tasks/{task_id} 轮询状态",
    })


@router.get("/tasks/{task_id}", summary="查询下载任务状态")
async def get_download_task(task_id: str):
    """轮询下载任务状态：pending → downloading → done / failed"""
    task_data = _download_tasks.get(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="任务不存在")

    return JSONResponse({
        "success": True,
        "task_id": task_id,
        "status": task_data["status"],
        "progress": task_data["progress"],
        "progress_message": task_data["progress_message"],
        "result": {
            "file_path": task_data.get("file_path"),
            "asset_id": task_data.get("asset_id"),
        } if task_data["status"] == "done" else None,
        "error": task_data.get("error"),
        "created_at": task_data["created_at"],
        "started_at": task_data.get("started_at"),
        "completed_at": task_data.get("completed_at"),
    })


@router.post("/open-folder", summary="打开文件夹并选中文件（Windows）")
async def open_folder(req: dict):
    """调用 Windows explorer /select,<path> 打开文件所在目录并选中文件"""
    import subprocess
    file_path = req.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    subprocess.Popen(["explorer", "/select,", file_path])
    return JSONResponse({"success": True})


@router.get("/cover-proxy", summary="封面图代理（解决 B站 CDN 防爬虫限制）")
async def cover_proxy(url: str):
    """后端代理请求封面图，解决浏览器直接加载 B站 CDN 的跨域限制"""
    import httpx
    if not url:
        raise HTTPException(status_code=400, detail="url 参数不能为空")
    try:
        headers = {
            "Referer": "https://www.bilibili.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
        }
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            content = resp.content
        # 推断 Content-Type
        import mimetypes
        mime = mimetypes.guess_type(url)[0] or "image/jpeg"
        return Response(content=content, media_type=mime)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"封面图请求失败: {e}")
    except Exception as e:
        import traceback
        logger.error(f"[cover-proxy] 错误: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=502, detail=f"封面图代理失败: {type(e).__name__}: {e}")
