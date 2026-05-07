"""
YLCraft — Clip Lab NarratoAI / MoE API

POST /api/v1/clip/narrato     — NarratoAI Pipeline 视频剪辑
POST /api/v1/clip/moe        — MoE 多专家协作剪辑
GET  /api/v1/clip/tasks/{id} — 任务状态查询
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.clip import (
    NarratoService,
    get_narrato_service,
    MoEService,
    get_moe_service,
)

router = APIRouter()
logger = logging.getLogger("ylcraft.clip")


# =============================================================================
# 请求/响应模型
# =============================================================================

class NarratoRequest(BaseModel):
    """NarratoAI Pipeline 请求"""
    video_path: str = Field(..., description="输入视频路径（绝对路径或 uploads 相对路径）")
    output_dir: Optional[str] = Field(None, description="输出目录（可选，默认临时目录）")
    target_duration: float = Field(60.0, ge=5, le=600, description="目标输出时长（秒）")
    num_clips: int = Field(5, ge=1, le=20, description="目标片段数量")
    min_clip_duration: float = Field(3.0, ge=1, description="最小片段时长（秒）")
    max_clip_duration: float = Field(15.0, ge=3, description="最大片段时长（秒）")


class NarratoResponse(BaseModel):
    success: bool
    task_id: str
    message: str


class MoeRequest(BaseModel):
    """MoE 多专家协作请求"""
    video_path: str = Field(..., description="输入视频路径")
    output_dir: Optional[str] = Field(None, description="输出目录（可选）")
    target_duration: float = Field(60.0, ge=5, le=600, description="目标输出时长（秒）")


class MoeResponse(BaseModel):
    success: bool
    task_id: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str          # pending / running / done / failed
    progress: int        # 0-100
    progress_message: str
    result: Optional[dict] = None
    error: Optional[str] = None


# =============================================================================
# API 路由
# =============================================================================

@router.post("/narrato", response_model=NarratoResponse, summary="NarratoAI Pipeline 剪辑")
async def narrato_clip(request: NarratoRequest):
    """
    NarratoAI Pipeline 视频剪辑。

    工作流程：
    1. 自动 OST 类型分类（TYPE_0/1/2）
    2. 音频节拍分析 / 场景检测
    3. 关键帧 VLM 美学评分
    4. 智能选段 + FFmpeg 合成

    返回 task_id，前端轮询 GET /api/v1/clip/tasks/{task_id} 查询进度。
    """
    try:
        from app.services.clip.narrato_service import NarratoConfig

        service = get_narrato_service()
        config = NarratoConfig(
            target_duration=request.target_duration,
            num_clips=request.num_clips,
            min_clip_duration=request.min_clip_duration,
            max_clip_duration=request.max_clip_duration,
        )

        task_id = await service.start_clip_task(
            video_path=request.video_path,
            output_dir=request.output_dir,
            config=config,
        )

        return NarratoResponse(
            success=True,
            task_id=task_id,
            message=f"NarratoAI Pipeline 任务已启动（task_id: {task_id}）",
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"NarratoAI start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/moe", response_model=MoeResponse, summary="MoE 多专家协作剪辑")
async def moe_clip(request: MoeRequest):
    """
    MoE 多专家协作视频剪辑。

    三专家并行分析：
    - BeatExpert（节拍专家）：音频节奏踩点
    - CompositionExpert（构图专家）：画面美学评分
    - NarrativeExpert（叙事专家）：内容叙事结构

    ControlPlane 整合三专家输出，输出最优剪辑方案。

    返回 task_id，前端轮询查询进度。
    """
    try:
        service = get_moe_service()
        task_id = await service.start_moe_task(
            video_path=request.video_path,
            target_duration=request.target_duration,
            output_dir=request.output_dir,
        )

        return MoeResponse(
            success=True,
            task_id=task_id,
            message=f"MoE 多专家任务已启动（task_id: {task_id}）",
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"MoE start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse, summary="查询 Clip Lab 任务状态")
async def get_clip_task_status(task_id: str):
    """
    查询 NarratoAI / MoE 任务状态。

    轮询建议：每 2-3 秒轮询一次，直到 status 变为 done 或 failed。
    """
    # 同时检查两个服务的任务状态
    for service_name, service in [("NarratoAI", get_narrato_service()), ("MoE", get_moe_service())]:
        status = await service.get_task_status(task_id)
        if "error" not in status:
            return TaskStatusResponse(**status)

    raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")


@router.get("/download", summary="下载剪辑结果视频")
async def download_clip_result(file_path: str = Query(..., description="文件绝对路径")):
    """
    下载剪辑结果视频文件。
    """
    p = Path(file_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

    return FileResponse(
        path=str(p),
        filename=p.name,
        media_type="video/mp4",
    )
