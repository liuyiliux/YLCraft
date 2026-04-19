"""
YLCraft — 图像生成 API

POST /api/v1/images/generate — 调用图像生成 Provider 生成图片
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm.manager import get_manager

router = APIRouter()
logger = logging.getLogger("ylcraft.images")


class ImageGenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    size: Optional[str] = "1024x1024"
    style: Optional[str] = None
    n: Optional[int] = 1
    provider: Optional[str] = None


class ImageResponse(BaseModel):
    success: bool
    url: Optional[str] = None
    urls: Optional[list[str]] = None
    error: Optional[str] = None


@router.post("/generate", response_model=ImageResponse, summary="生成图片")
async def generate_image(req: ImageGenerateRequest):
    """
    调用图像生成 Provider（如 DALL-E、Stable Diffusion 等）生成图片。
    """
    manager = get_manager()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="BackendManager 未初始化")

    try:
        from app.core.contracts.types import ImageGenerationRequest

        img_req = ImageGenerationRequest(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or "",
            size=req.size or "1024x1024",
            style=req.style or "",
            n=req.n or 1,
        )
        result = await manager.generate_image(img_req)

        if result.success:
            return ImageResponse(success=True, url=result.url, urls=result.urls)
        else:
            return ImageResponse(success=False, error=result.error)
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return ImageResponse(success=False, error=str(e))
