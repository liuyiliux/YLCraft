"""
YLCraft — 3D 模型 API

GET    /api/v1/3d/metadata/:id      — 获取 3D 模型元数据
POST   /api/v1/3d/extract-metadata — 提取模型元数据
POST   /api/v1/3d/generate-preview — 生成预览图
POST   /api/v1/3d/convert          — 格式转换
POST   /api/v1/3d/generate-from-image — TripoSR 图生 3D
GET    /api/v1/3d/generate-from-image/:task_id — 查询生成状态
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.services.model3d.service import Model3DService

router = APIRouter()
logger = logging.getLogger("ylcraft.model3d")

# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_model3d_service():
    """获取 Model3DService 实例"""
    async with get_async_session() as session:
        yield Model3DService(session)

# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class Model3DResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]

class ExtractMetadataRequest(BaseModel):
    file_path: str = Field(..., description="3D 模型文件路径")

class GeneratePreviewRequest(BaseModel):
    file_path: str = Field(..., description="3D 模型文件路径")
    output_path: Optional[str] = Field(None, description="输出路径")
    resolution: int = Field(512, description="预览分辨率")

class ConvertFormatRequest(BaseModel):
    source_path: str = Field(..., description="源文件路径")
    target_format: str = Field(..., description="目标格式: glb, gltf, fbx, obj")
    output_path: Optional[str] = Field(None, description="输出路径")

class GenerateFromImageRequest(BaseModel):
    image_path: str = Field(..., description="图片路径或 URL")
    task_id: Optional[str] = Field(None, description="已有任务 ID（查询进度用）")

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@router.post("/3d/extract-metadata", response_model=Model3DResponse)
async def extract_3d_metadata(
    request: ExtractMetadataRequest,
    service: Model3DService = Depends(get_model3d_service),
):
    """
    提取 3D 模型元数据

    支持格式：glb, gltf, fbx, obj
    返回顶点/面数/材质/纹理/动画/骨骼等信息。
    """
    metadata = await service.extract_metadata(request.file_path)

    if "error" in metadata:
        raise HTTPException(status_code=400, detail=metadata["error"])

    return {
        "success": True,
        "data": metadata,
    }


@router.post("/3d/generate-preview", response_model=Model3DResponse)
async def generate_3d_preview(
    request: GeneratePreviewRequest,
    service: Model3DService = Depends(get_model3d_service),
):
    """
    生成 3D 模型预览图

    需要服务端渲染支持（Blender 或 three.js）。
    """
    preview_path = await service.generate_preview(
        file_path=request.file_path,
        output_path=request.output_path,
        resolution=request.resolution,
    )

    if not preview_path:
        return {
            "success": True,
            "data": {"message": "Preview generation not supported for this format"},
        }

    return {
        "success": True,
        "data": {"preview_path": preview_path},
    }


@router.post("/3d/convert", response_model=Model3DResponse)
async def convert_3d_format(
    request: ConvertFormatRequest,
    service: Model3DService = Depends(get_model3d_service),
):
    """
    转换 3D 模型格式

    需要 Blender 或 pyransport 支持。
    """
    output_path = await service.convert_format(
        source_path=request.source_path,
        target_format=request.target_format,
        output_path=request.output_path,
    )

    if not output_path:
        return {
            "success": True,
            "data": {"message": "Format conversion not supported"},
        }

    return {
        "success": True,
        "data": {"output_path": output_path},
    }


@router.post("/3d/generate-from-image", response_model=Model3DResponse)
async def generate_3d_from_image(
    request: GenerateFromImageRequest,
    service: Model3DService = Depends(get_model3d_service),
):
    """
    使用 TripoSR 从图片生成 3D 模型

    首次调用返回 task_id，后续使用同一 task_id 查询进度。
    """
    result = await service.generate_3d_from_image(
        image_path=request.image_path,
        task_id=request.task_id,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "success": True,
        "data": result,
    }


@router.get("/3d/generate-from-image/{task_id}", response_model=Model3DResponse)
async def get_3d_generation_status(
    task_id: str,
    service: Model3DService = Depends(get_model3d_service),
):
    """
    查询 TripoSR 3D 生成任务状态
    """
    result = await service.generate_3d_from_image(
        image_path="",
        task_id=task_id,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "success": True,
        "data": result,
    }


@router.get("/3d/supported-formats")
async def get_supported_formats():
    """获取支持的 3D 模型格式列表"""
    return {
        "success": True,
        "data": {
            "formats": [".glb", ".gltf", ".fbx", ".obj", ".usdz", ".dae"],
        },
    }
