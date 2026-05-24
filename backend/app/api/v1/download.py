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
from app.services.download import parse_with_manager, download_with_manager, get_supported_platforms

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
    asset_id: str = ""   # 素材ID（解析时创建）
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
        cookie_jar = get_cookie_manager().get_cookiejar_for_url(url)
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "noplaylist": True,
            "format": "bestvideo+bestaudio/best",
            "http_headers": {"User-Agent": _BROWSER_UA},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if cookie_jar:
                ydl.cookiejar = cookie_jar
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

                from app.services.download.base import BaseDownloader
                size_str = BaseDownloader.calculate_filesize(
                    filesize_bytes=filesize,
                    bitrate_bps=tbr * 1000 if tbr else None,  # convert kbps to bps
                    duration_seconds=duration,
                )

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
    parsed_asset_id = ""
    
    # 1. 先尝试使用平台专用下载器
    try:
        from app.services.download import parse_with_manager
        info_new = await parse_with_manager(url)
        if info_new:
            logger.info(f"[parse] 使用平台专用下载器解析成功: {url[:60]}")
            
            # 转换为 ParseResponse 格式
            qualities = [
                VideoQuality(
                    quality=q.quality,
                    resolution=q.resolution,
                    filesize=q.filesize,
                    url=q.url,
                )
                for q in info_new.qualities
            ]
            
            # 解析时创建素材记录
            page_url = info_new.page_url or url
            try:
                from app.db.database import get_async_session
                from app.services.asset.service import AssetService
                
                async with get_async_session() as db_session:
                    asset_service = AssetService(db_session)
                    asset = await asset_service.create_from_parse(
                        source_url=url,
                        title=info_new.title,
                        platform=info_new.platform,
                        author=info_new.author,
                        cover_url=info_new.cover_url,
                        duration=info_new.duration,
                        metadata={"parse_method": "platform_manager"},
                    )
                    await db_session.commit()
                    await db_session.refresh(asset)
                    parsed_asset_id = asset.id
                    logger.info(f"[parse] asset tracked (platform) | id={asset.id}")
            except Exception as asset_e:
                logger.warning(f"[parse] asset tracking failed (platform): {asset_e}")
            
            return ParseResponse(
                success=True,
                asset_id=parsed_asset_id,
                title=info_new.title,
                author=info_new.author,
                platform=info_new.platform,
                cover_url=info_new.cover_url,
                duration=info_new.duration,
                duration_str=_format_duration(info_new.duration),
                qualities=qualities,
                page_url=page_url,
            )
    except Exception as e:
        logger.warning(f"[parse] 平台专用下载器失败，降级到 yt-dlp: {e}")
    
    # 2. 降级到 yt-dlp
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
        
        # 智能错误提示
        error_msg = "未找到视频或图片数据，请检查链接是否正确，或尝试使用其他平台的链接"
        url_lower = url.lower()
        
        if "twitter.com" in url_lower or "x.com" in url_lower:
            error_msg = "未能解析 Twitter/X 内容，可能需要登录或内容不公开"
        elif "telegram.org" in url_lower or "t.me" in url_lower:
            error_msg = "未能解析 Telegram 内容，可能需要登录或内容不公开"
        
        return ParseResponse(
            success=False,
            title=title,
            author=author_name,
            platform=platform,
            error=error_msg
        )

    qualities: list[VideoQuality] = []
    if url:
        qualities = await _get_qualities(url, title, platform)
        if not qualities:
            video_url = video_url or url

    # 解析完成后，在素材库创建一条 parsed 状态记录
    from app.db.database import get_async_session
    from app.services.asset.service import AssetService

    # 从 info 中提取 width/height
    width = 0
    height = 0
    if info and isinstance(info, dict):
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)

    # 解析时下载封面到本地
    thumbnail_local_path = ""
    if cover_url and cover_url.startswith("http"):
        try:
            loop = asyncio.get_running_loop()
            thumbnail_local_path = await loop.run_in_executor(
                None, _download_cover_image, cover_url, "", title
            )
            if thumbnail_local_path:
                logger.info(f"[parse] 封面已保存: {thumbnail_local_path}")
        except Exception as cover_err:
            logger.warning(f"[parse] 封面下载失败（非阻塞）: {cover_err}")

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
            # 更新 width/height/cover_url
            if width and asset.width == 0:
                asset.width = width
            if height and asset.height == 0:
                asset.height = height
            # 优先使用本地封面路径，其次使用URL
            if thumbnail_local_path:
                asset.cover_url = thumbnail_local_path
            elif cover_url and not asset.cover_url:
                asset.cover_url = cover_url
            if asset.duration == 0 and duration:
                asset.duration = duration
            await db_session.commit()
            await db_session.refresh(asset)
            logger.info(f"[parse] asset tracked | id={asset.id} | platform={platform}")
            parsed_asset_id = asset.id
    except Exception as e:
        logger.warning(f"[parse] asset tracking failed (non-blocking): {e}")
        parsed_asset_id = ""

    # page_url：原始分享页 URL，用于 yt-dlp 下载（不是 CDN 直链）
    page_url = info.get("original_url", "") or url

    return ParseResponse(
        success=True,
        asset_id=parsed_asset_id,
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
    asset_id: str | None = Field(None, description="素材ID（解析时创建，用于关联素材记录）")


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()[:200]




def _get_cookie_file_for_ytdlp(url: str) -> Optional[str]:
    """获取适用于 yt-dlp 的 cookie 文件路径（Netscape 格式）
    
    使用 CookieManager 的公共方法，会自动从 DB 重建文件（如不存在）。
    """
    try:
        mgr = get_cookie_manager()
        platform = _detect_platform(url)
        if not platform:
            return None
        return mgr.get_cookie_file(platform)
    except Exception as e:
        logger.warning(f'[_cookie] 获取 cookie 文件失败: {e}')
    return None

def _ytdlp_download(url: str, quality_label: str | None, title: str | None, page_url: str | None = None, is_audio: bool = False) -> str:
    """用 yt-dlp 下载视频（兜底方案）

    关键点：使用 cookie 文件路径（Netscape 格式），不用内存 CookieJar。
    Twitter/X 等平台对内存 CookieJar 支持不好，必须用文件。
    """
    savedir = ensure_download_path()
    logger.info(f"[download] yt-dlp start | url={url[:80]} | quality={quality_label} | is_audio={is_audio}")

    effective_url = page_url if page_url else url

    # 获取 cookie 文件路径（Netscape 格式），不用 CookieJar
    cookie_file = _get_cookie_file_for_ytdlp(effective_url)
    if cookie_file:
        logger.info(f"[download] yt-dlp 使用 cookie 文件: {cookie_file}")
    else:
        logger.info(f"[download] yt-dlp 无 cookie 文件，匿名下载")

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

    # 关键：传 cookie 文件，不传 CookieJar
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file
        logger.info(f"[download] yt-dlp cookiefile={cookie_file}")

    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = str(ffmpeg_path)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"[download] yt-dlp extracting info for {effective_url[:80]}")
        info = ydl.extract_info(effective_url, download=True)
        if not info:
            raise ValueError("yt-dlp 未能获取视频信息")

        output_path = info.get("_filename") or ydl.prepare_filename(info)
        if output_path and os.path.exists(output_path):
            logger.info(f"[download] yt-dlp success | path={output_path}")
            return output_path

        # fallback：按前缀匹配最新文件
        candidates = [
            os.path.join(savedir, f)
            for f in os.listdir(savedir)
            if f.startswith(f"ytdlp_{hash(effective_url) & 0xFFFFFFFF}_")
            and f.endswith((".mp4", ".m4a", ".mp3", ".wav"))
        ]
        if candidates:
            latest = max(candidates, key=os.path.getmtime)
            logger.info(f"[download] yt-dlp fallback | path={latest}")
            return latest

    raise ValueError("yt-dlp 下载失败，未找到输出文件")


