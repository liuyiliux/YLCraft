"""
YLCraft — 视频生成 API

POST /api/v1/videos/generate — 调用视频生成后端生成视频
GET  /api/v1/videos/backends — 可用的视频后端列表
GET  /api/v1/videos/tasks/:task_id — 查询任务状态
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import mimetypes
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import select

from app.db.database import get_async_session
from app.db.models.asset_hub import AssetRepresentation, AssetVersion
from app.db.models.creative_project import CreativeProject, ProjectAssetLink, ProjectContent
from app.db.models.task import VideoGenerationTask
from app.services.asset_hub import AssetHubFacade
from app.services.ai import get_ai_service
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
    reference_asset_ids: list[str] = Field(default_factory=list)
    project_id: Optional[str] = None
    content_id: Optional[str] = None
    chapter_number: Optional[int] = None
    source_index: Optional[str] = None
    source_type: Optional[str] = None
    source_title: Optional[str] = None
    generate_audio: Optional[bool] = True
    music_hint: Optional[str] = None


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
    model: str = ""
    asset_id: Optional[str] = None
    project_id: Optional[str] = None
    content_id: Optional[str] = None
    source_type: Optional[str] = None
    source_index: Optional[str] = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
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
    asset_id: Optional[str] = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class VideoTaskListResponse(BaseModel):
    success: bool = True
    data: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


async def _resolve_asset_paths(session, asset_ids: list[str]) -> dict[str, Path]:
    """Resolve Asset Hub node ids to their latest local file representations."""
    ids = list(dict.fromkeys(str(item).strip() for item in asset_ids if str(item).strip()))
    if not ids:
        return {}

    rows = await session.execute(
        select(
            AssetVersion.asset_node_id,
            AssetVersion.version_number,
            AssetRepresentation.file_path,
            AssetRepresentation.mime_type,
        )
        .join(AssetRepresentation, AssetRepresentation.asset_version_id == AssetVersion.id)
        .where(AssetVersion.asset_node_id.in_(ids))
        .order_by(AssetVersion.version_number.desc())
    )
    resolved: dict[str, Path] = {}
    for asset_id, _version, file_path, mime_type in rows.all():
        path = Path(str(file_path))
        if str(mime_type or "").startswith("image/") and str(asset_id) not in resolved and path.is_file():
            resolved[str(asset_id)] = path
    return resolved


def _materialize_data_uri(value: str) -> tuple[Path | None, Path | None]:
    """Turn a browser-uploaded data URI into a short-lived local file."""
    if not value.startswith("data:") or ";base64," not in value:
        return None, None
    header, encoded = value.split(";base64,", 1)
    mime = header[5:] or "image/png"
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("start_image is not a valid base64 data URI") from exc

    suffix = mimetypes.guess_extension(mime) or ".png"
    directory = Path(__file__).resolve().parents[3] / "storage" / "video_inputs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}{suffix}"
    path.write_bytes(payload)
    return path, path


def _request_context(req: VideoGenerateRequest, reference_asset_ids: list[str]) -> dict[str, Any]:
    return {
        "prompt": req.prompt,
        "duration": req.duration or 5,
        "resolution": req.resolution or "720p",
        "aspect_ratio": req.aspect_ratio or "9:16",
        "seed": req.seed,
        "generate_audio": req.generate_audio if req.generate_audio is not None else True,
        "music_hint": req.music_hint or "",
        "reference_asset_ids": reference_asset_ids,
        "project_id": req.project_id or "",
        "content_id": req.content_id or "",
        "chapter_number": req.chapter_number,
        "source_type": req.source_type or "",
        "source_index": req.source_index or "",
        "source_title": req.source_title or "",
    }


def _result_payload(result: Any) -> dict[str, Any]:
    return {
        "url": result.url or "",
        "local_path": str(result.video_path) if result.video_path else "",
        "duration": result.duration_seconds,
        "seed": result.seed,
        "cost": result.cost,
        "diagnostics": getattr(result, "diagnostics", {}) or {},
    }


def _task_to_dict(task: VideoGenerationTask) -> dict[str, Any]:
    try:
        request_data = json.loads(task.request_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        request_data = {}
    try:
        result_data = json.loads(task.result_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        result_data = {}
    return {
        "task_id": task.task_id,
        "provider": task.provider,
        "model": task.model,
        "status": task.status,
        "prompt": task.prompt,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "asset_id": task.asset_id,
        "project_id": task.project_id,
        "content_id": task.content_id,
        "error": task.error,
        "created_at": task.created_at,
        "request": request_data,
        "result": result_data,
    }


async def _persist_video_result(
    *,
    result: Any,
    context: dict[str, Any],
    existing_asset_id: str | None = None,
) -> str | None:
    """Import a locally materialized result exactly once and restore project lineage."""
    if existing_asset_id or not result.video_path:
        return existing_asset_id

    source_metadata = {
        "source": "video_generation",
        "prompt": context["prompt"],
        "provider": result.provider,
        "model": result.model,
        "task_id": result.task_id,
        "duration": result.duration_seconds,
        "seed": result.seed,
        "resolution": context["resolution"],
        "aspect_ratio": context["aspect_ratio"],
        "generate_audio": context["generate_audio"],
        "music_hint": context["music_hint"],
        "reference_asset_ids": context["reference_asset_ids"],
        "project_id": context["project_id"],
        "content_id": context["content_id"],
        "chapter_number": context["chapter_number"],
        "source_type": context["source_type"],
        "source_index": context["source_index"],
        "source_title": context["source_title"],
    }
    async with get_async_session() as session:
        created = await AssetHubFacade(session).create_imported_file(
            file_path=str(result.video_path),
            title=context["source_title"] or context["prompt"] or Path(result.video_path).stem,
            asset_type="video",
            source="video_generation",
            source_url=result.url or "",
            metadata=source_metadata,
            lineage={
                "source": "video_generation",
                "prompt": context["prompt"],
                "provider": result.provider,
                "model": result.model,
                "task_id": result.task_id,
                "reference_asset_ids": context["reference_asset_ids"],
                "project_id": context["project_id"],
                "content_id": context["content_id"],
                "source_type": context["source_type"],
                "source_index": context["source_index"],
            },
            tags=["ai-generated", "video-generation", result.provider or "", result.model or ""],
        )
        asset_id = created.node_id
        if context["project_id"]:
            project = await session.get(CreativeProject, context["project_id"])
            if project is None:
                raise ValueError(f"Project not found for generated video: {context['project_id']}")
            if context["content_id"]:
                content = await session.get(ProjectContent, context["content_id"])
                if content is None or content.project_id != context["project_id"]:
                    raise ValueError(f"Project content not found for generated video: {context['content_id']}")
            session.add(ProjectAssetLink(
                project_id=context["project_id"],
                asset_id=asset_id,
                content_id=context["content_id"] or None,
                role="output",
                relation="derived_from",
                metadata_json=json.dumps(source_metadata, ensure_ascii=False),
            ))
    logger.info("Video saved to Asset Hub: %s", result.video_path)
    return asset_id


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

    default_backend = manager.get_default(MediaType.VIDEO)
    return VideoBackendsResponse(
        success=True,
        backends=info_list,
        default=default_backend.name if default_backend else None,
    )


@router.post("/generate", response_model=VideoResponse, summary="Generate video with optional project lineage")
async def generate_video(req: VideoGenerateRequest):
    """
    调用视频生成后端生成视频。
    自动选择默认后端或指定 provider。
    """
    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    transient_start_image: Path | None = None
    try:
        async with get_async_session() as session:
            reference_paths = await _resolve_asset_paths(session, req.reference_asset_ids)

        start_image: Path | None = None
        if req.start_image:
            start_image, transient_start_image = _materialize_data_uri(req.start_image)
            if start_image is None:
                candidate = Path(req.start_image)
                if candidate.is_file():
                    start_image = candidate
                else:
                    raise ValueError("start_image must be a local path or a base64 data URI")
        if start_image is None and reference_paths:
            start_image = next(iter(reference_paths.values()))

        video_req = VideoGenerationRequest(
            prompt=req.prompt,
            duration=req.duration or 5,
            resolution=req.resolution or "720p",
            aspect_ratio=req.aspect_ratio or "9:16",
            provider=req.provider or "",
            model=req.model or "",
            seed=req.seed,
            generate_audio=req.generate_audio if req.generate_audio is not None else True,
            start_image=start_image,
            reference_images=list(reference_paths.values()) or None,
            await_completion=False,
        )
        result = await manager.generate_video(video_req)

        # A failed submission has no provider task id, but it still needs a
        # durable local ID so the complete request/response diagnostics survive.
        if not result.task_id:
            result.task_id = f"video_{uuid4().hex}"
        result.provider = result.provider or req.provider or ""
        result.model = result.model or req.model or ""

        context = _request_context(req, list(reference_paths))
        asset_id: str | None = None
        if result.success and result.video_path:
            try:
                asset_id = await _persist_video_result(result=result, context=context)
            except Exception as exc:
                logger.warning("Failed to persist generated video context: %s", exc)

        if result.task_id:
            async with get_async_session() as session:
                task = await session.get(VideoGenerationTask, result.task_id)
                if task is None:
                    task = VideoGenerationTask(task_id=result.task_id)
                    session.add(task)
                task.provider = result.provider or req.provider or ""
                task.model = result.model or req.model or ""
                task.status = (result.status or "pending") if result.success else "error"
                task.prompt = req.prompt
                task.request_json = json.dumps(context, ensure_ascii=False)
                task.result_json = json.dumps(_result_payload(result), ensure_ascii=False)
                task.asset_id = asset_id
                task.project_id = req.project_id or None
                task.content_id = req.content_id or None
                task.error = result.error or None
                task.progress = result.progress or (100 if result.status == "done" else 0)
                task.progress_message = result.progress_message or ""
                task.updated_at = time.time()
                task.completed_at = time.time() if task.status in {"done", "error"} else None

        if not result.success:
            return VideoResponse(
                success=False,
                task_id=result.task_id,
                status="error",
                provider=result.provider,
                model=result.model,
                diagnostics=getattr(result, "diagnostics", {}) or {},
                error=result.error or "Video provider request failed",
            )

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
            model=result.model,
            asset_id=asset_id,
            project_id=req.project_id,
            content_id=req.content_id,
            source_type=req.source_type,
            source_index=req.source_index,
            diagnostics=getattr(result, "diagnostics", {}) or {},
        )
    except Exception as e:
        logger.error(f"Video generation failed: {e}")
        return VideoResponse(success=False, error=str(e))
    finally:
        if transient_start_image is not None:
            transient_start_image.unlink(missing_ok=True)


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
        async with get_async_session() as session:
            task = await session.get(VideoGenerationTask, task_id)

        if task is None and not provider:
            return TaskStatusResponse(
                success=False,
                task_id=task_id,
                status="error",
                error="Unknown video task; submit it through the video workspace before polling.",
            )

        result = await manager.poll_video(provider or (task.provider if task else None), task_id)
        if task:
            result.provider = result.provider or task.provider
            result.model = result.model or task.model
        asset_id = task.asset_id if task else None
        if result.status == "done" and result.video_path and task:
            try:
                context = json.loads(task.request_json or "{}")
                asset_id = await _persist_video_result(result=result, context=context, existing_asset_id=asset_id)
            except Exception as exc:
                logger.warning("Failed to import completed video task %s: %s", task_id, exc)

        if task:
            async with get_async_session() as session:
                persisted = await session.get(VideoGenerationTask, task_id)
                if persisted:
                    persisted.provider = result.provider or persisted.provider
                    persisted.model = result.model or persisted.model
                    persisted.status = result.status or persisted.status
                    persisted.result_json = json.dumps(_result_payload(result), ensure_ascii=False)
                    persisted.asset_id = asset_id
                    persisted.error = result.error or None
                    persisted.progress = result.progress or (100 if result.status == "done" else 0)
                    persisted.progress_message = result.progress_message or ""
                    persisted.updated_at = time.time()
                    persisted.completed_at = time.time() if result.status == "done" else persisted.completed_at
        return TaskStatusResponse(
            success=result.success,
            task_id=result.task_id,
            status=result.status,
            progress=result.progress,
            progress_message=result.progress_message,
            url=result.url,
            local_path=str(result.video_path) if result.video_path else None,
            asset_id=asset_id,
            diagnostics=getattr(result, "diagnostics", {}) or {},
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


@router.get("/history", response_model=VideoTaskListResponse, summary="视频生成历史与待处理任务")
async def list_video_tasks(
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    """Return durable workspace history so refresh never loses submitted video jobs."""
    async with get_async_session() as session:
        statement = select(VideoGenerationTask)
        if status:
            statement = statement.where(VideoGenerationTask.status == status)
        if project_id:
            statement = statement.where(VideoGenerationTask.project_id == project_id)
        statement = statement.order_by(VideoGenerationTask.created_at.desc()).limit(limit)
        rows = (await session.execute(statement)).scalars().all()
    return VideoTaskListResponse(data=[_task_to_dict(item) for item in rows], total=len(rows))
