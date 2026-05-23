"""
YLCraft — 谱系追踪 API

GET    /api/v1/lineage/:id           — 获取完整谱系
GET    /api/v1/lineage/:id/upstream  — 获取上游谱系
GET    /api/v1/lineage/:id/downstream— 获取下游谱系
POST   /api/v1/lineage/link          — 创建谱系关系
POST   /api/v1/lineage/chain         — 创建 Prompt→Model→Output 链
GET    /api/v1/lineage/:id/stats     — 获取谱系统计
GET    /api/v1/lineage/common-ancestor — 查找公共祖先
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.db.models.asset_hub import RelationType
from app.services.lineage.service import LineageService

router = APIRouter()
logger = logging.getLogger("ylcraft.lineage")

# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_lineage_service():
    """获取 LineageService 实例"""
    async with get_async_session() as session:
        yield LineageService(session)

# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class LineageResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]

class LineageListResponse(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]]
    total: int

class LinkAssetsRequest(BaseModel):
    source_id: str = Field(..., description="源资产ID")
    target_id: str = Field(..., description="目标资产ID")
    relation_type: str = Field(..., description="关系类型: DERIVED_FROM, USES, REFERENCES, CONTAINS, VARIANT_OF")
    context: Optional[Dict[str, Any]] = Field(None, description="关系上下文")

class CreateChainRequest(BaseModel):
    prompt_asset_id: str = Field(..., description="Prompt 资产ID")
    model_asset_id: str = Field(..., description="Model 资产ID")
    output_asset_id: str = Field(..., description="Output 资产ID")
    extra_context: Optional[Dict[str, Any]] = Field(None, description="额外上下文")

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@router.get("/lineage/{asset_id}", response_model=LineageResponse)
async def get_full_lineage(
    asset_id: str,
    max_depth: int = Query(10, description="最大追溯深度"),
    service: LineageService = Depends(get_lineage_service),
):
    """
    获取完整谱系

    返回资产的完整上下游谱系，以及 D3.js/cytoscape.js 兼容的图数据。
    """
    result = await service.get_full_lineage(asset_id, max_depth)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return {"success": True, "data": result}


@router.get("/lineage/{asset_id}/upstream", response_model=LineageListResponse)
async def get_upstream_lineage(
    asset_id: str,
    max_depth: int = Query(10, description="最大追溯深度"),
    service: LineageService = Depends(get_lineage_service),
):
    """
    获取上游谱系

    向上追溯到 Prompt、Model 等上游资产。
    """
    upstream = await service.get_upstream(asset_id, max_depth)

    return {
        "success": True,
        "data": upstream,
        "total": len(upstream),
    }


@router.get("/lineage/{asset_id}/downstream", response_model=LineageListResponse)
async def get_downstream_lineage(
    asset_id: str,
    max_depth: int = Query(10, description="最大追溯深度"),
    service: LineageService = Depends(get_lineage_service),
):
    """
    获取下游谱系

    向下追溯到变体、后裔等下游资产。
    """
    downstream = await service.get_downstream(asset_id, max_depth)

    return {
        "success": True,
        "data": downstream,
        "total": len(downstream),
    }


@router.post("/lineage/link", response_model=LineageResponse)
async def link_assets(
    request: LinkAssetsRequest,
    service: LineageService = Depends(get_lineage_service),
):
    """
    创建资产间的谱系关系

    例如：model -> output (USES)
    """
    try:
        relation_type = RelationType(request.relation_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid relation_type. Must be one of: {[rt.value for rt in RelationType]}"
        )

    relation = await service.link_assets(
        source_id=request.source_id,
        target_id=request.target_id,
        relation_type=relation_type,
        context=request.context,
    )

    if not relation:
        raise HTTPException(status_code=400, detail="关系已存在或创建失败")

    return {
        "success": True,
        "data": {
            "id": str(relation.id),
            "source_id": str(relation.source_id),
            "target_id": str(relation.target_id),
            "relation_type": relation.relation_type.value,
        },
    }


@router.post("/lineage/chain", response_model=LineageResponse)
async def create_prompt_model_output_chain(
    request: CreateChainRequest,
    service: LineageService = Depends(get_lineage_service),
):
    """
    创建 Prompt → Model → Output 谱系链

    自动创建 model→output 和 prompt→output 两个关系。
    """
    result = await service.create_prompt_to_output_chain(
        prompt_asset_id=request.prompt_asset_id,
        model_asset_id=request.model_asset_id,
        output_asset_id=request.output_asset_id,
        extra_context=request.extra_context,
    )

    return {
        "success": True,
        "data": result,
    }


@router.get("/lineage/{asset_id}/stats", response_model=LineageResponse)
async def get_lineage_stats(
    asset_id: str,
    service: LineageService = Depends(get_lineage_service),
):
    """
    获取谱系统计信息

    返回上下游数量、关系类型分布、最大深度等。
    """
    stats = await service.get_lineage_stats(asset_id)
    return {"success": True, "data": stats}


@router.get("/lineage/common-ancestor", response_model=LineageResponse)
async def find_common_ancestor(
    asset_id_1: str = Query(..., description="资产1 ID"),
    asset_id_2: str = Query(..., description="资产2 ID"),
    service: LineageService = Depends(get_lineage_service),
):
    """
    查找两个资产的公共祖先

    用于找出不同生成结果的共同来源（如相同的 Model 或 Prompt）。
    """
    common = await service.find_common_ancestor(asset_id_1, asset_id_2)

    if not common:
        return {
            "success": True,
            "data": {"found": False, "ancestor": None},
        }

    return {
        "success": True,
        "data": {"found": True, "ancestor": common},
    }


@router.delete("/lineage/relation/{relation_id}")
async def delete_relation(
    relation_id: str,
    service: LineageService = Depends(get_lineage_service),
):
    """
    删除谱系关系
    """
    success = await service.delete_relation(relation_id)

    if not success:
        raise HTTPException(status_code=404, detail="关系不存在")

    return {"success": True, "data": {"message": "关系已删除"}}


@router.delete("/lineage/{asset_id}")
async def delete_all_relations(
    asset_id: str,
    service: LineageService = Depends(get_lineage_service),
):
    """
    删除资产的所有谱系关系
    """
    count = await service.delete_all_relations(asset_id)

    return {
        "success": True,
        "data": {"message": f"已删除 {count} 个关系"},
    }
