"""
YLCraft — 图像生成 API

POST /api/v1/images/generate — 调用图像生成后端生成图片
GET  /api/v1/images/backends — 可用的图像后端列表
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm.manager import get_manager
from app.core.contracts.types import ImageGenerationRequest

router = APIRouter()
logger = logging.getLogger("ylcraft.images")


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


class ImageResponse(BaseModel):
    success: bool
    url: Optional[str] = None
    urls: Optional[list[str]] = None
    local_path: Optional[str] = None
    all_local_paths: Optional[list[str]] = None
    task_id: str = ""
    prompt_id: str = ""
    cost: float = 0.0
    provider: str = ""
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
    manager = get_manager()
    
    with SessionLocal() as db_session:
        try:
            if not manager.is_loaded():
                from app.services.llm.manager import init_manager
                from pathlib import Path
                config_path = Path(__file__).parent.parent.parent.parent / "config" / "providers.yaml"
                init_manager(str(config_path), session=db_session)
                logger.info("BackendManager reinitialized from /backends endpoint")
        except Exception as e:
            logger.warning(f"Reinitializing manager failed: {e}")
        
        from app.db.models.ai_connector import AIConnector
        connectors = db_session.query(AIConnector).filter(
            AIConnector.is_active == True,
            AIConnector.provider_type == 'image'
        ).all()
        
        info_list = []
        for conn in connectors:
            try:
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
    manager = get_manager()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="BackendManager 未初始化")

    try:
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
            reference_images=req.reference_images or [],
            lora=req.lora or "",
            controlnet=req.controlnet or "",
        )
        result = await manager.generate_image(img_req)

        if result.success:
            # 自动入库到资产库
            if result.local_path:
                try:
                    from app.db.database import get_async_session
                    from app.services.asset.service import AssetService
                    async with get_async_session() as session:
                        service = AssetService(session)
                        await service.create_from_image_generation(
                            image_path=str(result.local_path),
                            prompt=req.prompt,
                            provider=result.provider,
                            model=result.model,
                            seed=result.seed,
                            url=result.url or "",
                            negative_prompt=req.negative_prompt or "",
                            size=req.size or "1024x1024",
                            steps=req.steps,
                            cfg_scale=req.cfg_scale,
                            sampler=req.sampler or "euler",
                            lora=req.lora or "",
                            controlnet=req.controlnet or "",
                            source_image=req.source_image or "",
                            reference_images=img_req.reference_images if img_req.reference_images else None,
                        )
                    logger.info(f"Image saved to asset library: {result.local_path}")
                except Exception as e:
                    logger.warning(f"Failed to save image to asset library: {e}")

            return ImageResponse(
                success=True,
                url=result.url,
                urls=result.urls,
                local_path=str(result.local_path) if result.local_path else None,
                all_local_paths=result.all_local_paths,
                task_id=result.task_id,
                prompt_id=result.prompt_id,
                cost=result.cost,
                provider=result.provider or "",
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


# =============================================================================
# 多平台生图
# =============================================================================

class PlatformTemplateInfo(BaseModel):
    id: str = ""
    platform: str = ""
    name: str = ""
    outline_template: str = ""
    image_template: str = ""
    video_template: Optional[str] = None
    default_size: str = "1024x1024"
    is_active: bool = True
    sort_order: int = 0


class PlatformTemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    outline_template: Optional[str] = None
    image_template: Optional[str] = None
    video_template: Optional[str] = None
    default_size: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class GenerateOutlineRequest(BaseModel):
    topic: str
    platforms: list[str] = []  # ["xiaohongshu", "douyin"]
    llm_model: Optional[str] = None  # 指定 LLM 模型
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


@router.get("/platform-templates", response_model=dict, summary="可用平台模板列表")
async def list_platform_templates():
    """返回所有已激活的平台生成模板（完整信息）"""
    from app.db.database import get_async_session
    from app.db.models.platform_template import PlatformTemplate
    from sqlmodel import select
    
    async with get_async_session() as session:
        result = await session.exec(
            select(PlatformTemplate)
            .where(PlatformTemplate.is_active == True)
            .order_by(PlatformTemplate.sort_order)
        )
        templates = result.all()
        return {
            "success": True,
            "templates": [
                {
                    "id": str(t.id),
                    "platform": t.platform,
                    "name": t.name,
                    "outline_template": t.outline_template,
                    "image_template": t.image_template,
                    "video_template": t.video_template,
                    "default_size": t.default_size,
                    "is_active": t.is_active,
                    "sort_order": t.sort_order,
                }
                for t in templates
            ],
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
            "template": {
                "id": str(template.id),
                "platform": template.platform,
                "name": template.name,
                "outline_template": template.outline_template,
                "image_template": template.image_template,
                "video_template": template.video_template,
                "default_size": template.default_size,
                "is_active": template.is_active,
                "sort_order": template.sort_order,
            },
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
    """
    from app.db.database import get_async_session
    from app.services.image.outline_service import generate_outline
    
    if not req.topic or not req.topic.strip():
        return GenerateOutlineResponse(success=False, error="Topic is required")
    if not req.platforms:
        return GenerateOutlineResponse(success=False, error="At least one platform is required")
    
    try:
        async with get_async_session() as session:
            outlines = await generate_outline(session, req.topic, req.platforms, req.llm_model, req.reference_images)
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


class BatchRetryResponse(BaseModel):
    success: bool = True
    urls: list[str] = []
    platform: str = ""
    prompt: str = ""
    error: Optional[str] = None


@router.post("/generate-batch/retry", response_model=BatchRetryResponse, summary="单张图片重生成")
async def batch_retry_endpoint(req: BatchRetryRequest):
    """
    对批量生成中失败的图片进行单张重生成。
    复用 generate_image 逻辑，返回新的图片 URL。
    """
    from app.core.contracts.types import ImageGenerationRequest
    from app.db.database import get_async_session
    from app.services.asset.service import AssetService

    manager = get_manager()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="BackendManager 未初始化")

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
            if result.local_path:
                try:
                    async with get_async_session() as session:
                        service = AssetService(session)
                        await service.create_from_image_generation(
                            image_path=str(result.local_path),
                            prompt=req.prompt,
                            provider=result.provider,
                            model=result.model,
                            seed=result.seed,
                            url=result.url or "",
                            size=req.size or "1024x1024",
                        )
                except Exception as e:
                    logger.warning(f"Failed to save retry image to asset library: {e}")

            return BatchRetryResponse(
                success=True,
                urls=urls,
                platform=req.platform,
                prompt=req.prompt,
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
    from app.services.image.outline_service import batch_generate_images
    
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
