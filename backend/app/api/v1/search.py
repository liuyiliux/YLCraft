"""
YLCraft — 向量搜索 API

POST   /api/v1/search/hybrid       — 混合搜索（向量 + 全文 + 标签）
POST   /api/v1/search/by-text       — 文本相似度搜索
POST   /api/v1/search/by-image      — 图像相似度搜索
POST   /api/v1/search/by-embedding  — 向量直接搜索

GET    /api/v1/search/similar/:id   — 获取相似资产（"还喜欢"）
POST   /api/v1/embed/text           — 文本嵌入
POST   /api/v1/embed/image          — 图像嵌入
POST   /api/v1/embed/batch          — 批量嵌入
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.services.embedding.service import EmbeddingService

router = APIRouter()
logger = logging.getLogger("ylcraft.search")

# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_embedding_service():
    """获取 EmbeddingService 实例，自动查找数据库中配置的 embedding provider"""
    async with get_async_session() as session:
        from app.db.models.ai_connector import AIConnector, AIProviderType
        from sqlalchemy import select
        result = await session.execute(
            select(AIConnector)
            .where(AIConnector.provider_type == AIProviderType.embedding)
            .where(AIConnector.is_active == True)
            .order_by(AIConnector.priority)
            .limit(1)
        )
        conn = result.scalar_one_or_none()
        provider_name = conn.name if conn else None
        yield EmbeddingService(session, provider_name=provider_name)

# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class SearchResponse(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]]
    total: int
    query: str

class HybridSearchRequest(BaseModel):
    query: str = Field(..., description="搜索文本")
    top_k: int = Field(10, description="返回结果数量")
    vector_weight: float = Field(0.7, description="向量搜索权重 (0-1)")
    text_weight: float = Field(0.3, description="全文搜索权重 (0-1)")
    min_similarity: float = Field(0.0, description="最小相似度阈值")
    tag_filters: Optional[List[str]] = Field(None, description="标签过滤")
    asset_type: Optional[str] = Field(None, description="资产类型过滤")

class TextSearchRequest(BaseModel):
    query: str = Field(..., description="搜索文本")
    top_k: int = Field(10, description="返回结果数量")
    min_similarity: float = Field(0.0, description="最小相似度阈值")
    asset_type: Optional[str] = Field(None, description="资产类型过滤")

class ImageSearchRequest(BaseModel):
    image_path: str = Field(..., description="图片路径或URL")
    top_k: int = Field(10, description="返回结果数量")
    min_similarity: float = Field(0.0, description="最小相似度阈值")
    asset_type: Optional[str] = Field(None, description="资产类型过滤")

class EmbeddingRequest(BaseModel):
    asset_id: str = Field(..., description="资产ID")
    text: Optional[str] = Field(None, description="文本内容")
    image_path: Optional[str] = Field(None, description="图片路径")

class BatchEmbeddingRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(..., description="批量嵌入列表")

class SimilarAssetsRequest(BaseModel):
    asset_id: str = Field(..., description="资产ID")
    top_k: int = Field(10, description="返回相似资产数量")

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@router.post("/search/hybrid", response_model=SearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    混合搜索

    一次查询完成向量搜索 + 全文搜索 + 标签过滤，综合排序返回结果。
    """
    results = await service.hybrid_search(
        query_text=request.query,
        top_k=request.top_k,
        vector_weight=request.vector_weight,
        text_weight=request.text_weight,
        min_similarity=request.min_similarity,
        tag_filters=request.tag_filters,
        asset_type_filter=request.asset_type,
    )

    return {
        "success": True,
        "data": results,
        "total": len(results),
        "query": request.query,
    }


