"""
YLCraft — 资产中枢 API

提供三层资产的完整 REST CRUD：
- AssetNode        /asset-hub/nodes
- AssetVersion     /asset-hub/nodes/{id}/versions
- AssetRepresentation /asset-hub/versions/{id}/representations

配合现有 /tags、/search、/lineage 路由使用。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.db.database import get_async_session
from app.db.models.asset_hub import AssetType, RelationType
from app.services.asset_hub import (
    AssetNodeService,
    AssetVersionService,
    AssetRepresentationService,
)

router = APIRouter()
logger = logging.getLogger("ylcraft.asset_hub")


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_node_service():
    """获取 AssetNodeService 实例"""
    async with get_async_session() as session:
        yield AssetNodeService(session)


async def get_version_service():
    """获取 AssetVersionService 实例"""
    async with get_async_session() as session:
        yield AssetVersionService(session)


async def get_rep_service():
    """获取 AssetRepresentationService 实例"""
    async with get_async_session() as session:
        yield AssetRepresentationService(session)


# ---------------------------------------------------------------------------
# Schemas — AssetNode
# ---------------------------------------------------------------------------

class AssetNodeCreateRequest(BaseModel):
    name: str = Field(..., description="资产名称")
    asset_type: str = Field(..., description="资产类型，如 image/character/world_setting")
    parent_id: Optional[str] = Field(None, description="父节点 ID")
    thumbnail_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = Field(None, description="标签名称列表（自动创建或关联）")
    quality_score: Optional[float] = None
    phash: Optional[str] = None


class AssetNodeUpdateRequest(BaseModel):
    name: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    quality_score: Optional[float] = None
    phash: Optional[str] = None
    increment_use_count: bool = False


class AssetNodeResponse(BaseModel):
    id: str
    name: str
    asset_type: str
    parent_id: Optional[str]
    thumbnail_url: Optional[str]
    metadata: Dict[str, Any] = {}
    tags: List[str] = []
    use_count: int = 0
    quality_score: Optional[float] = None
    phash: Optional[str] = None
    created_at: str
    updated_at: str


class AssetNodeListResponse(BaseModel):
    success: bool = True
    data: List[AssetNodeResponse]
    total: int = 0
    page: int = 1
    page_size: int = 20


# ---------------------------------------------------------------------------
# Schemas — AssetVersion
# ---------------------------------------------------------------------------

class AssetVersionCreateRequest(BaseModel):
    prompt_used: Optional[str] = None
    model_used: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    lineage: Optional[Dict[str, Any]] = None
    parent_version_id: Optional[str] = Field(None, description="上一版本 ID（版本链）")


class AssetVersionResponse(BaseModel):
    id: str
    asset_node_id: str
    version_number: int
    prompt_used: Optional[str]
    model_used: Optional[str]
    params: Dict[str, Any] = {}
    lineage: Dict[str, Any] = {}
    created_at: str


class AssetVersionListResponse(BaseModel):
    success: bool = True
    data: List[AssetVersionResponse]
    total: int = 0


# ---------------------------------------------------------------------------
# Schemas — AssetRepresentation
# ---------------------------------------------------------------------------

class AssetRepresentationCreateRequest(BaseModel):
    file_path: str
    mime_type: str
    file_size: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    format: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class AssetRepresentationResponse(BaseModel):
    id: str
    asset_version_id: str
    file_path: str
    mime_type: str
    file_size: int
    width: Optional[int]
    height: Optional[int]
    duration: Optional[float]
    format: Optional[str]
    extra: Dict[str, Any] = {}


class AssetRepresentationListResponse(BaseModel):
    success: bool = True
    data: List[AssetRepresentationResponse]


# ---------------------------------------------------------------------------
# Schemas — 统计
# ---------------------------------------------------------------------------

class AssetTypeStatsResponse(BaseModel):
    success: bool = True
    data: Dict[str, int]


# ---------------------------------------------------------------------------
# 序列化工具
# ---------------------------------------------------------------------------

def _node_to_response(node, tags=None) -> AssetNodeResponse:
    """AssetNode ORM → 响应 dict"""
    return AssetNodeResponse(
        id=str(node.id),
        name=node.name,
        asset_type=node.asset_type.value if hasattr(node.asset_type, "value") else str(node.asset_type),
        parent_id=str(node.parent_id) if node.parent_id else None,
        thumbnail_url=node.thumbnail_url,
        metadata=node.metadata_json or {},
        tags=[t.name for t in (tags or [])],
        use_count=node.use_count or 0,
        quality_score=node.quality_score,
        phash=node.phash,
        created_at=node.created_at.isoformat() if node.created_at else "",
        updated_at=node.updated_at.isoformat() if node.updated_at else "",
    )


def _version_to_response(v) -> AssetVersionResponse:
    return AssetVersionResponse(
        id=str(v.id),
        asset_node_id=str(v.asset_node_id),
        version_number=v.version_number,
        prompt_used=v.prompt_used,
        model_used=v.model_used,
        params=v.params_json or {},
        lineage=v.lineage_json or {},
        created_at=v.created_at.isoformat() if v.created_at else "",
    )


def _rep_to_response(r) -> AssetRepresentationResponse:
    return AssetRepresentationResponse(
        id=str(r.id),
        asset_version_id=str(r.asset_version_id),
        file_path=r.file_path,
        mime_type=r.mime_type,
        file_size=r.file_size,
        width=r.width,
        height=r.height,
        duration=r.duration,
        format=r.format,
        extra=r.extra_json or {},
    )


# ===========================================================================
# AssetNode 路由
# ===========================================================================

@router.get("/types", response_model=Dict[str, Any], summary="所有资产类型")
async def list_asset_types():
    """返回所有支持的资产类型枚举"""
    return {
        "success": True,
        "data": [{"value": t.value, "label": t.value} for t in AssetType],
    }


@router.get("/nodes", response_model=AssetNodeListResponse, summary="资产节点列表")
async def list_nodes(
    asset_type: Optional[str] = Query(None, description="按类型过滤"),
    parent_id: Optional[str] = Query(None, description="按父节点过滤（'root' 表示只看根节点）"),
    tag_ids: Optional[str] = Query(None, description="标签 ID 列表，逗号分隔"),
    keyword: Optional[str] = Query(None, description="名称模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: AssetNodeService = Depends(get_node_service),
):
    """分页查询资产节点"""
    try:
        tag_id_list = (
            [t.strip() for t in tag_ids.split(",") if t.strip()]
            if tag_ids
            else None
        )

        nodes, total = await service.list_nodes(
            asset_type=asset_type,
            parent_id=parent_id,
            tag_ids=tag_id_list,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )

        data = []
        for node in nodes:
            tags = await service.get_tags(node.id)
            data.append(_node_to_response(node, tags))

        return {
            "success": True,
            "data": data,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.exception(f"[list_nodes] failed: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/nodes", response_model=Dict[str, Any], summary="创建资产节点")
async def create_node(
    req: AssetNodeCreateRequest,
    service: AssetNodeService = Depends(get_node_service),
):
    """创建资产节点"""
    try:
        node = await service.create(
            name=req.name,
            asset_type=req.asset_type,
            parent_id=req.parent_id,
            thumbnail_url=req.thumbnail_url,
            metadata=req.metadata,
            tags=req.tags,
            quality_score=req.quality_score,
            phash=req.phash,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    tags = await service.get_tags(node.id)
    return {"success": True, "data": _node_to_response(node, tags).model_dump()}


@router.get("/nodes/{node_id}", response_model=Dict[str, Any], summary="资产节点详情")
async def get_node(
    node_id: str,
    service: AssetNodeService = Depends(get_node_service),
):
    """获取资产节点详情"""
    node = await service.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="资产节点不存在")
    tags = await service.get_tags(node_id)
    return {"success": True, "data": _node_to_response(node, tags).model_dump()}


@router.put("/nodes/{node_id}", response_model=Dict[str, Any], summary="更新资产节点")
async def update_node(
    node_id: str,
    req: AssetNodeUpdateRequest,
    service: AssetNodeService = Depends(get_node_service),
):
    """更新资产节点字段"""
    node = await service.update(
        node_id=node_id,
        name=req.name,
        thumbnail_url=req.thumbnail_url,
        metadata=req.metadata,
        quality_score=req.quality_score,
        phash=req.phash,
        increment_use_count=req.increment_use_count,
    )
    if not node:
        raise HTTPException(status_code=404, detail="资产节点不存在")
    tags = await service.get_tags(node_id)
    return {"success": True, "data": _node_to_response(node, tags).model_dump()}


@router.delete("/nodes/{node_id}", response_model=Dict[str, Any], summary="删除资产节点")
async def delete_node(
    node_id: str,
    cascade: bool = Query(False, description="是否级联删除子节点"),
    service: AssetNodeService = Depends(get_node_service),
):
    """删除资产节点"""
    try:
        ok = await service.delete(node_id, cascade=cascade)
    except ValueError as exc:
        # 如「存在子节点需 cascade」：给可操作的 400，而不是裸 500
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="资产节点不存在")
    return {"success": True, "message": "已删除"}


@router.get("/nodes/{node_id}/children", response_model=AssetNodeListResponse, summary="子节点列表")
async def list_node_children(
    node_id: str,
    service: AssetNodeService = Depends(get_node_service),
):
    """获取直接子节点（角色的不同装扮等）"""
    children = await service.list_children(node_id)
    data = []
    for node in children:
        tags = await service.get_tags(node.id)
        data.append(_node_to_response(node, tags))
    return {"success": True, "data": data, "total": len(data)}


@router.post("/nodes/{node_id}/tags", response_model=Dict[str, Any], summary="批量添加标签")
async def add_node_tags(
    node_id: str,
    tag_names: List[str],
    service: AssetNodeService = Depends(get_node_service),
):
    """按名称批量添加标签（不存在自动创建）"""
    await service.add_tags(node_id, tag_names)
    tags = await service.get_tags(node_id)
    return {
        "success": True,
        "data": [{"id": str(t.id), "name": t.name} for t in tags],
    }


# ===========================================================================
# AssetVersion 路由
# ===========================================================================

@router.get(
    "/nodes/{node_id}/versions",
    response_model=AssetVersionListResponse,
    summary="资产版本列表",
)
async def list_versions(
    node_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: AssetVersionService = Depends(get_version_service),
):
    """获取某资产节点的所有版本（按版本号倒序）"""
    versions, total = await service.list_versions(
        asset_node_id=node_id,
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "data": [_version_to_response(v).model_dump() for v in versions],
        "total": total,
    }


@router.post(
    "/nodes/{node_id}/versions",
    response_model=Dict[str, Any],
    summary="创建资产版本",
)
async def create_version(
    node_id: str,
    req: AssetVersionCreateRequest,
    service: AssetVersionService = Depends(get_version_service),
):
    """为资产节点创建新版本快照"""
    try:
        version = await service.create(
            asset_node_id=node_id,
            prompt_used=req.prompt_used,
            model_used=req.model_used,
            params=req.params,
            lineage=req.lineage,
            parent_version_id=req.parent_version_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "data": _version_to_response(version).model_dump()}


@router.get(
    "/versions/{version_id}",
    response_model=Dict[str, Any],
    summary="版本详情",
)
async def get_version(
    version_id: str,
    service: AssetVersionService = Depends(get_version_service),
):
    version = await service.get(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"success": True, "data": _version_to_response(version).model_dump()}


@router.delete(
    "/versions/{version_id}",
    response_model=Dict[str, Any],
    summary="删除版本",
)
async def delete_version(
    version_id: str,
    service: AssetVersionService = Depends(get_version_service),
):
    """删除版本（不允许删除唯一版本）"""
    try:
        ok = await service.delete(version_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"success": True, "message": "已删除"}


# ===========================================================================
# AssetRepresentation 路由
# ===========================================================================

@router.get(
    "/versions/{version_id}/representations",
    response_model=AssetRepresentationListResponse,
    summary="版本文件列表",
)
async def list_representations(
    version_id: str,
    service: AssetRepresentationService = Depends(get_rep_service),
):
    """获取版本下的所有文件表示"""
    reps = await service.list_by_version(version_id)
    return {
        "success": True,
        "data": [_rep_to_response(r).model_dump() for r in reps],
    }


@router.post(
    "/versions/{version_id}/representations",
    response_model=Dict[str, Any],
    summary="创建文件表示",
)
async def create_representation(
    version_id: str,
    req: AssetRepresentationCreateRequest,
    service: AssetRepresentationService = Depends(get_rep_service),
):
    """为版本创建文件表示"""
    try:
        rep = await service.create(
            asset_version_id=version_id,
            file_path=req.file_path,
            mime_type=req.mime_type,
            file_size=req.file_size,
            width=req.width,
            height=req.height,
            duration=req.duration,
            format=req.format,
            extra=req.extra,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "data": _rep_to_response(rep).model_dump()}


@router.delete(
    "/representations/{rep_id}",
    response_model=Dict[str, Any],
    summary="删除文件表示",
)
async def delete_representation(
    rep_id: str,
    service: AssetRepresentationService = Depends(get_rep_service),
):
    ok = await service.delete(rep_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文件表示不存在")
    return {"success": True, "message": "已删除"}


# ===========================================================================
# 统计路由
# ===========================================================================

@router.get("/stats/type-counts", response_model=AssetTypeStatsResponse, summary="按类型统计")
async def get_type_counts(
    service: AssetNodeService = Depends(get_node_service),
):
    """按资产类型统计数量"""
    counts = await service.count_by_type()
    return {"success": True, "data": counts}


# ===========================================================================
# 标签种子路由
# ===========================================================================

DEFAULT_TAG_TREE = [
    {
        "name": "类型",
        "category": "type",
        "color": "#3b82f6",
        "children": ["角色", "角色立绘", "背景", "画风", "道具", "场景", "分镜", "漫画页"],
    },
    {
        "name": "风格",
        "category": "style",
        "color": "#a855f7",
        "children": ["写实", "动漫", "国风", "赛博朋克", "水墨"],
    },
    {
        "name": "来源",
        "category": "source",
        "color": "#10b981",
        "children": ["AI生成", "上传", "采集", "解析"],
    },
    {
        "name": "状态",
        "category": "status",
        "color": "#f59e0b",
        "children": ["草稿", "成品", "已弃用"],
    },
]


@router.post("/seed-tags", response_model=Dict[str, Any], summary="初始化默认标签树")
async def seed_default_tags(
    dry_run: bool = Query(False, description="只打印不写入"),
):
    """
    初始化资产中枢的预设标签树（幂等，可重复执行）。

    标签树结构：
    - 类型：角色 / 角色立绘 / 背景 / 画风 / 道具 / 场景 / 分镜 / 漫画页
    - 风格：写实 / 动漫 / 国风 / 赛博朋克 / 水墨
    - 来源：AI生成 / 上传 / 采集 / 解析
    - 状态：草稿 / 成品 / 已弃用
    """
    from uuid import uuid4
    from app.db.models.asset_hub import Tag
    from sqlalchemy import select as sa_select

    stats = {"created": 0, "skipped": 0}
    created_tags: List[Dict[str, str]] = []

    async with get_async_session() as session:
        async with session.begin():
            for root_def in DEFAULT_TAG_TREE:
                root_name = root_def["name"]
                root_category = root_def.get("category")
                root_color = root_def.get("color")

                # 查找根标签
                stmt = sa_select(Tag).where(
                    Tag.name == root_name, Tag.parent_id.is_(None)
                ).limit(1)
                existing = (await session.execute(stmt)).scalar_one_or_none()

                if existing:
                    stats["skipped"] += 1
                    root_tag = existing
                else:
                    if dry_run:
                        created_tags.append({"name": root_name, "path": f"root/{root_name}"})
                        stats["created"] += 1
                        continue
                    root_tag = Tag(
                        id=str(uuid4()),
                        name=root_name,
                        parent_id=None,
                        level=0,
                        path=f"root/{root_name}",
                        category=root_category,
                        color=root_color,
                        asset_count=0,
                    )
                    session.add(root_tag)
                    await session.flush()
                    await session.refresh(root_tag)
                    stats["created"] += 1
                    created_tags.append({"id": root_tag.id, "name": root_name, "path": root_tag.path})

                # 子标签
                for child_name in root_def.get("children", []):
                    child_stmt = sa_select(Tag).where(
                        Tag.name == child_name, Tag.parent_id == root_tag.id
                    ).limit(1)
                    child_existing = (await session.execute(child_stmt)).scalar_one_or_none()
                    if child_existing:
                        stats["skipped"] += 1
                        continue
                    if dry_run:
                        created_tags.append({"name": child_name, "path": f"{root_tag.path}/{child_name}"})
                        stats["created"] += 1
                        continue
                    child_tag = Tag(
                        id=str(uuid4()),
                        name=child_name,
                        parent_id=root_tag.id,
                        level=1,
                        path=f"{root_tag.path}/{child_name}",
                        category=root_category,
                        color=root_color,
                        asset_count=0,
                    )
                    session.add(child_tag)
                    await session.flush()
                    stats["created"] += 1
                    created_tags.append({"id": child_tag.id, "name": child_name, "path": child_tag.path})

    return {
        "success": True,
        "message": f"新增 {stats['created']} 个，跳过 {stats['skipped']} 个（已存在）",
        "stats": stats,
        "tags": created_tags,
    }