@router.post("/download", summary="通过 yt-dlp 下载视频（返回文件流）")
async def download_video(req: DownloadRequest):
    """调用下载器下载视频，以流式响应返回"""
    loop = asyncio.get_running_loop()
    
    # 1. 先尝试使用平台专用下载器
    try:
        from app.services.download import download_with_manager
        result = await asyncio.wait_for(
            download_with_manager(
                url=req.url,
                quality=req.quality or "best",
                title=req.title,
                page_url=req.page_url,
                is_audio=req.is_audio,
            ),
            timeout=1800,
        )
        filepath, video_info = result
        if filepath:
            logger.info(f"[download] 使用平台专用下载器完成: {filepath}")
    except Exception as e:
        logger.warning(f"[download] 平台专用下载器失败，降级到 yt-dlp: {e}")
        filepath = None
        video_info = None
    
    # 2. 降级到 yt-dlp
    if not filepath:
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
    
    # 从 video_info 获取元数据（优先）
    if video_info:
        width = height = 0
        if video_info.qualities:
            best_quality = video_info.qualities[0]
            if best_quality.resolution:
                res_parts = best_quality.resolution.split("x")
                if len(res_parts) == 2:
                    width = int(res_parts[0])
                    height = int(res_parts[1])
        duration = video_info.duration or 0
        cover_url = video_info.cover_url or ""
        title = video_info.title or ""
        author = video_info.author or ""
        platform = video_info.platform or ""
    else:
        width = height = duration = 0
        thumbnail_path = ""
        title = ""
        author = ""
        platform = ""
        cover_url = ""
    
    # 从数据库查询已有元数据（补充）
    search_urls = [req.page_url, req.url] if req.page_url else [req.url]
    
    try:
        from app.db.database import get_async_session
        from app.services.asset.service import AssetService
        async with get_async_session() as _db_session:
            _asset_service = AssetService(_db_session)
            _existing = None
            for url_to_search in search_urls:
                _existing = await _asset_service.get_by_url(url_to_search)
                if _existing:
                    break
            
            if _existing:
                if not width:
                    width = _existing.width or 0
                if not height:
                    height = _existing.height or 0
                if not duration:
                    duration = _existing.duration or 0
                if not title:
                    title = _existing.title or ""
                if not author:
                    author = _existing.author or ""
                if not platform:
                    platform = _existing.platform or ""
                if not cover_url:
                    cover_url = _existing.cover_url or ""
    except Exception:
        pass
    
    # 如果没有找到已有记录，使用请求参数中的标题或文件名
    effective_title = title or req.title or filename
    
    from app.db.database import get_async_session
    from app.services.asset.service import AssetService

    # 构建下载元数据
    download_metadata = {
        "quality": req.quality or "best",
        "is_audio": req.is_audio,
        "page_url": req.page_url or "",
    }

    async with get_async_session() as db_session:
        asset_service = AssetService(db_session)
        
        # 优先使用 req.asset_id 查找资产（最准确）
        existing = None
        if req.asset_id:
            existing = await asset_service.get_by_id(req.asset_id)
            if existing:
                logger.info(f"[download] 使用 asset_id 找到素材: {req.asset_id}")
        
        # 如果没有 asset_id 或找不到，按 URL 查找
        if not existing:
            for url_to_search in search_urls:
                existing = await asset_service.get_by_url(url_to_search)
                if existing:
                    break
        
        # 如果还是没找到，尝试用原始 URL
        if not existing:
            existing = await asset_service.get_by_url(req.url)
        
        detected_platform = platform or _detect_platform(effective_url)
        
        if existing:
            await asset_service.mark_ready(existing, file_path=filepath, file_size=file_size, mime_type=media_type)
            if width: existing.width = width
            if height: existing.height = height
            if duration: existing.duration = duration
            if cover_url:
                existing.cover_url = cover_url
            if title: existing.title = title
            if author: existing.author = author
            if detected_platform: existing.platform = detected_platform
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
            asset_type = "audio" if req.is_audio else "video"
            new_asset = await asset_service.create(
                asset_type=asset_type,
                title=effective_title,
                source_url=effective_url,
                platform=platform,
                file_path=filepath,
                file_size=file_size,
                mime_type=media_type,
                status="READY",
                width=width,
                height=height,
                duration=duration,
                cover_url=thumbnail_path,
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
                 title: str | None, page_url: str | None, is_audio: bool,
                 asset_id: str | None = None):
        self.task_id = task_id
        self.url = url
        self.quality = quality
        self.title = title
        self.page_url = page_url
        self.is_audio = is_audio
        self.asset_id = asset_id  # 素材ID（解析时创建）
        self.status = "PENDING"
        self.progress = 0
        self.progress_message = ""
        self.file_path: str | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self.started_at: float | None = None
        self.completed_at: float | None = None


