"""
YLCraft — 图像生成 API

POST /api/v1/images/generate — 调用图像生成后端生成图片
GET  /api/v1/images/backends — 可用的图像后端列表
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.task_queue import TaskStatus, get_task_queue
from app.db.models.asset_hub import AssetNode
from app.services.ai import get_ai_service, AIService
from app.services.ai.types import ImageGenerationRequest
from app.services.asset_hub.representation_service import AssetRepresentationService
from app.services.asset_hub.version_service import AssetVersionService

router = APIRouter()
logger = logging.getLogger("ylcraft.images")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response_excerpt(data: dict, limit: int = 1000) -> str:
    try:
        text = json.dumps(data, ensure_ascii=False)
    except Exception:
        text = str(data)
    if len(text) > limit:
        return text[:limit] + "...(truncated)"
    return text


async def _create_generated_image_asset_hub(
    session,
    *,
    image_path: str,
    prompt: str,
    provider: str,
    model: str,
    source_url: str = "",
    negative_prompt: str = "",
    size: str = "",
    seed: int | None = None,
    generation_params: dict | None = None,
    lineage: dict | None = None,
) -> str:
    from app.services.asset_hub import AssetHubFacade

    result = await AssetHubFacade(session).create_generated_image(
        file_path=image_path,
        prompt=prompt,
        provider=provider,
        model=model,
        source_url=source_url,
        negative_prompt=negative_prompt,
        size=size,
        seed=seed,
        generation_params=generation_params,
        lineage=lineage,
    )
    return result.node_id


class ImageGenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    size: Optional[str] = "1024x1024"
    style: Optional[str] = None
    n: Optional[int] = 1
    provider: Optional[str] = None
    model: Optional[str] = None  # 动态指定模型（控制花费）
    # 扩展参数
    seed: Optional[int] = None
    steps: Optional[int] = 20
    cfg_scale: Optional[float] = 7.0
    batch_size: Optional[int] = 1
    sampler: Optional[str] = "euler"
    source_image: Optional[str] = None
    reference_images: Optional[list[str]] = None  # 图生图参考图列表
    lora: Optional[str] = None
    controlnet: Optional[str] = None
    project_id: Optional[str] = None
    content_id: Optional[str] = None
    source_type: Optional[str] = None
    source_index: Optional[str] = None
    source_title: Optional[str] = None
    chapter_number: Optional[str] = None
    reference_asset_ids: Optional[list[str]] = None
    character_ids: Optional[list[str]] = None
    portrait_node_ids: Optional[list[str]] = None
    portrait_version_ids: Optional[list[str]] = None
    reference_image_collection: Optional[list[dict]] = None
    prompt_reference_id: Optional[str] = None
    prompt_reference_source_id: Optional[str] = None
    prompt_reference_title: Optional[str] = None
    prompt_reference_category: Optional[str] = None
    prompt_reference_source_url: Optional[str] = None


def _generation_lineage_from_request(req: ImageGenerateRequest, *, extra: dict | None = None) -> dict:
    lineage = {
        "project_id": req.project_id or "",
        "content_id": req.content_id or "",
        "source_type": req.source_type or "",
        "source_index": req.source_index or "",
        "source_title": req.source_title or "",
        "chapter_number": req.chapter_number or "",
        "reference_asset_ids": req.reference_asset_ids or [],
        "character_ids": req.character_ids or [],
        "portrait_node_ids": req.portrait_node_ids or [],
        "portrait_version_ids": req.portrait_version_ids or [],
        "reference_image_collection": req.reference_image_collection or [],
        "prompt_reference_id": req.prompt_reference_id or "",
        "prompt_reference_source_id": req.prompt_reference_source_id or "",
        "prompt_reference_title": req.prompt_reference_title or "",
        "prompt_reference_category": req.prompt_reference_category or "",
        "prompt_reference_source_url": req.prompt_reference_source_url or "",
        **(extra or {}),
    }
    return {key: value for key, value in lineage.items() if value not in (None, "", [])}


def _generation_lineage_from_payload(payload: dict, *, extra: dict | None = None) -> dict:
    lineage = {
        "project_id": payload.get("project_id", ""),
        "content_id": payload.get("content_id", ""),
        "source_type": payload.get("source_type", ""),
        "source_index": payload.get("source_index", ""),
        "source_title": payload.get("source_title", ""),
        "chapter_number": payload.get("chapter_number", ""),
        "reference_asset_ids": payload.get("reference_asset_ids") or [],
        "character_ids": payload.get("character_ids") or [],
        "portrait_node_ids": payload.get("portrait_node_ids") or [],
        "portrait_version_ids": payload.get("portrait_version_ids") or [],
        "reference_image_collection": payload.get("reference_image_collection") or [],
        "prompt_reference_id": payload.get("prompt_reference_id", ""),
        "prompt_reference_source_id": payload.get("prompt_reference_source_id", ""),
        "prompt_reference_title": payload.get("prompt_reference_title", ""),
        "prompt_reference_category": payload.get("prompt_reference_category", ""),
        "prompt_reference_source_url": payload.get("prompt_reference_source_url", ""),
        **(extra or {}),
    }
    return {key: value for key, value in lineage.items() if value not in (None, "", [])}


def _reference_images_from_collection(collection: list[dict] | None) -> list[str]:
    refs: list[str] = []
    for item in collection or []:
        if not isinstance(item, dict):
            continue
        value = (
            item.get("url")
            or item.get("image_url")
            or item.get("src")
            or item.get("data_url")
            or item.get("local_path")
            or item.get("path")
        )
        if value:
            refs.append(str(value))
    return refs


def _looks_like_image_path(path_value: str) -> bool:
    suffix = Path(path_value or "").suffix.lower()
    return suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _is_image_representation(rep) -> bool:
    mime_type = str(getattr(rep, "mime_type", "") or "").lower()
    return mime_type.startswith("image/") or _looks_like_image_path(getattr(rep, "file_path", "") or "")


async def _primary_image_path_for_asset(session, asset_id: str) -> str | None:
    node = await session.get(AssetNode, asset_id)
    if not node:
        return None
    node_meta = node.metadata_json if isinstance(node.metadata_json, dict) else {}
    if node_meta.get("deleted_at") or str(node_meta.get("status", "")).upper() == "DELETED":
        return None

    version = await AssetVersionService(session).get_latest_version(str(node.id))
    if not version:
        return None

    reps = await AssetRepresentationService(session).list_by_version(str(version.id))
    for rep in reps:
        if _is_image_representation(rep) and rep.file_path:
            return str(rep.file_path)
    return None


async def _reference_images_from_asset_ids(asset_ids: list[str] | None, *, max_refs: int = 12) -> list[str]:
    """Resolve Asset Hub IDs into local image paths for image-to-image backends."""
    ids = [str(item or "").strip() for item in (asset_ids or []) if str(item or "").strip()]
    if not ids:
        return []

    from app.db.database import get_async_session

    refs: list[str] = []
    async with get_async_session() as session:
        for asset_id in ids:
            if len(refs) >= max_refs:
                break

            primary_path = await _primary_image_path_for_asset(session, asset_id)
            if primary_path:
                refs.append(primary_path)
                continue

            # Reference cards can be collection/character roots whose usable images live on children.
            try:
                result = await session.execute(
                    select(AssetNode)
                    .where(AssetNode.parent_id == asset_id)
                    .order_by(AssetNode.created_at.asc())
                    .limit(max_refs)
                )
                children = list(result.scalars().all())
            except Exception as exc:
                logger.warning("[images] failed to resolve reference asset children for %s: %s", asset_id, exc)
                children = []

            for child in children:
                if len(refs) >= max_refs:
                    break
                child_path = await _primary_image_path_for_asset(session, str(child.id))
                if child_path:
                    refs.append(child_path)
    return refs


async def _merge_reference_images(req: ImageGenerateRequest) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    asset_refs = await _reference_images_from_asset_ids(req.reference_asset_ids)
    for value in [
        *(req.reference_images or []),
        *_reference_images_from_collection(req.reference_image_collection),
        *asset_refs,
    ]:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            refs.append(item)
    return refs


class ImageResponse(BaseModel):
    success: bool
    url: Optional[str] = None
    urls: Optional[list[str]] = None
    local_path: Optional[str] = None
    all_local_paths: Optional[list[str]] = None
    asset_id: str = ""
    all_asset_ids: list[str] = []
    asset_hub_node_id: str = ""
    all_asset_hub_node_ids: list[str] = []
    task_id: str = ""
    external_task_id: str = ""
    prompt_id: str = ""
    cost: float = 0.0
    provider: str = ""
    model: str = ""
    status: str = "pending"
    progress: float = 0.0
    error: Optional[str] = None


class BackendInfo(BaseModel):
    provider: str  # 纯净厂商名
    provider_label: str  # 厂商中文标签
    name: str  # 完整连接名称
    model: str  # 默认模型
    available_models: list[str] = []  # 可用模型列表（支持动态选择控制花费）
    capabilities: list[str]
    support_reference_image: bool = False  # 是否支持图生图
    reference_image_field: Optional[str] = None  # 参考图字段名
    supported_sizes: list[str] = []  # 支持的尺寸列表（如 1024x1024）
    supported_aspect_ratios: list[str] = []  # 支持的比例列表（如 1:1, 16:9）


class ImageBackendsResponse(BaseModel):
    success: bool = True
    backends: list[BackendInfo] = []
    default: Optional[str] = None


@router.get("/backends", response_model=ImageBackendsResponse, summary="可用图像后端列表")
async def list_backends():
    """返回所有已注册的图像生成后端"""
    from app.db.database import SessionLocal
    manager = get_ai_service()
    
    with SessionLocal() as db_session:
        try:
            if not manager.is_loaded():
                from pathlib import Path
                config_path = Path(__file__).parent.parent.parent.parent / "config" / "providers.yaml"
                AIService.initialize(str(config_path), session=db_session)
                logger.info("AIService reinitialized from /backends endpoint")
        except Exception as e:
            logger.warning(f"Reinitializing manager failed: {e}")

        registered_backend_names = set()
        try:
            from app.services.ai.types import MediaType
            registered_backend_names = set(manager._registry.get_all_backends(MediaType.IMAGE).keys())
        except Exception as e:
            logger.warning(f"Failed to get registered image backends: {e}")
        
        from app.db.models.ai_connector import AIConnector
        connectors = db_session.query(AIConnector).filter(
            AIConnector.is_active == True,
            AIConnector.provider_type == 'image'
        ).all()
        
        info_list = []
        for conn in connectors:
            try:
                if registered_backend_names and conn.name not in registered_backend_names:
                    continue
                name = conn.name
                model = conn.default_model or ''
                capabilities = ['text_to_image']
                if conn.support_reference_image:
                    capabilities.append('image_to_image')
                
                available_models = []
                if conn.default_params:
                    try:
                        import json
                        default_params = json.loads(conn.default_params) if isinstance(conn.default_params, str) else conn.default_params
                        if 'available_models' in default_params and isinstance(default_params['available_models'], list):
                            available_models = default_params['available_models']
                    except Exception:
                        pass
                if not available_models and model:
                    available_models = [model]
                
                # 解析 supported_sizes
                supported_sizes = []
                if conn.supported_sizes:
                    try:
                        supported_sizes = json.loads(conn.supported_sizes) if isinstance(conn.supported_sizes, str) else conn.supported_sizes
                    except Exception:
                        supported_sizes = []
                
                from app.db.models.ai_connector import AIProvider
                provider_label = AIProvider.label(conn.provider)
                info_list.append(BackendInfo(
                    provider=conn.provider,
                    provider_label=provider_label,
                    name=name,
                    model=model,
                    available_models=available_models,
                    capabilities=capabilities,
                    support_reference_image=bool(conn.support_reference_image),
                    reference_image_field=conn.reference_image_field,
                    supported_sizes=supported_sizes,
                    supported_aspect_ratios=[],  # TODO: 从 default_params 解析或添加数据库字段
                ))
            except Exception as e:
                logger.warning(f"Failed to get backend info for {conn.name}: {e}")
                continue
        
        default_backend = info_list[0].name if info_list else None
        
        return ImageBackendsResponse(
            success=True,
            backends=info_list,
            default=default_backend,
        )


@router.post("/generate", response_model=ImageResponse, summary="生成图片")
async def generate_image(req: ImageGenerateRequest):
    """
    调用图像生成后端生成图片。
    自动选择默认后端或指定 provider。
    支持动态指定 model 参数控制花费。
    """
    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    try:
        reference_images = await _merge_reference_images(req)
        img_req = ImageGenerationRequest(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or "",
            size=req.size or "1024x1024",
            style=req.style or "",
            n=req.n or 1,
            provider=req.provider or "",
            model=req.model or "",  # 动态指定模型
            # 扩展参数
            seed=req.seed,
            steps=req.steps or 20,
            cfg_scale=req.cfg_scale or 7.0,
            batch_size=req.batch_size or 1,
            sampler=req.sampler or "euler",
            source_image=req.source_image or "",
            reference_images=reference_images,
            lora=req.lora or "",
            controlnet=req.controlnet or "",
        )
        result = await manager.generate_image(img_req)

        if result.success:
            if result.task_id and result.status == "pending":
                queue = get_task_queue()
                task = await queue.create_task(
                    task_type="image_generation",
                    payload={
                        "external_task_id": result.task_id,
                        "provider": result.provider or req.provider or "",
                        "model": result.model or req.model or "",
                        "prompt": req.prompt,
                        "negative_prompt": req.negative_prompt or "",
                        "size": req.size or "1024x1024",
                        "steps": req.steps,
                        "cfg_scale": req.cfg_scale,
                        "sampler": req.sampler or "euler",
                        "lora": req.lora or "",
                        "controlnet": req.controlnet or "",
                        "source_image": req.source_image or "",
                        "reference_images": reference_images if reference_images else None,
                        "project_id": req.project_id or "",
                        "content_id": req.content_id or "",
                        "source_type": req.source_type or "",
                        "source_index": req.source_index or "",
                        "source_title": req.source_title or "",
                        "chapter_number": req.chapter_number or "",
                        "reference_asset_ids": req.reference_asset_ids or [],
                        "character_ids": req.character_ids or [],
                        "portrait_node_ids": req.portrait_node_ids or [],
                        "portrait_version_ids": req.portrait_version_ids or [],
                        "reference_image_collection": req.reference_image_collection or [],
                        "prompt_reference_id": req.prompt_reference_id or "",
                        "prompt_reference_source_id": req.prompt_reference_source_id or "",
                        "prompt_reference_title": req.prompt_reference_title or "",
                        "prompt_reference_category": req.prompt_reference_category or "",
                        "prompt_reference_source_url": req.prompt_reference_source_url or "",
                        "diagnostics": {
                            "external_task_id": result.task_id,
                            "provider": result.provider or req.provider or "",
                            "model": result.model or req.model or "",
                            "last_remote_status": result.status,
                            "last_polled_at": None,
                            "poll_count": 0,
                            "poll_error_count": 0,
                            "last_poll_error": "",
                            "last_response_excerpt": "",
                        },
                    },
                    max_retries=0,
                )
                await queue.append_event(
                    task.task_id,
                    "created",
                    "图片生成任务已创建",
                    data={"provider": result.provider or req.provider or "", "model": result.model or req.model or ""},
                )
                await queue.append_event(
                    task.task_id,
                    "submitted_remote",
                    "已提交到远端生图服务",
                    data={"external_task_id": result.task_id},
                )
                await queue.update_progress(
                    task.task_id,
                    max(5, int(result.progress or 0)),
                    "图片生成任务已提交",
                )
                return ImageResponse(
                    success=True,
                    task_id=task.task_id,
                    external_task_id=result.task_id,
                    prompt_id=result.prompt_id,
                    cost=result.cost,
                    provider=result.provider or "",
                    model=result.model or "",
                    status="pending",
                    progress=result.progress,
                )

            # 自动入库到资产库，并把素材 ID 返回给前端，方便项目工作流回写关联。
            asset_ids = []
            asset_hub_node_ids = []
            local_paths = result.all_local_paths or ([result.local_path] if result.local_path else [])
            if local_paths:
                try:
                    from app.db.database import get_async_session
                    async with get_async_session() as session:
                        for idx, local_path in enumerate(local_paths):
                            urls = result.urls or ([result.url] if result.url else [])
                            asset_hub_node_id = ""
                            try:
                                asset_hub_node_id = await _create_generated_image_asset_hub(
                                    session,
                                    image_path=str(local_path),
                                    prompt=req.prompt,
                                    provider=result.provider or "",
                                    model=result.model or "",
                                    source_url=urls[idx] if idx < len(urls) else (result.url or ""),
                                    negative_prompt=req.negative_prompt or "",
                                    size=req.size or "1024x1024",
                                    seed=result.seed,
                                    generation_params={
                                        "steps": req.steps,
                                        "cfg_scale": req.cfg_scale,
                                        "sampler": req.sampler or "euler",
                                        "lora": req.lora or "",
                                        "controlnet": req.controlnet or "",
                                        "image_index": idx,
                                        "reference_images_count": len(reference_images),
                                        "reference_image_collection": req.reference_image_collection or [],
                                        "prompt_reference_id": req.prompt_reference_id or "",
                                        "prompt_reference_source_id": req.prompt_reference_source_id or "",
                                        "prompt_reference_title": req.prompt_reference_title or "",
                                    },
                                    lineage=_generation_lineage_from_request(req),
                                )
                            except Exception as hub_error:
                                logger.warning(f"Failed to save image to Asset Hub: {hub_error}")
                            if asset_hub_node_id:
                                asset_hub_node_ids.append(asset_hub_node_id)
                                asset_ids.append(asset_hub_node_id)
                    logger.info(f"Image saved to asset library: {local_paths}")
                except Exception as e:
                    logger.warning(f"Failed to save image to asset library: {e}")

            return ImageResponse(
                success=True,
                url=result.url,
                urls=result.urls,
                local_path=str(result.local_path) if result.local_path else None,
                all_local_paths=result.all_local_paths,
                asset_id=asset_ids[0] if asset_ids else "",
                all_asset_ids=asset_ids,
                asset_hub_node_id=asset_hub_node_ids[0] if asset_hub_node_ids else "",
                all_asset_hub_node_ids=asset_hub_node_ids,
                task_id=result.task_id,
                external_task_id=result.task_id,
                prompt_id=result.prompt_id,
                cost=result.cost,
                provider=result.provider or "",
                model=result.model or "",
                status=result.status,
                progress=result.progress,
            )
        else:
            return ImageResponse(
                success=False,
                error=result.error,
                provider=result.provider or "",
                status=result.status,
            )
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return ImageResponse(success=False, error=str(e), provider="")


@router.get("/tasks/{task_id}", response_model=ImageResponse, summary="轮询图像生成任务")
async def poll_image_task(
    task_id: str,
    provider: str | None = Query(None, description="指定 provider（可选，默认使用默认后端）"),
):
    """
    轮询异步图像生成任务状态。

    适用于 ModelScope 等先返回 task_id 再通过轮询获取结果的 API。
    - 如果任务还在进行中，返回 status="pending"
    - 如果任务已完成，返回 status="done" + 图片 URL
    - 如果任务失败，返回 success=false
    """
    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    try:
        queue = get_task_queue()
        tracked_task = await queue.get_task(task_id)
        external_task_id = task_id
        task_provider = provider

        if tracked_task and tracked_task.task_type == "image_generation":
            payload = tracked_task.payload or {}
            external_task_id = payload.get("external_task_id") or task_id
            task_provider = provider or payload.get("provider") or None
            diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
            poll_count = int(diagnostics.get("poll_count") or 0) + 1
            await queue.update_diagnostics(
                task_id,
                poll_count=poll_count,
                last_polled_at=_utc_iso(),
            )

            if tracked_task.status == TaskStatus.DONE and tracked_task.result:
                data = tracked_task.result
                return ImageResponse(
                    success=True,
                    url=data.get("url"),
                    urls=data.get("urls"),
                    local_path=data.get("local_path"),
                    all_local_paths=data.get("all_local_paths"),
                    asset_id=data.get("asset_id", ""),
                    all_asset_ids=data.get("all_asset_ids", []),
                    asset_hub_node_id=data.get("asset_hub_node_id", ""),
                    all_asset_hub_node_ids=data.get("all_asset_hub_node_ids", []),
                    task_id=task_id,
                    external_task_id=external_task_id,
                    provider=data.get("provider", "") or payload.get("provider", ""),
                    model=data.get("model", "") or payload.get("model", ""),
                    status="done",
                    progress=100.0,
                )

            if tracked_task.status == TaskStatus.FAILED:
                return ImageResponse(
                    success=False,
                    error=tracked_task.error or "图片生成任务失败",
                    task_id=task_id,
                    external_task_id=external_task_id,
                    provider=payload.get("provider", ""),
                    model=payload.get("model", ""),
                    status="error",
                    progress=float(tracked_task.progress or 0),
                )

            await queue.update_progress(
                task_id,
                max(10, int(tracked_task.progress or 0)),
                "正在生成图片...",
            )

        result = await manager.poll_image(task_provider, external_task_id)
        if tracked_task and tracked_task.task_type == "image_generation":
            await queue.update_diagnostics(
                task_id,
                last_remote_status=result.status or "pending",
                last_response_excerpt=_response_excerpt({
                    "success": result.success,
                    "status": result.status,
                    "error": result.error,
                    "url_count": len(result.urls or []),
                }),
            )

        if result.success and result.status == "done":
            asset_ids = []
            asset_hub_node_ids = []
            if tracked_task and tracked_task.task_type == "image_generation":
                await queue.append_event(
                    task_id,
                    "poll_done",
                    "远端图片生成完成",
                    data={"external_task_id": external_task_id, "url_count": len(result.urls or [])},
                )
                payload = tracked_task.payload or {}
                local_paths = result.all_local_paths or ([result.local_path] if result.local_path else [])
                if local_paths:
                    try:
                        from app.db.database import get_async_session

                        await queue.append_event(
                            task_id,
                            "download_started",
                            "开始保存生成图片",
                            data={"file_count": len(local_paths)},
                        )
                        async with get_async_session() as session:
                            urls = result.urls or ([result.url] if result.url else [])
                            for idx, local_path in enumerate(local_paths):
                                asset_hub_node_id = ""
                                try:
                                    asset_hub_node_id = await _create_generated_image_asset_hub(
                                        session,
                                        image_path=str(local_path),
                                        prompt=payload.get("prompt", ""),
                                        provider=result.provider or "",
                                        model=result.model or "",
                                        source_url=urls[idx] if idx < len(urls) else (result.url or ""),
                                        negative_prompt=payload.get("negative_prompt", ""),
                                        size=payload.get("size", "1024x1024"),
                                        seed=result.seed,
                                        generation_params={
                                            "steps": payload.get("steps"),
                                            "cfg_scale": payload.get("cfg_scale"),
                                            "sampler": payload.get("sampler", "euler"),
                                            "lora": payload.get("lora", ""),
                                            "controlnet": payload.get("controlnet", ""),
                                            "image_index": idx,
                                            "reference_images_count": len(payload.get("reference_images") or []),
                                            "reference_image_collection": payload.get("reference_image_collection") or [],
                                            "prompt_reference_id": payload.get("prompt_reference_id", ""),
                                            "prompt_reference_source_id": payload.get("prompt_reference_source_id", ""),
                                            "prompt_reference_title": payload.get("prompt_reference_title", ""),
                                        },
                                        lineage=_generation_lineage_from_payload(
                                            payload,
                                            extra={
                                                "task_id": task_id,
                                                "external_task_id": external_task_id,
                                            },
                                        ),
                                    )
                                except Exception as hub_error:
                                    logger.warning(f"Failed to save async image to Asset Hub: {hub_error}")
                                if asset_hub_node_id:
                                    asset_hub_node_ids.append(asset_hub_node_id)
                                    asset_ids.append(asset_hub_node_id)
                                await queue.append_event(
                                    task_id,
                                    "asset_saved",
                                    "生成图片已入素材库",
                                    data={"asset_id": asset_hub_node_id, "asset_hub_node_id": asset_hub_node_id, "image_index": idx},
                                )
                        await queue.append_event(
                            task_id,
                            "download_done",
                            "生成图片保存完成",
                            data={"file_count": len(local_paths), "asset_count": len(asset_ids)},
                        )
                    except Exception as e:
                        logger.warning(f"Failed to save async image to asset library: {e}")
                        await queue.append_event(
                            task_id,
                            "failed",
                            "生成图片入素材库失败",
                            level="warning",
                            data={"error": str(e)},
                        )

            response_data = {
                "url": result.url,
                "urls": result.urls,
                "local_path": result.local_path,
                "all_local_paths": result.all_local_paths,
                "asset_id": asset_ids[0] if asset_ids else "",
                "all_asset_ids": asset_ids,
                "asset_hub_node_id": asset_hub_node_ids[0] if asset_hub_node_ids else "",
                "all_asset_hub_node_ids": asset_hub_node_ids,
                "provider": result.provider or "",
                "model": result.model or "",
                "diagnostics": (tracked_task.payload or {}).get("diagnostics", {}) if tracked_task else {},
            }
            if tracked_task and tracked_task.task_type == "image_generation":
                tracked_task.status = TaskStatus.DONE
                tracked_task.progress = 100
                tracked_task.progress_message = "图片生成完成"
                tracked_task.result = response_data
                tracked_task.error = None
                tracked_task.completed_at = time.time()
                await queue.update_task(tracked_task)

            return ImageResponse(
                success=True,
                url=result.url,
                urls=result.urls,
                local_path=result.local_path,
                all_local_paths=result.all_local_paths,
                asset_id=asset_ids[0] if asset_ids else "",
                all_asset_ids=asset_ids,
                asset_hub_node_id=asset_hub_node_ids[0] if asset_hub_node_ids else "",
                all_asset_hub_node_ids=asset_hub_node_ids,
                task_id=task_id,
                external_task_id=result.task_id or external_task_id,
                provider=result.provider or "",
                model=result.model or "",
                status=result.status,
                progress=result.progress,
            )
        elif not result.success and result.error:
            if tracked_task and tracked_task.task_type == "image_generation":
                payload = tracked_task.payload or {}
                diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
                await queue.update_diagnostics(
                    task_id,
                    poll_error_count=int(diagnostics.get("poll_error_count") or 0) + 1,
                    last_poll_error=result.error,
                    last_remote_status=result.status or "error",
                )
                await queue.append_event(
                    task_id,
                    "failed",
                    "图片生成任务失败",
                    level="error",
                    data={"error": result.error, "remote_status": result.status},
                )
                tracked_task.status = TaskStatus.FAILED
                tracked_task.error = result.error
                tracked_task.progress_message = result.error
                tracked_task.completed_at = time.time()
                await queue.update_task(tracked_task)

            return ImageResponse(
                success=False,
                error=result.error,
                task_id=task_id,
                external_task_id=external_task_id,
                provider=result.provider or "",
                status=result.status or "error",
            )
        else:
            if tracked_task and tracked_task.task_type == "image_generation":
                diagnostics = (tracked_task.payload or {}).get("diagnostics", {})
                poll_count = int(diagnostics.get("poll_count") or 0)
                if poll_count <= 1 or poll_count % 5 == 0:
                    await queue.append_event(
                        task_id,
                        "poll_pending",
                        "远端任务仍在处理中",
                        data={"remote_status": result.status or "pending", "poll_count": poll_count},
                    )
                await queue.update_progress(
                    task_id,
                    max(int(result.progress or 0), int(tracked_task.progress or 0), 10),
                    "正在生成图片...",
                )

            return ImageResponse(
                success=True,
                task_id=task_id,
                external_task_id=result.task_id or external_task_id,
                provider=result.provider or "",
                model=result.model or "",
                status=result.status or "pending",
                progress=result.progress,
            )
    except Exception as e:
        logger.error(f"Image poll failed: {e}")
        try:
            queue = get_task_queue()
            tracked_task = await queue.get_task(task_id)
            if tracked_task and tracked_task.task_type == "image_generation":
                payload = tracked_task.payload or {}
                diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
                await queue.update_diagnostics(
                    task_id,
                    poll_error_count=int(diagnostics.get("poll_error_count") or 0) + 1,
                    last_poll_error=str(e),
                    last_polled_at=_utc_iso(),
                )
                await queue.append_event(
                    task_id,
                    "failed",
                    "查询图片生成任务异常",
                    level="error",
                    data={"error": str(e)},
                )
        except Exception:
            pass
        return ImageResponse(success=False, error=str(e), task_id=task_id)


# =============================================================================
# 多平台生图
# =============================================================================

class PlatformTemplateInfo(BaseModel):
    id: str = ""
    platform: str = ""
    name: str = ""
    template_scope: str = "image_platform"
    template_stage: str = "platform"
    description: Optional[str] = None
    system_template: str = ""
    outline_template: str = ""
    image_template: str = ""
    page_structure: dict = {}
    variables: dict = {}
    video_template: Optional[str] = None
    default_size: str = "1024x1024"
    is_active: bool = True
    sort_order: int = 0


class PlatformTemplateCreateRequest(BaseModel):
    platform: str
    name: str
    template_scope: str = "image_platform"
    template_stage: str = "platform"
    description: Optional[str] = None
    system_template: str = ""
    outline_template: str
    image_template: str = ""
    page_structure: Optional[dict] = {}
    variables: Optional[dict] = {}
    video_template: Optional[str] = None
    default_size: str = "1024x1024"
    is_active: bool = True
    sort_order: int = 0


class PlatformTemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    template_scope: Optional[str] = None
    template_stage: Optional[str] = None
    description: Optional[str] = None
    system_template: Optional[str] = None
    outline_template: Optional[str] = None
    image_template: Optional[str] = None
    page_structure: Optional[dict] = None
    variables: Optional[dict] = None
    video_template: Optional[str] = None
    default_size: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class GenerateOutlineRequest(BaseModel):
    topic: str
    platforms: list[str] = []  # ["xiaohongshu", "douyin"]
    backend_name: Optional[str] = None  # 指定 Backend 名称（如"小米2.5pro"），使用该 Backend 的默认模型
    model: Optional[str] = None  # 指定模型（如"mimo-v2.5-pro"），覆盖 Backend 默认模型
    reference_images: Optional[list[str]] = None  # 参考图（base64，用于多模态 LLM 反推）


class GenerateOutlineResponse(BaseModel):
    success: bool = True
    outlines: dict = {}  # { xiaohongshu: { title, copywriting, pages: [{type, prompt}] } }
    error: Optional[str] = None


class BatchGenerateRequest(BaseModel):
    pages: list[dict] = []  # [{ prompt, platform, size, n }]
    provider: Optional[str] = None
    model: Optional[str] = None
    # 多平台生图上下文（可选，用于资产库记录）
    topic: Optional[str] = None
    template_id: Optional[str] = None
    outline_title: Optional[str] = None
    outline_copywriting: Optional[str] = None
    # 参考图（支持反推人物特征）
    reference_images: list[str] = []  # base64 编码的图片


class BatchGenerateResponse(BaseModel):
    success: bool = True
    results: dict = {}  # { xiaohongshu: [{ urls, prompt, success }] }
    error: Optional[str] = None


class BatchTopicGenerateRequest(BaseModel):
    topics: list[str] = []
    platforms: list[str] = []
    provider: Optional[str] = None
    model: Optional[str] = None
    backend_name: Optional[str] = None
    llm_model: Optional[str] = None
    reference_images: list[str] = []


class BatchTopicGenerateResponse(BaseModel):
    success: bool = True
    results: list[dict] = []
    error: Optional[str] = None


def _serialize_platform_template(t) -> dict:
    return {
        "id": str(t.id),
        "platform": t.platform,
        "name": t.name,
        "template_scope": getattr(t, "template_scope", "image_platform") or "image_platform",
        "template_stage": getattr(t, "template_stage", "platform") or "platform",
        "description": getattr(t, "description", None),
        "system_template": getattr(t, "system_template", "") or "",
        "outline_template": t.outline_template,
        "image_template": t.image_template,
        "page_structure": t.page_structure or {},
        "variables": getattr(t, "variables", None) or {},
        "video_template": t.video_template,
        "default_size": t.default_size,
        "is_active": t.is_active,
        "sort_order": t.sort_order,
    }


@router.get("/platform-templates", response_model=dict, summary="可用平台/Prompt 模板列表")
async def list_platform_templates(
    template_scope: str | None = Query(default="image_platform", description="image_platform/creative_project/all"),
    template_stage: str | None = Query(default=None, description="outline/chapter_plan/script/storyboard/platform"),
    include_inactive: bool = Query(default=False),
):
    """返回平台模板或创作项目 Prompt 模板。

    默认只返回 image_platform，保持多平台生图旧接口行为不变。
    """
    from app.db.database import get_async_session
    from app.db.models.platform_template import PlatformTemplate
    from sqlmodel import select
    
    async with get_async_session() as session:
        stmt = select(PlatformTemplate)
        if not include_inactive:
            stmt = stmt.where(PlatformTemplate.is_active == True)
        if template_scope and template_scope not in {"all", "*"}:
            stmt = stmt.where(PlatformTemplate.template_scope == template_scope)
        if template_stage and template_stage not in {"all", "*"}:
            stmt = stmt.where(PlatformTemplate.template_stage == template_stage)
        stmt = stmt.order_by(PlatformTemplate.template_scope, PlatformTemplate.sort_order)
        result = await session.exec(stmt)
        templates = result.all()
        return {
            "success": True,
            "templates": [_serialize_platform_template(t) for t in templates],
        }


@router.post("/platform-templates", response_model=dict, summary="新增平台模板")
async def create_platform_template(req: PlatformTemplateCreateRequest):
    """新增一个平台模板"""
    from app.db.database import get_async_session
    from app.db.models.platform_template import PlatformTemplate
    from sqlmodel import select

    async with get_async_session() as session:
        # 检查 platform 是否已存在
        existing = await session.exec(
            select(PlatformTemplate).where(PlatformTemplate.platform == req.platform)
        )
        if existing.first():
            raise HTTPException(status_code=409, detail=f"平台标识 '{req.platform}' 已存在")

        template = PlatformTemplate(**req.model_dump())
        session.add(template)
        await session.commit()
        await session.refresh(template)

        return {
            "success": True,
            "template": _serialize_platform_template(template),
            "message": "创建成功",
        }


@router.put("/platform-templates/{template_id}", response_model=dict, summary="更新平台模板")
async def update_platform_template(
    template_id: str,
    req: PlatformTemplateUpdateRequest,
):
    """更新指定平台模板"""
    from app.db.database import get_async_session
    from app.db.models.platform_template import PlatformTemplate
    from sqlmodel import select
    import uuid

    async with get_async_session() as session:
        # 查询模板
        stmt = select(PlatformTemplate).where(PlatformTemplate.id == uuid.UUID(template_id))
        result = await session.exec(stmt)
        template = result.one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")

        # 更新字段
        update_data = req.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(template, key, value)

        session.add(template)
        await session.commit()
        await session.refresh(template)

        return {
            "success": True,
            "template": _serialize_platform_template(template),
            "message": "更新成功",
        }


@router.delete("/platform-templates/{template_id}", response_model=dict, summary="删除平台模板")
async def delete_platform_template(template_id: str):
    """删除指定平台模板（软删除：设置 is_active=False）"""
    from app.db.database import get_async_session
    from app.db.models.platform_template import PlatformTemplate
    from sqlmodel import select
    import uuid

    async with get_async_session() as session:
        stmt = select(PlatformTemplate).where(PlatformTemplate.id == uuid.UUID(template_id))
        result = await session.exec(stmt)
        template = result.one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")

        # 软删除
        template.is_active = False
        session.add(template)
        await session.commit()

        return {
            "success": True,
            "message": "删除成功",
        }


@router.post("/generate-outline", response_model=GenerateOutlineResponse, summary="多平台大纲生成")
async def generate_outline_endpoint(req: GenerateOutlineRequest):
    """
    使用 LLM 为输入的 topic 生成多平台结构化大纲。
    每个平台返回 title、copywriting、pages（含 type 和 prompt）。
    支持参考图（多模态 LLM）。
    
    选择逻辑：
    1. 如果传了 backend_name，使用该 Backend 的默认模型
    2. 如果同时传了 backend_name + model，使用指定的模型（覆盖默认）
    3. 如果都没传，使用系统默认 Backend
    """
    logger.info("[API] generate-outline called: topic=%s, platforms=%s, backend_name=%s, model=%s",
                req.topic, req.platforms, req.backend_name, req.model)
    from app.db.database import get_async_session
    from app.services.ai.outline_service import generate_outline
    
    if not req.topic or not req.topic.strip():
        return GenerateOutlineResponse(success=False, error="Topic is required")
    if not req.platforms:
        return GenerateOutlineResponse(success=False, error="At least one platform is required")
    
    try:
        async with get_async_session() as session:
            outlines = await generate_outline(
                session, 
                req.topic, 
                req.platforms, 
                backend_name=req.backend_name,
                model=req.model,
                reference_images=req.reference_images
            )
            return GenerateOutlineResponse(success=bool(outlines), outlines=outlines)
    except Exception as e:
        logger.error(f"Generate outline failed: {e}")
        return GenerateOutlineResponse(success=False, error=str(e))


class BatchRetryRequest(BaseModel):
    prompt: str
    platform: str = ""
    size: Optional[str] = "1024x1024"
    n: Optional[int] = 1
    provider: Optional[str] = None
    model: Optional[str] = None
    topic: Optional[str] = None
    template_id: Optional[str] = None
    outline_title: Optional[str] = None
    outline_copywriting: Optional[str] = None
    page_type: Optional[str] = None


class BatchRetryResponse(BaseModel):
    success: bool = True
    urls: list[str] = []
    platform: str = ""
    prompt: str = ""
    asset_id: str = ""
    error: Optional[str] = None


@router.post("/generate-batch/retry", response_model=BatchRetryResponse, summary="单张图片重生成")
async def batch_retry_endpoint(req: BatchRetryRequest):
    """
    对批量生成中失败的图片进行单张重生成。
    复用 generate_image 逻辑，返回新的图片 URL。
    """
    from app.services.ai.types import ImageGenerationRequest
    from app.db.database import get_async_session

    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    try:
        img_req = ImageGenerationRequest(
            prompt=req.prompt,
            size=req.size or "1024x1024",
            n=req.n or 1,
            provider=req.provider or "",
            model=req.model or "",
        )
        result = await manager.generate_image(img_req)

        if result.success:
            urls = result.urls or [result.url] if result.url else []

            # 自动入库到资产库
            asset_hub_node_id = ""
            if result.local_path:
                try:
                    async with get_async_session() as session:
                        try:
                            asset_hub_node_id = await _create_generated_image_asset_hub(
                                session,
                                image_path=str(result.local_path),
                                prompt=req.prompt,
                                provider=result.provider or "",
                                model=result.model or "",
                                source_url=result.url or "",
                                size=req.size or "1024x1024",
                                seed=result.seed,
                                lineage={
                                    "topic": req.topic or "",
                                    "template_id": req.template_id or "",
                                    "outline_title": req.outline_title or "",
                                    "outline_copywriting": req.outline_copywriting or "",
                                    "page_type": req.page_type or "",
                                    "content_platform": req.platform or "",
                                },
                            )
                        except Exception as hub_error:
                            logger.warning(f"Failed to save retry image to Asset Hub: {hub_error}")
                except Exception as e:
                    logger.warning(f"Failed to save retry image to asset library: {e}")

            return BatchRetryResponse(
                success=True,
                urls=urls,
                platform=req.platform,
                prompt=req.prompt,
                asset_id=asset_hub_node_id,
            )
        else:
            return BatchRetryResponse(
                success=False,
                platform=req.platform,
                prompt=req.prompt,
                error=result.error or "Generation failed",
            )
    except Exception as e:
        logger.error(f"Batch retry failed: {e}")
        return BatchRetryResponse(success=False, error=str(e), platform=req.platform, prompt=req.prompt)


@router.post("/generate-batch", response_model=BatchGenerateResponse, summary="批量生成多平台图片")
async def batch_generate_endpoint(req: BatchGenerateRequest):
    """
    批量生成图片：对每页并行调用现有 generate_image。
    返回按平台分组的结果。
    自动入库到资产库（topic/template_id 等上下文字段用于标记多平台生图来源）。
    支持参考图反推人物特征。
    """
    from app.db.database import get_async_session
    from app.services.ai.outline_service import batch_generate_images
    
    if not req.pages:
        return BatchGenerateResponse(success=False, error="pages is required")
    
    try:
        async with get_async_session() as session:
            results = await batch_generate_images(
                session,
                req.pages,
                provider=req.provider or "",
                model=req.model or "",
                topic=req.topic,
                template_id=req.template_id,
                outline_title=req.outline_title,
                outline_copywriting=req.outline_copywriting,
                reference_images=req.reference_images,
            )
            return BatchGenerateResponse(success=True, results=results.get("results", {}))
    except Exception as e:
        logger.error(f"Batch generate failed: {e}")
        return BatchGenerateResponse(success=False, error=str(e))


@router.post("/generate-batch/topics", response_model=BatchTopicGenerateResponse, summary="多主题批量生成")
async def batch_topics_generate_endpoint(req: BatchTopicGenerateRequest):
    """
    多主题编排：每个主题先生成多平台大纲，再批量生成图片并入库。
    """
    from app.db.database import get_async_session
    from app.services.ai.outline_service import batch_generate_images, generate_outline

    topics = [t.strip() for t in req.topics if t and t.strip()]
    if not topics:
        return BatchTopicGenerateResponse(success=False, error="topics is required")
    if not req.platforms:
        return BatchTopicGenerateResponse(success=False, error="platforms is required")

    async def run_topic(topic: str) -> dict:
        async with get_async_session() as session:
            try:
                outlines = await generate_outline(
                    session,
                    topic,
                    req.platforms,
                    backend_name=req.backend_name,
                    model=req.llm_model,
                    reference_images=req.reference_images,
                )
                pages: list[dict] = []
                for platform, outline in outlines.items():
                    for page in outline.get("pages", []) or []:
                        pages.append({
                            "prompt": page.get("prompt", ""),
                            "platform": platform,
                            "size": page.get("size", "1024x1024"),
                            "n": 1,
                            "type": page.get("type", ""),
                        })

                generated = {"results": {}}
                if pages:
                    generated = await batch_generate_images(
                        session,
                        pages,
                        provider=req.provider or "",
                        model=req.model or "",
                        topic=topic,
                        outline_title=next(iter(outlines.values())).get("title", topic) if outlines else topic,
                        outline_copywriting=next(iter(outlines.values())).get("copywriting", "") if outlines else "",
                        reference_images=req.reference_images,
                    )

                return {
                    "topic": topic,
                    "success": True,
                    "outlines": outlines,
                    "results": generated.get("results", {}),
                }
            except Exception as e:
                logger.error("Batch topic generation failed for %s: %s", topic, e)
                return {
                    "topic": topic,
                    "success": False,
                    "error": str(e),
                    "outlines": {},
                    "results": {},
                }

    semaphore = asyncio.Semaphore(2)

    async def run_limited(topic: str) -> dict:
        async with semaphore:
            return await run_topic(topic)

    results = await asyncio.gather(*(run_limited(topic) for topic in topics))
    return BatchTopicGenerateResponse(
        success=all(item.get("success") for item in results),
        results=results,
    )