@router.post("/search/by-text", response_model=SearchResponse)
async def search_by_text(
    request: TextSearchRequest,
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    文本相似度搜索

    将查询文本转换为向量，在资产向量库中查找最相似的资产。
    """
    results = await service.search_by_text(
        query_text=request.query,
        top_k=request.top_k,
        min_similarity=request.min_similarity,
        asset_type_filter=request.asset_type,
    )

    return {
        "success": True,
        "data": results,
        "total": len(results),
        "query": request.query,
    }


@router.post("/search/by-image", response_model=SearchResponse)
async def search_by_image(
    request: ImageSearchRequest,
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    图像相似度搜索

    将查询图片转换为向量，在资产向量库中查找视觉上最相似的资产。
    """
    results = await service.search_by_image(
        image_path=request.image_path,
        top_k=request.top_k,
        min_similarity=request.min_similarity,
        asset_type_filter=request.asset_type,
    )

    return {
        "success": True,
        "data": results,
        "total": len(results),
        "query": request.image_path,
    }


@router.post("/search/by-embedding", response_model=SearchResponse)
async def search_by_embedding(
    query_vector: List[float],
    top_k: int = Query(10, description="返回结果数量"),
    min_similarity: float = Query(0.0, description="最小相似度阈值"),
    asset_type: Optional[str] = Query(None, description="资产类型过滤"),
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    向量直接搜索

    直接使用给定的向量进行相似度搜索。
    """
    results = await service.search_by_embedding(
        query_vector=query_vector,
        top_k=top_k,
        min_similarity=min_similarity,
        asset_type_filter=asset_type,
    )

    return {
        "success": True,
        "data": results,
        "total": len(results),
        "query": "embedding_search",
    }


@router.get("/search/similar/{asset_id}", response_model=SearchResponse)
async def get_similar_assets(
    asset_id: str,
    top_k: int = Query(10, description="返回相似资产数量"),
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    获取相似资产

    基于资产的嵌入向量，返回视觉或语义上最相似的其他资产（"还喜欢"推荐）。
    """
    # 获取资产的嵌入向量
    info = await service.get_embedding_info(asset_id)

    if not info["embeddings"]:
        raise HTTPException(status_code=404, detail="资产没有嵌入向量")

    # 使用第一个嵌入向量进行搜索
    from app.db.models.asset_hub import AssetEmbedding
    async with get_async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(AssetEmbedding)
            .where(AssetEmbedding.asset_node_id == asset_id)
            .limit(1)
        )
        embedding_record = result.scalar_one_or_none()

        if not embedding_record:
            raise HTTPException(status_code=404, detail="找不到嵌入向量")

        # 搜索相似资产（排除自身）
        results = await service.search_by_embedding(
            query_vector=embedding_record.embedding,
            top_k=top_k + 1,  # 多取一个，因为结果可能包含自身
            asset_type_filter=None,
        )

        # 过滤掉自身
        results = [r for r in results if r["asset_id"] != asset_id][:top_k]

    return {
        "success": True,
        "data": results,
        "total": len(results),
        "query": asset_id,
    }


# ---------------------------------------------------------------------------
# 嵌入接口
# ---------------------------------------------------------------------------

@router.post("/embed/text")
async def embed_text(
    request: EmbeddingRequest,
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    文本嵌入

    将文本转换为向量并存储到资产的嵌入记录中。
    """
    if not request.text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    result = await service.store_text_embedding(
        asset_id=request.asset_id,
        text=request.text,
    )

    if not result:
        raise HTTPException(status_code=500, detail="嵌入失败")

    return {
        "success": True,
        "data": result,
    }


@router.post("/embed/image")
async def embed_image(
    request: EmbeddingRequest,
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    图像嵌入

    将图像转换为向量并存储到资产的嵌入记录中。
    """
    if not request.image_path:
        raise HTTPException(status_code=400, detail="image_path 不能为空")

    result = await service.store_image_embedding(
        asset_id=request.asset_id,
        image_path=request.image_path,
    )

    if not result:
        raise HTTPException(status_code=500, detail="图像嵌入失败")

    return {
        "success": True,
        "data": result,
    }


@router.post("/embed/batch")
async def batch_embed(
    request: BatchEmbeddingRequest,
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    批量嵌入

    批量处理多个资产的嵌入。
    """
    asset_ids = []
    texts = []
    image_paths = []

    for item in request.items:
        asset_ids.append(item["asset_id"])
        texts.append(item.get("text"))
        image_paths.append(item.get("image_path"))

    stats = await service.batch_embed_and_store(
        asset_ids=asset_ids,
        texts=texts,
        image_paths=image_paths,
    )

    return {
        "success": True,
        "data": stats,
    }


@router.get("/embed/{asset_id}")
async def get_embedding_info(
    asset_id: str,
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    获取资产的嵌入信息

    返回资产的所有嵌入向量信息（模型、维度、创建时间等）。
    """
    info = await service.get_embedding_info(asset_id)

    if not info["embeddings"]:
        raise HTTPException(status_code=404, detail="资产没有嵌入向量")

    return {
        "success": True,
        "data": info,
    }


@router.delete("/embed/{asset_id}")
async def delete_embedding(
    asset_id: str,
    model: Optional[str] = Query(None, description="嵌入模型类型"),
    service: EmbeddingService = Depends(get_embedding_service),
):
    """
    删除资产的嵌入向量
    """
    success = await service.delete_embedding(asset_id, model)

    if not success:
        raise HTTPException(status_code=404, detail="资产没有嵌入向量")

    return {
        "success": True,
        "data": {"message": "嵌入向量已删除"},
    }
