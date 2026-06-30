"""
YLCraft — 视频生成 API

POST /api/v1/videos/generate — 调用视频生成后端生成视频
GET  /api/v1/videos/backends — 可用的视频后端列表
GET  /api/v1/videos/tasks/:task_id — 查询任务状态
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.ai import get_ai_service, AIService
from app.services.ai.types import VideoGenerationRequest

router = APIRouter()
logger = logging.getLogger("ylcraft.videos")


class VideoGenerateRequest(BaseModel):
    prompt: str
    duration: Optional[int] = 5
    resolution: Optional[str] = "720p"
    aspect_ratio: Optional[str] = "9:16"
    provider: Optional[str] = None
    model: Optional[str] = None  # 动态选择模型
    seed: Optional[int] = None
    start_image: Optional[str] = None  # 首帧图片路径
    generate_audio: Optional[bool] = True


class VideoResponse(BaseModel):
    success: bool
    task_id: Optional[str] = None
    url: Optional[str] = None
    local_path: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    progress_message: Optional[str] = None
    cost: float = 0.0
    provider: str = ""
    error: Optional[str] = None


class BackendInfo(BaseModel):
    name: str
    model: str
    available_models: list[str] = []  # 支持的模型列表
    capabilities: list[str]


class VideoBackendsResponse(BaseModel):
    success: bool = True
    backends: list[BackendInfo] = []
    default: Optional[str] = None


class TaskStatusResponse(BaseModel):
    success: bool = True
    task_id: str
    status: str
    progress: int = 0
    progress_message: str = ""
    url: Optional[str] = None
    local_path: Optional[str] = None
    error: Optional[str] = None


@router.get("/backends", response_model=VideoBackendsResponse, summary="可用视频后端列表")
async def list_backends():
    """返回所有已注册的视频生成后端"""
    manager = get_ai_service()
    if not manager.is_loaded():
        return VideoBackendsResponse(success=False, backends=[], default=None)

    from app.services.ai.types import MediaType
    keys = manager.list_backends(MediaType.VIDEO)
    info_list = []
    for key in keys:
        b = manager.get_backend(MediaType.VIDEO, key)
        if b:
            info_list.append(BackendInfo(
                name=b.name,
                model=b.model,
                available_models=getattr(b, 'available_models', [b.model]),
                capabilities=list(b.capabilities),
            ))

    return VideoBackendsResponse(
        success=True,
        backends=info_list,
        default=manager.get_default(MediaType.VIDEO),
    )


@router.post("/generate", response_model=VideoResponse, summary="生成视频")
async def generate_video(req: VideoGenerateRequest):
    """
    调用视频生成后端生成视频。
    自动选择默认后端或指定 provider。
    """
    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    try:
        video_req = VideoGenerationRequest(
            prompt=req.prompt,
            duration=req.duration or 5,
            resolution=req.resolution or "720p",
            aspect_ratio=req.aspect_ratio or "9:16",
            provider=req.provider or "",
            model=req.model or "",  # 动态选择模型
            seed=req.seed,
            generate_audio=req.generate_audio or True,
            start_image=Path(req.start_image) if req.start_image else None,
        )
        result = await manager.generate_video(video_req)

        if result.success:
            # 自动入库到资产中枢
            if result.video_path:
                try:
                    from app.db.database import get_async_session
                    from app.db.models.asset_hub import AssetType
                    from app.services.asset_hub import AssetHubFacade
                    async with get_async_session() as session:
                        await AssetHubFacade(session).create_imported_file(
                            file_path=str(result.video_path),
                            title=req.prompt or Path(result.video_path).stem,
                            asset_type=AssetType.VIDEO,
                            source="video_generation",
                            source_url=result.url or "",
                            metadata={
                                "prompt": req.prompt,
                                "provider": result.provider,
                                "model": result.model,
                                "duration": result.duration_seconds,
                                "seed": result.seed,
                                "resolution": req.resolution or "720p",
                                "aspect_ratio": req.aspect_ratio or "9:16",
                                "generate_audio": req.generate_audio if req.generate_audio is not None else True,
                                "start_image": str(req.start_image) if req.start_image else "",
                                "reference_images": [str(p) for p in video_req.reference_images] if video_req.reference_images else [],
                            },
                            lineage={
                                "source": "video_generation",
                                "prompt": req.prompt,
                                "provider": result.provider,
                                "model": result.model,
                            },
                            tags=["ai-generated", result.provider or "", result.model or ""],
                        )
                    logger.info(f"Video saved to asset library: {result.video_path}")
                except Exception as e:
                    logger.warning(f"Failed to save video to asset library: {e}")

            return VideoResponse(
                success=True,
                task_id=result.task_id,
                url=result.url,
                local_path=str(result.video_path) if result.video_path else None,
                status=result.status,
                progress=result.progress,
                progress_message=result.progress_message,
                cost=result.cost,
                provider=result.provider,
            )
        else:
            return VideoResponse(success=False, error=result.error, provider=result.provider)
    except Exception as e:
        logger.error(f"Video generation failed: {e}")
        return VideoResponse(success=False, error=str(e))


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
async def get_task_status(task_id: str, provider: Optional[str] = None):
    """
    查询视频生成任务状态。
    用于轮询异步生成任务。
    """
    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    try:
        result = await manager.poll_video(provider, task_id)
        return TaskStatusResponse(
            success=result.success,
            task_id=result.task_id,
            status=result.status,
            progress=result.progress,
            progress_message=result.progress_message,
            url=result.url,
            local_path=str(result.video_path) if result.video_path else None,
            error=result.error,
        )
    except Exception as e:
        logger.error(f"Poll task failed: {e}")
        return TaskStatusResponse(
            success=False,
            task_id=task_id,
            status="error",
            error=str(e),
        )
