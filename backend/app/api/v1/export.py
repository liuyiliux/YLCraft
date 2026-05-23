"""
YLCraft — 导出 + 质量 + 去重 API

POST   /api/v1/export/dataset      — 导出数据集
GET    /api/v1/export/stats       — 获取数据集统计
POST   /api/v1/export/quality     — 批量计算质量评分
POST   /api/v1/export/duplicates  — 查找重复资产
POST   /api/v1/export/merge       — 合并重复资产
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.db.models.asset_hub import AssetType
from app.services.export.service import ExportService

router = APIRouter()
logger = logging.getLogger("ylcraft.export")

# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_export_service():
    """获取 ExportService 实例"""
    async with get_async_session() as session:
        yield ExportService(session)

# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class ExportDatasetRequest(BaseModel):
    output_path: str = Field(..., description="输出 ZIP 文件路径")
    filters: Optional[Dict[str, Any]] = Field(None, description="过滤条件")
    include_metadata: bool = Field(True, description="包含元数据")
    include_lineage: bool = Field(False, description="包含谱系信息")

class QualityScoreRequest(BaseModel):
    asset_ids: Optional[List[str]] = Field(None, description="资产ID列表")
    asset_type: Optional[str] = Field(None, description="资产类型过滤")

class FindDuplicatesRequest(BaseModel):
    asset_type: Optional[str] = Field(None, description="资产类型过滤")
    similarity_threshold: float = Field(0.95, description="相似度阈值")

class MergeDuplicatesRequest(BaseModel):
    primary_asset_id: str = Field(..., description="主资产ID")
    duplicate_asset_ids: List[str] = Field(..., description="要合并的资产ID列表")
    keep_references: bool = Field(True, description="保留引用关系")

class ExportResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@router.post("/export/dataset", response_model=ExportResponse)
async def export_dataset(
    request: ExportDatasetRequest,
    service: ExportService = Depends(get_export_service),
):
    """
    导出数据集

    将符合条件的资产打包为 ZIP 文件，包含：
    - 所有原始文件（图片/视频/模型等）
    - metadata.json（元数据列表）
    - summary.json（统计摘要）
    """
    result = await service.export_dataset(
        output_path=request.output_path,
        filters=request.filters,
        include_metadata=request.include_metadata,
        include_lineage=request.include_lineage,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Export failed")

    return {
        "success": True,
        "data": result,
    }


@router.get("/export/stats", response_model=ExportResponse)
async def get_dataset_stats(
    service: ExportService = Depends(get_export_service),
):
    """
    获取数据集统计信息

    返回资产总数、分类统计、标签数量、平均质量分等。
    """
    stats = await service.get_dataset_stats()
    return {
        "success": True,
        "data": stats,
    }


@router.post("/export/quality", response_model=ExportResponse)
async def batch_calculate_quality(
    request: QualityScoreRequest,
    service: ExportService = Depends(get_export_service),
):
    """
    批量计算质量评分

    对指定资产或所有某类型资产计算质量评分。
    """
    asset_type = None
    if request.asset_type:
        try:
            asset_type = AssetType(request.asset_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid asset type")

    stats = await service.batch_calculate_quality(
        asset_ids=request.asset_ids,
        asset_type=asset_type,
    )

    return {
        "success": True,
        "data": stats,
    }


@router.post("/export/duplicates", response_model=ExportResponse)
async def find_duplicates(
    request: FindDuplicatesRequest,
    service: ExportService = Depends(get_export_service),
):
    """
    查找重复资产

    使用向量相似度查找视觉上高度相似的资产对。
    """
    asset_type = None
    if request.asset_type:
        try:
            asset_type = AssetType(request.asset_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid asset type")

    duplicates = await service.find_duplicates_by_vector(
        asset_type=asset_type,
        similarity_threshold=request.similarity_threshold,
    )

    return {
        "success": True,
        "data": {
            "duplicate_count": len(duplicates),
            "duplicates": duplicates,
        },
    }


@router.post("/export/merge", response_model=ExportResponse)
async def merge_duplicates(
    request: MergeDuplicatesRequest,
    service: ExportService = Depends(get_export_service),
):
    """
    合并重复资产

    将多个重复资产合并到主资产，更新引用关系。
    """
    result = await service.merge_duplicates(
        primary_asset_id=request.primary_asset_id,
        duplicate_asset_ids=request.duplicate_asset_ids,
        keep_references=request.keep_references,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "success": True,
        "data": result,
    }


@router.get("/export/quality/{asset_id}")
async def calculate_quality_score(
    asset_id: str,
    service: ExportService = Depends(get_export_service),
):
    """
    计算单个资产的质量评分
    """
    score = await service.calculate_quality_score(asset_id)

    if score is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    return {
        "success": True,
        "data": {
            "asset_id": asset_id,
            "quality_score": score,
        },
    }