async def _run_download_task(task: DownloadTask):
    """执行后台下载任务"""
    task.started_at = time.time()
    task.status = "DOWNLOADING"
    task.progress = 5
    task.progress_message = "开始下载"
    
    try:
        from app.services.download import download_with_manager
        
        # 更新全局任务字典（状态同步）
        _download_tasks[task.task_id] = task.__dict__
        
        # 调用下载逻辑
        task.progress = 10
        task.progress_message = "解析视频信息..."
        _download_tasks[task.task_id] = task.__dict__
        
        result = await download_with_manager(
            url=task.url,
            quality=task.quality or "best",
            title=task.title,
            page_url=task.page_url,
            is_audio=task.is_audio,
        )
        filepath, video_info = result

        # 平台专用下载器失败，降级到 yt-dlp
        if not filepath:
            task.progress_message = "专用下载器失败，尝试 yt-dlp 兜底..."
            _download_tasks[task.task_id] = task.__dict__
            logger.warning(f"[_run_download_task] 平台下载器失败，降级到 yt-dlp: {task.url[:80]}")
            
            loop = asyncio.get_running_loop()
            filepath = await asyncio.wait_for(
                loop.run_in_executor(
                    None, _ytdlp_download,
                    task.url, task.quality, task.title,
                    task.page_url, task.is_audio,
                ),
                timeout=1800,
            )

        if not filepath:
            raise ValueError("所有下载方式均失败（平台下载器 + yt-dlp 兜底），可能解析或权限问题")

        task.file_path = filepath
        task.status = "DONE"
        task.progress = 100
        task.progress_message = "下载完成"
        
        # 记录到数据库
        try:
            from app.db.database import get_async_session
            from app.services.asset.service import AssetService
            from sqlalchemy import select
            
            async with get_async_session() as db_session:
                asset_service = AssetService(db_session)
                platform = _detect_platform(task.url)
                file_size = os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 0
                
                # 优先使用 task.asset_id 查找资产（最准确）
                existing = None
                if task.asset_id:
                    existing = await asset_service.get_by_id(task.asset_id)
                    if existing:
                        logger.info(f"[_run_download_task] 使用 asset_id 找到素材: {task.asset_id}")
                
                # 如果没有 asset_id 或找不到，按 URL 查找
                if not existing:
                    if task.page_url:
                        existing = await asset_service.get_by_url(task.page_url)
                    if not existing:
                        existing = await asset_service.get_by_url(task.url)
                
                # 从 video_info 中获取元数据
                width = 0
                height = 0
                cover_url = ""
                if video_info:
                    # 获取分辨率：优先匹配实际下载的 quality，否则取最高分辨率
                    if video_info.qualities and task.quality:
                        matched_quality = None
                        for q in video_info.qualities:
                            if q.quality == task.quality:
                                matched_quality = q
                                break
                        if not matched_quality:
                            matched_quality = video_info.qualities[0]
                        if matched_quality and matched_quality.resolution:
                            res_parts = matched_quality.resolution.split("x")
                            if len(res_parts) == 2:
                                width = int(res_parts[0])
                                height = int(res_parts[1])
                    elif video_info.qualities:
                        best_quality = video_info.qualities[0]
                        if best_quality.resolution:
                            res_parts = best_quality.resolution.split("x")
                            if len(res_parts) == 2:
                                width = int(res_parts[0])
                                height = int(res_parts[1])
                    # 获取封面URL
                    cover_url = video_info.cover_url or ""
                
                # 下载封面到本地
                local_cover_path = ""
                if cover_url and cover_url.startswith("http"):
                    local_cover_path = _download_cover_image(cover_url, filepath, task.title)
                    if local_cover_path:
                        logger.info(f"[_run_download_task] 封面已下载: {local_cover_path}")
                
                if existing:
                    mime_type = "audio/mpeg" if task.is_audio else "video/mp4"
                    await asset_service.mark_ready(existing, file_path=filepath, file_size=file_size, mime_type=mime_type)
                    # 更新元数据
                    if width: existing.width = width
                    if height: existing.height = height
                    if local_cover_path:
                        existing.cover_url = local_cover_path
                    elif cover_url and not existing.cover_url:
                        existing.cover_url = cover_url
                    task.asset_id = existing.id
                else:
                    new_asset = await asset_service.create(
                        type="audio" if task.is_audio else "video",
                        title=task.title or os.path.basename(filepath),
                        source_url=task.url,
                        platform=platform,
                        file_path=filepath,
                        file_size=file_size,
                        mime_type="audio/mpeg" if task.is_audio else "video/mp4",
                        status="READY",
                        width=width,
                        height=height,
                        cover_url=local_cover_path or cover_url,
                    )
                    task.asset_id = new_asset.id
                
                await db_session.commit()

                # 确保 asset_node 存在（嵌入向量存储需要引用 asset_nodes.id）
                try:
                    from app.db.models.asset_hub import AssetNode, AssetType as HubAssetType
                    result = await db_session.execute(
                        select(AssetNode).where(AssetNode.id == task.asset_id)
                    )
                    if not result.scalar_one_or_none():
                        asset_type = HubAssetType.VIDEO
                        if task.is_audio:
                            asset_type = HubAssetType.AUDIO
                        asset_node = AssetNode(
                            id=task.asset_id,
                            name=task.title or os.path.basename(filepath),
                            asset_type=asset_type,
                            thumbnail_url=local_cover_path or cover_url or "",
                        )
                        db_session.add(asset_node)
                        await db_session.commit()
                        logger.info(f"[_run_download_task] 已创建 asset_node: {task.asset_id}")
                except Exception as node_e:
                    logger.warning(f"[_run_download_task] 创建 asset_node 失败: {node_e}")

                # 自动生成嵌入向量（用于混合搜索）
                if task.asset_id:
                    try:
                        from app.services.embedding.service import EmbeddingService
                        embed_service = EmbeddingService(db_session)
                        # 文本嵌入：用标题
                        if task.title:
                            await embed_service.store_text_embedding(task.asset_id, task.title)
                            logger.info(f"[_run_download_task] 已生成文本嵌入: {task.asset_id}")
                        # 图像嵌入：用封面图
                        cover = local_cover_path or cover_url
                        if cover:
                            await embed_service.store_image_embedding(task.asset_id, cover)
                            logger.info(f"[_run_download_task] 已生成图像嵌入: {task.asset_id}")
                    except Exception as embed_e:
                        logger.warning(f"[_run_download_task] 嵌入生成失败（不影响下载）: {embed_e}")
                    
        except Exception as db_e:
            logger.warning(f"[_run_download_task] 数据库记录失败: {db_e}")
        
    except Exception as e:
        task.status = "FAILED"
        task.error = str(e)
        task.progress_message = f"下载失败: {str(e)[:50]}"
        logger.error(f"[_run_download_task] 下载失败: {e}")
        
    finally:
        task.completed_at = time.time()
        # 更新全局任务字典
        _download_tasks[task.task_id] = task.__dict__


