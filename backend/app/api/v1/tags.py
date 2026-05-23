"""
YLCraft — 标签系统 API

GET    /api/v1/tags              — 获取标签树
GET    /api/v1/tags/:id          — 获取标签详情
POST   /api/v1/tags              — 创建标签
PUT    /api/v1/tags/:id          — 更新标签
DELETE /api/v1/tags/:id          — 删除标签

GET    /api/v1/tags/:id/children — 获取子标签
GET    /api/v1/tags/:id/assets   — 获取标签下的资产
POST   /api/v1/tags/batch        — 批量创建标签

POST   /api/v1/tags/:id/assets   — 给资产添加标签
DELETE /api/v1/tags/:id/assets   — 移除资产的标签
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.db.database import get_async_session
from app.db.models.asset_hub import Tag, AssetNode
from app.services.tag.service import TagService
from app.services.auto_tagging.service import AutoTaggingService

router = APIRouter()
logger = logging.getLogger("ylcraft.tags")

# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_tag_service():
    """获取 TagService 实例"""
    async with get_async_session() as session:
        yield TagService(session)

# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class TagResponse(BaseModel):
    success: bool = True
    data: dict

class TagListResponse(BaseModel):
    success: bool = True
    data: List[dict]
    total: int = 0

class TagTreeResponse(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]]

class CreateTagRequest(BaseModel):
    name: str = Field(..., description="标签名称")
    parent_id: Optional[str] = Field(None, description="父标签ID")
    color: Optional[str] = Field(None, description="标签颜色")
    category: Optional[str] = Field(None, description="标签分类")

class UpdateTagRequest(BaseModel):
    name: Optional[str] = Field(None, description="标签名称")
    color: Optional[str] = Field(None, description="标签颜色")
    category: Optional[str] = Field(None, description="标签分类")

class TagAssetRequest(BaseModel):
    asset_id: str = Field(..., description="资产ID")
    confidence: Optional[float] = Field(None, description="置信度")
    source: str = Field("manual", description="标签来源")

class BatchTagRequest(BaseModel):
    asset_ids: List[str] = Field(..., description="资产ID列表")
    tag_id: str = Field(..., description="标签ID")
    confidence: Optional[float] = Field(None, description="置信度")
    source: str = Field("manual", description="标签来源")

class SearchTagsRequest(BaseModel):
    keyword: Optional[str] = Field(None, description="搜索关键词")
    category: Optional[str] = Field(None, description="分类")
    min_asset_count: int = Field(0, description="最小资产数")

class AutoTagRequest(BaseModel):
    asset_ids: List[str] = Field(..., description="资产ID列表")
    confidence_threshold: Optional[float] = Field(0.7, description="置信度阈值")
    use_api: bool = Field(True, description="是否使用外部AI API")
    model: Optional[str] = Field(None, description="AI模型名称")

class AutoTagAssetRequest(BaseModel):
    confidence_threshold: Optional[float] = Field(0.7, description="置信度阈值")
    use_api: bool = Field(True, description="是否使用外部AI API")
    model: Optional[str] = Field(None, description="AI模型名称")

class TagSyncRequest(BaseModel):
    tag_id: Optional[str] = Field(None, description="标签ID（不传则全量同步）")

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _tag_to_dict(tag: Tag) -> dict:
    """Tag ORM 对象 → dict"""
    return {
        "id": tag.id,
        "name": tag.name,
        "parent_id": tag.parent_id,
        "level": tag.level,
        "path": tag.path,
        "color": tag.color,
        "category": tag.category,
        "asset_count": tag.asset_count,
        "created_at": tag.created_at.isoformat() if tag.created_at else None,
    }

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@router.get("/tags", response_model=TagTreeResponse)
async def get_tag_tree(
    root_id: Optional[str] = Query(None, description="根标签ID，不传则获取整棵树"),
    service: TagService = Depends(get_tag_service),
):
    """获取标签树结构"""
    tree = await service.get_tag_tree(root_id)
    return {"success": True, "data": tree}

@router.get("/tags/list", response_model=TagListResponse)
async def list_tags(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类"),
    min_asset_count: int = Query(0, description="最小资产数"),
    service: TagService = Depends(get_tag_service),
):
    """搜索/过滤标签列表"""
    tags = await service.search_tags(keyword, category, min_asset_count)
    return {
        "success": True,
        "data": [_tag_to_dict(tag) for tag in tags],
        "total": len(tags),
    }

@router.get("/tags/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: str,
    service: TagService = Depends(get_tag_service),
):
    """获取标签详情"""
    tag = await service.get_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    return {"success": True, "data": _tag_to_dict(tag)}

@router.post("/tags", response_model=TagResponse)
async def create_tag(
    request: CreateTagRequest,
    service: TagService = Depends(get_tag_service),
):
    """创建标签"""
    tag = await service.create_tag(
        name=request.name,
        parent_id=request.parent_id,
        color=request.color,
        category=request.category,
    )
    return {"success": True, "data": _tag_to_dict(tag)}

@router.put("/tags/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: str,
    request: UpdateTagRequest,
    service: TagService = Depends(get_tag_service),
):
    """更新标签"""
    tag = await service.update_tag(
        tag_id=tag_id,
        name=request.name,
        color=request.color,
        category=request.category,
    )
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    return {"success": True, "data": _tag_to_dict(tag)}

@router.delete("/tags/{tag_id}", response_model=TagResponse)
async def delete_tag(
    tag_id: str,
    cascade: bool = Query(True, description="是否级联删除子标签"),
    service: TagService = Depends(get_tag_service),
):
    """删除标签"""
    success = await service.delete_tag(tag_id, cascade)
    if not success:
        raise HTTPException(status_code=404, detail="标签不存在")
    return {"success": True, "data": {"message": "标签删除成功"}}

@router.get("/tags/{tag_id}/children", response_model=TagListResponse)
async def get_tag_children(
    tag_id: str,
    service: TagService = Depends(get_tag_service),
):
    """获取标签的直接子标签"""
    children = await service.get_children(tag_id)
    return {
        "success": True,
        "data": [_tag_to_dict(tag) for tag in children],
        "total": len(children),
    }

@router.get("/tags/{tag_id}/descendants", response_model=TagListResponse)
async def get_tag_descendants(
    tag_id: str,
    service: TagService = Depends(get_tag_service),
):
    """获取标签的所有后代标签"""
    descendants = await service.get_descendants(tag_id)
    return {
        "success": True,
        "data": [_tag_to_dict(tag) for tag in descendants],
        "total": len(descendants),
    }

@router.get("/tags/{tag_id}/ancestors", response_model=TagListResponse)
async def get_tag_ancestors(
    tag_id: str,
    service: TagService = Depends(get_tag_service),
):
    """获取标签的所有祖先标签"""
    ancestors = await service.get_ancestors(tag_id)
    return {
        "success": True,
        "data": [_tag_to_dict(tag) for tag in ancestors],
        "total": len(ancestors),
    }

@router.get("/tags/categories", response_model=TagListResponse)
async def get_tag_categories(
    service: TagService = Depends(get_tag_service),
):
    """获取标签分类统计"""
    stats = await service.get_category_stats()
    return {
        "success": True,
        "data": stats,
        "total": len(stats),
    }

@router.get("/tags/{tag_id}/assets", response_model=TagListResponse)
async def get_tagged_assets(
    tag_id: str,
    service: TagService = Depends(get_tag_service),
):
    """获取标签下的所有资产"""
    assets = await service.get_tagged_assets(tag_id)
    
    asset_list = []
    for asset in assets:
        asset_list.append({
            "id": asset.id,
            "name": asset.name,
            "asset_type": asset.asset_type.value,
            "thumbnail_url": asset.thumbnail_url,
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
        })
    
    return {
        "success": True,
        "data": asset_list,
        "total": len(asset_list),
    }

@router.post("/tags/{tag_id}/assets", response_model=TagResponse)
async def tag_asset(
    tag_id: str,
    request: TagAssetRequest,
    service: TagService = Depends(get_tag_service),
):
    """给资产添加标签"""
    link = await service.tag_asset(
        asset_id=request.asset_id,
        tag_id=tag_id,
        confidence=request.confidence,
        source=request.source,
    )
    
    if not link:
        raise HTTPException(status_code=400, detail="添加标签失败")
    
    return {
        "success": True,
        "data": {
            "asset_id": link.asset_node_id,
            "tag_id": link.tag_id,
            "confidence": link.confidence,
            "source": link.source,
        },
    }

@router.delete("/tags/{tag_id}/assets", response_model=TagResponse)
async def untag_asset(
    tag_id: str,
    asset_id: str = Query(..., description="资产ID"),
    service: TagService = Depends(get_tag_service),
):
    """移除资产的标签"""
    success = await service.untag_asset(asset_id, tag_id)
    if not success:
        raise HTTPException(status_code=400, detail="移除标签失败")
    return {"success": True, "data": {"message": "标签已移除"}}

@router.post("/tags/batch", response_model=TagResponse)
async def batch_tag_assets(
    request: BatchTagRequest,
    service: TagService = Depends(get_tag_service),
):
    """批量给多个资产添加标签"""
    count = await service.batch_tag_assets(
        asset_ids=request.asset_ids,
        tag_id=request.tag_id,
        confidence=request.confidence,
        source=request.source,
    )
    return {"success": True, "data": {"count": count, "message": f"成功为 {count} 个资产添加标签"}}

@router.get("/assets/{asset_id}/tags", response_model=TagListResponse)
async def get_asset_tags(
    asset_id: str,
    service: TagService = Depends(get_tag_service),
):
    """获取资产的所有标签"""
    tags = await service.get_asset_tags(asset_id)
    return {
        "success": True,
        "data": [_tag_to_dict(tag) for tag in tags],
        "total": len(tags),
    }

@router.get("/tags/suggest/{asset_id}", response_model=TagListResponse)
async def suggest_tags(
    asset_id: str,
    service: TagService = Depends(get_tag_service),
):
    """根据资产内容建议标签"""
    suggestions = await service.suggest_tags(asset_id)
    return {
        "success": True,
        "data": suggestions,
        "total": len(suggestions),
    }

# ---------------------------------------------------------------------------
# 自动标签 API
# ---------------------------------------------------------------------------

async def get_auto_tagging_service():
    """获取 AutoTaggingService 实例"""
    async with get_async_session() as session:
        yield AutoTaggingService(session)

@router.post("/assets/{asset_id}/auto-tag", response_model=TagListResponse)
async def auto_tag_asset(
    asset_id: str,
    request: AutoTagAssetRequest,
    service: AutoTaggingService = Depends(get_auto_tagging_service),
):
    """给单个资产自动打标签"""
    links = await service.auto_tag_asset(
        asset_id=asset_id,
        confidence_threshold=request.confidence_threshold,
        use_api=request.use_api,
        model=request.model,
    )
    return {
        "success": True,
        "data": [
            {
                "asset_id": link.asset_node_id,
                "tag_id": link.tag_id,
                "confidence": link.confidence,
                "source": link.source,
            }
            for link in links
        ],
        "total": len(links),
    }

@router.post("/assets/batch-auto-tag", response_model=TagListResponse)
async def auto_tag_batch_assets(
    request: AutoTagRequest,
    service: AutoTaggingService = Depends(get_auto_tagging_service),
):
    """批量给资产自动打标签"""
    results = await service.auto_tag_batch(
        asset_ids=request.asset_ids,
        confidence_threshold=request.confidence_threshold,
    )
    
    # 整理结果
    all_links = []
    for links in results.values():
        all_links.extend([
            {
                "asset_id": link.asset_node_id,
                "tag_id": link.tag_id,
                "confidence": link.confidence,
                "source": link.source,
            }
            for link in links
        ])
    
    return {
        "success": True,
        "data": all_links,
        "total": len(all_links),
    }

@router.post("/tags/sync-counts", response_model=TagResponse)
async def sync_tag_counts(
    request: TagSyncRequest,
    service: TagService = Depends(get_tag_service),
):
    """同步标签的 asset_count"""
    await service.sync_asset_counts(request.tag_id)
    return {
        "success": True,
        "data": {"message": "标签计数同步成功"},
    }
