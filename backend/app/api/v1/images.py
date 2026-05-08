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
                
                from app.db.models.ai_connector import AIProvider
                provider_label = AIProvider.label(conn.provider)
                info_list.append(BackendInfo(
                    provider=conn.provider,
                    provider_label=provider_label,
                    name=name,
                    model=model,
                    available_models=available_models,
                    capabilities=capabilities,
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
            lora=req.lora or "",
            controlnet=req.controlnet or "",
        )
        result = await manager.generate_image(img_req)

        if result.success:
            # 自动入库到资产库
            if result.local_path:
                try:
                    from app.services.asset_service import AssetService
                    AssetService.create_from_image_generation(
                        image_path=str(result.local_path),
                        prompt=req.prompt,
                        provider=result.provider,
                        model=result.model,
                        seed=result.seed,
                        url=result.url or "",
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