def _download_cover_image(cover_url: str, video_path: str, title: str | None) -> str:
    """下载封面图到本地，与视频同目录"""
    import httpx
    import mimetypes

    if not cover_url or not cover_url.startswith("http"):
        return ""

    try:
        savedir = ensure_download_path()
        safe_title = _sanitize_filename(title) if title else "video"
        ext = "jpg"

        # 根据 URL 或 Content-Type 推断扩展名
        if ".png" in cover_url.lower():
            ext = "png"
        elif ".webp" in cover_url.lower():
            ext = "webp"
        elif ".gif" in cover_url.lower():
            ext = "gif"

        filename = f"{safe_title}_cover.{ext}"
        filepath = savedir / filename

        # 直接下载覆盖
        with httpx.stream("GET", cover_url, timeout=30.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

        return str(filepath)
    except Exception as e:
        logger.warning(f"[_download_cover_image] 封面下载失败: {e}")
        return ""


class TaskCreateRequest(BaseModel):
    url: str = Field(..., description="视频链接")
    quality: str | None = Field(None, description="清晰度")
    title: str | None = Field(None, description="文件名")
    page_url: str | None = Field(None, description="原始分享页URL")
    is_audio: bool = Field(False, description="是否仅下载音频")
    asset_id: str | None = Field(None, description="素材ID（解析时创建，用于关联素材记录）")


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
        asset_id=req.asset_id,
    )
    _download_tasks[task_id] = task.__dict__
    background.add_task(_run_download_task, task)

    return JSONResponse({
        "success": True,
        "task_id": task_id,
        "status": "PENDING",
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
        } if task_data["status"] == "DONE" else None,
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


@router.get("/cover-proxy", summary="封面图代理（弃用，请使用 /api/v1/proxy/image）")
async def cover_proxy(url: str):
    """后端代理请求封面图，解决浏览器直接加载 B站 CDN 的跨域限制。
    已弃用，重定向到通用代理接口 /api/v1/proxy/image"""
    from fastapi.responses import RedirectResponse
    if not url:
        raise HTTPException(status_code=400, detail="url 参数不能为空")
    return RedirectResponse(url=f"/api/v1/proxy/image?url={url}")
