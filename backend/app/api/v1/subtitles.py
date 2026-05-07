"""
YLCraft — 字幕管理 API

POST /api/v1/subtitles/extract          — 提交视频字幕提取任务（后台运行）
GET  /api/v1/subtitles/tasks/{task_id}  — 查询提取任务状态
GET  /api/v1/subtitles/{subtitle_id}    — 下载字幕文件
POST /api/v1/subtitles/burn             — 烧录字幕到视频
GET  /api/v1/subtitles/styles           — 获取可用字幕样式
DELETE /api/v1/subtitles/{subtitle_id}  — 删除字幕文件
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.services.subtitle.service import subtitle_service
from app.services.ffmpeg_service import FFmpegService

router = APIRouter()
logger = logging.getLogger("ylcraft.subtitles")

# 内存任务表 { task_id -> {...} }
_subtitle_tasks: dict[str, dict] = {}

# FFmpeg 服务
_ffmpeg = FFmpegService()


# ────────────────────────── 请求 / 响应模型 ──────────────────────────

class ExtractRequest(BaseModel):
    video_path: str
    language: str = "zh"               # zh / en / ja / ko / auto
    model_size: str = "medium"          # tiny / base / small / medium / large
    output_format: str = "srt"          # srt / ass / vtt
    word_timestamps: bool = False
    subtitle_style: str = "tiktok"      # tiktok / minimal / bold / cinematic


class BurnRequest(BaseModel):
    video_path: str
    subtitle_path: str
    output_path: Optional[str] = None
    style: str = "tiktok"               # 仅 ASS 格式有效（SRT 用此参数自动转 ASS）


# ────────────────────────── 后台任务执行 ──────────────────────────

async def _run_extract_task(task_id: str, req: ExtractRequest):
    """在后台执行字幕提取"""
    task = _subtitle_tasks[task_id]
    task["status"] = "running"
    task["progress"] = 0.0
    task["message"] = "开始转录..."

    def _progress(p: float, msg: str):
        task["progress"] = p
        task["message"] = msg

    result = await subtitle_service.extract(
        video_path=Path(req.video_path),
        language=req.language,
        model_size=req.model_size,
        output_format=req.output_format,
        word_timestamps=req.word_timestamps,
        subtitle_style=req.subtitle_style,
        on_progress=_progress,
    )

    if result["success"]:
        task["status"] = "completed"
        task["progress"] = 1.0
        task["message"] = "字幕提取完成"
        task["result"] = result
    else:
        task["status"] = "failed"
        task["message"] = result.get("error", "未知错误")
        task["result"] = result

    task["finished_at"] = time.time()


# ────────────────────────── API 端点 ──────────────────────────

@router.get("/styles", summary="获取可用字幕样式列表")
async def list_subtitle_styles():
    """返回所有可用字幕样式预设"""
    return {"success": True, "styles": subtitle_service.get_styles()}


@router.post("/extract", summary="提交字幕提取任务")
async def extract_subtitles(req: ExtractRequest, background_tasks: BackgroundTasks):
    """
    提交视频字幕提取任务（异步后台执行）。
    返回 task_id，通过 /tasks/{task_id} 轮询状态。
    """
    # 验证文件存在
    if not Path(req.video_path).exists():
        raise HTTPException(status_code=400, detail=f"视频文件不存在: {req.video_path}")

    task_id = uuid.uuid4().hex
    _subtitle_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "message": "任务已提交，等待处理...",
        "video_path": req.video_path,
        "created_at": time.time(),
        "result": None,
    }

    background_tasks.add_task(_run_extract_task, task_id, req)

    return {"success": True, "task_id": task_id, "message": "字幕提取任务已提交"}


@router.get("/tasks/{task_id}", summary="查询提取任务状态")
async def get_subtitle_task(task_id: str):
    """轮询字幕提取任务状态"""
    task = _subtitle_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return task


@router.get("/tasks", summary="列出所有字幕任务")
async def list_subtitle_tasks():
    """列出所有字幕提取任务"""
    tasks = sorted(_subtitle_tasks.values(), key=lambda t: t["created_at"], reverse=True)
    return {"success": True, "tasks": tasks[:50]}  # 最多返回 50 条


@router.get("/{subtitle_id}/download", summary="下载字幕文件")
async def download_subtitle(subtitle_id: str):
    """根据 subtitle_id 下载字幕文件"""
    # 从任务表中查找 subtitle_id
    for task in _subtitle_tasks.values():
        result = task.get("result")
        if result and result.get("subtitle_id") == subtitle_id:
            subtitle_path = result.get("subtitle_path")
            if subtitle_path and Path(subtitle_path).exists():
                return FileResponse(
                    path=subtitle_path,
                    filename=Path(subtitle_path).name,
                    media_type="text/plain",
                )
            raise HTTPException(status_code=404, detail="字幕文件已被删除")

    raise HTTPException(status_code=404, detail=f"字幕不存在: {subtitle_id}")


@router.post("/burn", summary="烧录字幕到视频")
async def burn_subtitle(req: BurnRequest, background_tasks: BackgroundTasks):
    """
    将字幕文件烧录到视频（硬字幕）。
    - SRT 文件：直接烧录（FFmpeg drawtext/subtitles filter）
    - ASS 文件：包含样式信息，原生支持

    返回烧录后的视频文件路径。
    """
    video_path = Path(req.video_path)
    subtitle_path = Path(req.subtitle_path)

    if not video_path.exists():
        raise HTTPException(status_code=400, detail=f"视频文件不存在: {req.video_path}")
    if not subtitle_path.exists():
        raise HTTPException(status_code=400, detail=f"字幕文件不存在: {req.subtitle_path}")

    # 生成输出文件路径
    if req.output_path:
        output_path = Path(req.output_path)
    else:
        output_path = video_path.parent / f"{video_path.stem}_subtitled{video_path.suffix}"

    # 调用 FFmpegService 烧录字幕
    task_id = uuid.uuid4().hex
    _subtitle_tasks[f"burn_{task_id}"] = {
        "task_id": f"burn_{task_id}",
        "status": "running",
        "progress": 0.0,
        "message": "正在烧录字幕...",
        "video_path": str(video_path),
        "created_at": time.time(),
        "type": "burn",
    }

    async def _do_burn():
        task = _subtitle_tasks[f"burn_{task_id}"]
        try:
            result = await _ffmpeg.add_subtitles(
                video_path=video_path,
                subtitle_path=subtitle_path,
                output_path=output_path,
            )
            task["status"] = "completed"
            task["progress"] = 1.0
            task["message"] = "字幕烧录完成"
            task["result"] = {"success": True, "output_path": str(output_path)}
        except Exception as e:
            task["status"] = "failed"
            task["message"] = str(e)
            task["result"] = {"success": False, "error": str(e)}
        task["finished_at"] = time.time()

    background_tasks.add_task(_do_burn)

    return {
        "success": True,
        "task_id": f"burn_{task_id}",
        "message": "字幕烧录任务已提交",
        "output_path": str(output_path),
    }


@router.delete("/{subtitle_id}", summary="删除字幕文件")
async def delete_subtitle(subtitle_id: str):
    """根据 subtitle_id 删除字幕文件及其任务记录"""
    for task_id, task in list(_subtitle_tasks.items()):
        result = task.get("result")
        if result and result.get("subtitle_id") == subtitle_id:
            subtitle_path = result.get("subtitle_path")
            if subtitle_path:
                subtitle_service.delete_subtitle(subtitle_path)
            del _subtitle_tasks[task_id]
            return {"success": True, "message": "字幕已删除"}

    raise HTTPException(status_code=404, detail=f"字幕不存在: {subtitle_id}")
