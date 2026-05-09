"""
YLCraft — 素材资产库 API

GET    /api/v1/assets              — 资产列表（分页/搜索/过滤）
GET    /api/v1/assets/:id          — 资产详情
PUT    /api/v1/assets/:id          — 更新资产（元数据/标签）
DELETE /api/v1/assets/:id           — 删除资产
POST   /api/v1/assets/:id/tags     — 更新标签

GET    /api/v1/assets/:id/download — 下载资产文件
GET    /api/v1/assets/:id/thumbnail — 代理加载封面图

GET    /api/v1/assets/tags         — 标签列表
POST   /api/v1/assets/tags         — 创建标签
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from app.db.database import get_async_session
from app.db.models.asset import Asset, AssetType, AssetStatus, AssetTag
from app.services.asset.service import AssetService

router = APIRouter()
logger = logging.getLogger("ylcraft.assets")


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_asset_service():
    """获取 AssetService 实例"""
    async with get_async_session() as session:
        yield AssetService(session)


# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class AssetResponse(BaseModel):
    success: bool = True
    data: dict


class AssetListResponse(BaseModel):
    success: bool = True
    data: list[dict]
    total: int
    page: int
    page_size: int


class TagResponse(BaseModel):
    success: bool = True
    data: dict


class TagListResponse(BaseModel):
    success: bool = True
    data: list[dict]


def _asset_to_dict(asset: Asset) -> dict:
    """Asset ORM 对象 → dict（用于 JSON 序列化）"""
    return {
        "id": asset.id,
        "asset_type": asset.asset_type,
        "title": asset.title,
        "description": asset.description,
        "file_path": asset.file_path,
        "file_size": asset.file_size,
        "mime_type": asset.mime_type,
        "duration": asset.duration,
        "width": asset.width,
        "height": asset.height,
        "source_url": asset.source_url,
        "platform": asset.platform,
        "author": asset.author,
        "author_url": asset.author_url,
        "thumbnail_path": asset.thumbnail_path,
        "thumbnail_url": f"/api/v1/assets/{asset.id}/thumbnail" if asset.thumbnail_path else None,
        "status": asset.status,
        "error_message": asset.error_message,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
        "downloaded_at": asset.downloaded_at.isoformat() if asset.downloaded_at else None,
        "use_count": asset.use_count,
        "last_used_at": asset.last_used_at.isoformat() if asset.last_used_at else None,
        "tags": json.loads(asset.tags) if asset.tags else [],
        "metadata": json.loads(asset.metadata_json) if asset.metadata_json else {},
    }


def _tag_to_dict(tag: AssetTag) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
        "asset_count": tag.asset_count,
        "created_at": tag.created_at.isoformat() if tag.created_at else None,
    }


# ---------------------------------------------------------------------------
# 资产列表 GET /api/v1/assets
# ---------------------------------------------------------------------------

@router.get("", response_model=AssetListResponse, summary="素材资产列表")
async def list_assets(
    service: AssetService = Depends(get_asset_service),
    asset_type: Optional[str] = Query(None, description="素材类型：video/image/audio/document"),
    platform: Optional[str] = Query(None, description="平台：douyin/kuaishou/bilibili/..."),
    status: Optional[str] = Query(None, description="状态：parsed/downloading/ready/error"),
    search: Optional[str] = Query(None, description="搜索标题"),
    tags: Optional[str] = Query(None, description="标签（逗号分隔）"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="asc / desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    多条件分页查询资产列表。
    """
    at = AssetType(asset_type) if asset_type else None
    st = AssetStatus(status) if status else None
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    assets, total = await service.list_assets(
        asset_type=at,
        platform=platform,
        status=st,
        search=search,
        tags=tag_list,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    return AssetListResponse(
        success=True,
        data=[_asset_to_dict(a) for a in assets],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# 资产详情 GET /api/v1/assets/:id
# ---------------------------------------------------------------------------

@router.get("/{asset_id}", response_model=AssetResponse, summary="资产详情")
async def get_asset(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    return AssetResponse(success=True, data=_asset_to_dict(asset))


# ---------------------------------------------------------------------------
# 更新资产 PUT /api/v1/assets/:id
# ---------------------------------------------------------------------------

class AssetUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


@router.put("/{asset_id}", response_model=AssetResponse, summary="更新资产")
async def update_asset(
    asset_id: str,
    req: AssetUpdateRequest,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if req.title is not None:
        asset.title = req.title
    if req.description is not None:
        asset.description = req.description
    if req.tags is not None:
        await service.update_tags(asset, req.tags)
    asset.updated_at = datetime.now()

    await service.session.commit()
    await service.session.refresh(asset)
    return AssetResponse(success=True, data=_asset_to_dict(asset))


# ---------------------------------------------------------------------------
# 删除资产 DELETE /api/v1/assets/:id
# ---------------------------------------------------------------------------

class DeleteRequest(BaseModel):
    hard: bool = Field(False, description="true=同时删除物理文件，false=仅删除记录")


@router.delete("/{asset_id}", summary="删除资产")
async def delete_asset(
    asset_id: str,
    hard: bool = Query(False, description="true=同时删除物理文件，false=仅删除记录"),
    service: AssetService = Depends(get_asset_service),
):
    ok = await service.delete(asset_id, hard=hard)
    if not ok:
        raise HTTPException(status_code=404, detail="资产不存在")
    return {"success": True, "message": "已删除"}


# ---------------------------------------------------------------------------
# 下载资产文件 GET /api/v1/assets/:id/download
# ---------------------------------------------------------------------------

@router.get("/{asset_id}/download", summary="下载资产文件")
async def download_asset(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    """
    返回资产文件（流式响应，不阻塞）。
    资产必须处于 READY 状态。
    """
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if asset.status != AssetStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"资产状态为 {asset.status}，无法下载",
        )

    if not asset.file_path or not os.path.exists(asset.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = os.path.basename(asset.file_path)
    from urllib.parse import quote

    async def file_iterator():
        chunk_size = 1024 * 1024  # 1MB
        with open(asset.file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type=asset.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename*=utf-8\'\'{quote(filename)}',
            "Content-Length": str(asset.file_size),
        },
    )


# ---------------------------------------------------------------------------
# 标签管理
# ---------------------------------------------------------------------------

class CreateTagRequest(BaseModel):
    name: str
    color: str = "#1890ff"


@router.get("/tags", response_model=TagListResponse, summary="标签列表")
async def list_tags(
    service: AssetService = Depends(get_asset_service),
):
    tags = await service.list_tags()
    return TagListResponse(success=True, data=[_tag_to_dict(t) for t in tags])


@router.post("/tags", response_model=TagResponse, summary="创建标签")
async def create_tag(
    req: CreateTagRequest,
    service: AssetService = Depends(get_asset_service),
):
    tag = await service.get_or_create_tag(req.name, req.color)
    return TagResponse(success=True, data=_tag_to_dict(tag))


# ---------------------------------------------------------------------------
# 图片代理（解决B站等平台跨域问题）
# ---------------------------------------------------------------------------

@router.get("/{asset_id}/thumbnail", summary="代理加载封面图")
async def proxy_thumbnail(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    """
    通过后端代理加载封面图，解决跨域/防盗链问题。
    支持本地文件路径和远程 URL。
    """
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    
    if not asset.thumbnail_path:
        raise HTTPException(status_code=404, detail="封面图不存在")
    
    # 本地文件
    thumb_path = Path(asset.thumbnail_path)
    if thumb_path.exists() and thumb_path.is_file():
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
        media_type = mime_map.get(thumb_path.suffix.lower(), "image/png")
        return FileResponse(thumb_path, media_type=media_type)
    
    # 远程 URL
    try:
        async with httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"https://{asset.platform}.com",
            },
            follow_redirects=True,
            timeout=30.0
        ) as client:
            resp = await client.get(asset.thumbnail_path)
            resp.raise_for_status()
            
            async def streamer():
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    yield chunk
            
            return StreamingResponse(
                streamer(),
                media_type=resp.headers.get("content-type", "image/jpeg"),
                headers={
                    "Cache-Control": "public, max-age=86400",
                }
            )
    except Exception as e:
        logger.error(f"代理加载封面图失败: {e}")
        raise HTTPException(status_code=500, detail="加载封面图失败")

