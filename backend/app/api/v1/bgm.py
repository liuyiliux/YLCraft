"""
YLCraft — BGM 配乐 API

GET    /api/v1/bgm/library          — BGM 曲目库列表
GET    /api/v1/bgm/genres           — 风格分类列表
GET    /api/v1/bgm/moods            — 情绪分类列表
GET    /api/v1/bgm/{track_id}       — 曲目详情
GET    /api/v1/bgm/{track_id}/file  — 获取音频文件（用于前端预览播放）
POST   /api/v1/bgm/upload           — 上传自定义 BGM
POST   /api/v1/bgm/mix              — 将 BGM 混音到视频（后台任务）
GET    /api/v1/bgm/tasks/{task_id}  — 混音任务状态
DELETE /api/v1/bgm/{track_id}       — 删除自定义曲目
PATCH  /api/v1/bgm/{track_id}/favorite — 切换收藏
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.services.bgm.service import bgm_service
from app.services.video.ffmpeg import FFmpegService

router = APIRouter()
logger = logging.getLogger("ylcraft.bgm")

_ffmpeg = FFmpegService()

# 内存混音任务表
_mix_tasks: dict[str, dict] = {}

# BGM 上传目录
_upload_dir = Path("data/bgm/uploads")
_upload_dir.mkdir(parents=True, exist_ok=True)


# ────────────────────────── 请求模型 ──────────────────────────

class BGMMixRequest(BaseModel):
    video_path: str
    bgm_track_id: str
    bgm_volume: float = 0.3           # BGM 音量（0.0 ~ 1.0）
    original_volume: float = 1.0      # 原视频音量
    fade_in: float = 0.0              # BGM 淡入时长（秒）
    fade_out: float = 2.0             # BGM 淡出时长（秒）
    loop: bool = True                 # BGM 是否循环（短于视频时）
    output_path: Optional[str] = None


# ────────────────────────── 后台混音任务 ──────────────────────────

async def _run_mix_task(task_id: str, req: BGMMixRequest, track: dict):
    """在后台执行 BGM 混音"""
    task = _mix_tasks[task_id]
    task["status"] = "running"
    task["message"] = "开始混音..."

    try:
        video_path = Path(req.video_path)
        bgm_path = Path(track["file_path"])
        output_path = Path(req.output_path) if req.output_path else (
            video_path.parent / f"{video_path.stem}_bgm{video_path.suffix}"
        )

        # 验证文件
        if not bgm_path.exists():
            raise FileNotFoundError(f"BGM 文件不存在: {bgm_path}")

        task["message"] = "正在生成混音滤镜..."
        task["progress"] = 0.2

        # 构建 FFmpeg filter_complex 命令
        filter_complex = _build_mix_filter(
            bgm_volume=req.bgm_volume,
            original_volume=req.original_volume,
            fade_in=req.fade_in,
            fade_out=req.fade_out,
            loop=req.loop,
        )

        import subprocess
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-stream_loop", "-1" if req.loop else "0",   # BGM 循环
            "-i", str(bgm_path),
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[mixed]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",                                  # 以最短流为准（防止 BGM 无限延长）
            str(output_path),
        ]

        task["message"] = "FFmpeg 混音中..."
        task["progress"] = 0.5

        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg 混音失败: {result.stderr[-500:]}")

        task["status"] = "completed"
        task["progress"] = 1.0
        task["message"] = "混音完成"
        task["result"] = {
            "success": True,
            "output_path": str(output_path),
        }

    except Exception as e:
        logger.exception(f"BGM 混音失败: {e}")
        task["status"] = "failed"
        task["message"] = str(e)
        task["result"] = {"success": False, "error": str(e)}

    task["finished_at"] = time.time()


def _build_mix_filter(
    bgm_volume: float,
    original_volume: float,
    fade_in: float,
    fade_out: float,
    loop: bool,
) -> str:
    """构建 FFmpeg filter_complex 字符串"""
    parts = []

    # 原始音频音量调节
    parts.append(f"[0:a]volume={original_volume}[a0]")

    # BGM 音量 + 淡入淡出
    bgm_filter = f"[1:a]volume={bgm_volume}"
    if fade_in > 0:
        bgm_filter += f",afade=t=in:st=0:d={fade_in}"
    if fade_out > 0:
        bgm_filter += f",afade=t=out:st=9999:d={fade_out}"  # 9999 表示"接近结尾"
    bgm_filter += "[a1]"
    parts.append(bgm_filter)

    # 混合两路音频
    parts.append("[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[mixed]")

    return ";".join(parts)


# ────────────────────────── API 端点 ──────────────────────────

@router.get("/library", summary="BGM 曲目库列表")
async def list_bgm_library(
    genre: Optional[str] = None,
    mood: Optional[str] = None,
    search: Optional[str] = None,
    include_unavailable: bool = True,
):
    """列出 BGM 曲目库，支持按风格/情绪过滤"""
    tracks = bgm_service.list_tracks(
        genre=genre,
        mood=mood,
        search=search,
        include_unavailable=include_unavailable,
    )
    return {"success": True, "total": len(tracks), "tracks": tracks}


@router.get("/genres", summary="风格分类列表")
async def list_genres():
    return {"success": True, "genres": bgm_service.get_genres()}


@router.get("/moods", summary="情绪分类列表")
async def list_moods():
    return {"success": True, "moods": bgm_service.get_moods()}


@router.get("/tasks/{task_id}", summary="查询混音任务状态")
async def get_mix_task(task_id: str):
    task = _mix_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task


@router.post("/upload", summary="上传自定义 BGM")
async def upload_bgm(
    file: UploadFile = File(...),
    name: str = Form(...),
    artist: str = Form(""),
    genre: str = Form("other"),
    mood: str = Form("neutral"),
    bpm: int = Form(0),
):
    """上传自定义 BGM 文件"""
    # 验证文件类型
    allowed_types = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/flac", "audio/ogg"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file.content_type}")

    # 保存文件
    file_ext = Path(file.filename or "track.mp3").suffix or ".mp3"
    saved_name = f"custom_{uuid.uuid4().hex[:12]}{file_ext}"
    saved_path = _upload_dir / saved_name

    content = await file.read()
    saved_path.write_bytes(content)

    # 获取音频时长
    duration = await bgm_service.get_audio_duration(str(saved_path))

    # 注册到曲目库
    track = bgm_service.add_track(
        file_path=str(saved_path),
        name=name,
        artist=artist,
        genre=genre,
        mood=mood,
        bpm=bpm,
        duration=duration,
        license_info="用户上传",
    )

    return {"success": True, "track": track, "message": f"BGM '{name}' 上传成功"}


@router.post("/mix", summary="将 BGM 混音到视频")
async def mix_bgm(req: BGMMixRequest, background_tasks: BackgroundTasks):
    """提交 BGM 混音任务（异步后台执行）"""
    # 验证文件
    if not Path(req.video_path).exists():
        raise HTTPException(status_code=400, detail=f"视频文件不存在: {req.video_path}")

    track = bgm_service.get_track(req.bgm_track_id)
    if not track:
        raise HTTPException(status_code=404, detail=f"BGM 曲目不存在: {req.bgm_track_id}")

    if not track.get("available") and not Path(track["file_path"]).exists():
        raise HTTPException(
            status_code=400,
            detail=f"BGM 文件不存在: {track['file_path']}（内置示例曲目需要手动放置音频文件）"
        )

    task_id = uuid.uuid4().hex
    _mix_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "message": "任务已提交...",
        "video_path": req.video_path,
        "bgm_name": track["name"],
        "created_at": time.time(),
        "result": None,
    }

    background_tasks.add_task(_run_mix_task, task_id, req, track)

    output_path = req.output_path or str(
        Path(req.video_path).parent / f"{Path(req.video_path).stem}_bgm{Path(req.video_path).suffix}"
    )

    return {
        "success": True,
        "task_id": task_id,
        "message": f"BGM 混音任务已提交（{track['name']}）",
        "output_path": output_path,
    }


@router.get("/{track_id}/file", summary="获取 BGM 音频文件")
async def get_bgm_file(track_id: str):
    """返回 BGM 音频文件（用于前端 <audio> 预览播放）"""
    track = bgm_service.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail=f"曲目不存在: {track_id}")

    file_path = Path(track["file_path"])
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="音频文件不存在（内置示例曲目需要手动放置音频文件）"
        )

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=file_path.name,
    )


@router.patch("/{track_id}/favorite", summary="切换收藏状态")
async def toggle_favorite(track_id: str):
    """切换 BGM 曲目的收藏状态"""
    track = bgm_service.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail=f"曲目不存在: {track_id}")

    is_fav = bgm_service.toggle_favorite(track_id)
    return {"success": True, "is_favorite": is_fav}


@router.get("/{track_id}", summary="曲目详情")
async def get_bgm_track(track_id: str):
    """获取 BGM 曲目详情"""
    track = bgm_service.get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail=f"曲目不存在: {track_id}")
    return {"success": True, "track": track}


@router.delete("/{track_id}", summary="删除自定义曲目")
async def delete_bgm_track(track_id: str):
    """删除自定义上传的 BGM 曲目（内置曲目不可删除）"""
    try:
        success = bgm_service.delete_track(track_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"曲目不存在: {track_id}")
        return {"success": True, "message": "曲目已删除"}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
