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

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse, FileResponse, Response
from pydantic import BaseModel, Field

from app.db.database import get_async_session
from app.db.models.asset import Asset, AssetTag
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


def _asset_to_dict(asset: Asset, include_metadata: bool = False) -> dict:
    """Asset ORM 对象 → dict（用于 JSON 序列化）
    
    Args:
        asset: Asset ORM 对象
        include_metadata: 是否包含完整 metadata（详情页需要，列表页不需要）
    """
    # 解析 metadata_json
    metadata = {}
    if asset.metadata_json:
        try:
            metadata = json.loads(asset.metadata_json)
        except Exception:
            pass
    
    def _format_datetime(dt) -> Optional[str]:
        """将 datetime 对象格式化为可读字符串"""
        if not dt:
            return None
        # 格式：2026-05-23 18:37:56
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def _get_resolution_label(width: int, height: int) -> str:
        """根据分辨率返回友好的标签"""
        if not width or not height:
            return ""
        
        # 根据高度判断分辨率等级
        if height >= 2160:
            return "4K"
        elif height >= 1440:
            return "2K"
        elif height >= 1080:
            return "1080P"
        elif height >= 720:
            return "720P"
        elif height >= 480:
            return "480P"
        elif height >= 360:
            return "360P"
        else:
            return ""
    
    def _format_resolution(width: int, height: int) -> Optional[str]:
        """格式化分辨率显示，如：1280x720 (720P)"""
        if not width or not height:
            return None
        label = _get_resolution_label(width, height)
        if label:
            return f"{width}x{height} ({label})"
        return f"{width}x{height}"
    
    # 基础字段（列表和详情都需要）
    result = {
        "id": asset.id,
        "type": asset.type,
        "title": asset.title,
        "platform": asset.platform,
        "author": asset.author,
        "status": asset.status,
        "source_type": asset.source_type,
        "source_url": asset.source_url,
        "tags": json.loads(asset.tags) if asset.tags else [],
        "created_at": _format_datetime(asset.created_at),
        "updated_at": _format_datetime(asset.updated_at),
        "downloaded_at": _format_datetime(asset.updated_at) if asset.status == "READY" else None,
        "thumbnail_url": f"/api/v1/assets/{asset.id}/thumbnail" if asset.cover_url else None,
        "duration": asset.duration,
        "width": asset.width,
        "height": asset.height,
        "file_size": asset.file_size,
        "resolution": _format_resolution(asset.width, asset.height),
    }
    
    # AI 生成需要的最小 metadata（用于列表跳转）
    # 只返回必要信息，不包含 base64 图片数据
    if asset.source_type == 'ai_generated':
        reference_images = metadata.get("reference_images", []) or []
        source_image = metadata.get("source_image", "")
        result["metadata"] = {
            "prompt": metadata.get("prompt", ""),
            "negative_prompt": metadata.get("negative_prompt", ""),
            "model": metadata.get("model", ""),
            "size": metadata.get("size", ""),
            # 只返回是否有参考图（bool），不返回 base64 数据
            "has_reference_images": len(reference_images) > 0,
            "reference_images_count": len(reference_images),
            # 只返回是否有源图（bool），不返回 base64 数据
            "has_source_image": bool(source_image),
            "ai_params": metadata.get("ai_params", {}),
        }
    
    # 详情需要的额外字段
    if include_metadata:
        result.update({
            "description": metadata.get("description", ""),
            "file_path": asset.file_path,
            "file_size": asset.file_size,
            "mime_type": asset.mime_type,
            "duration": asset.duration,
            "width": asset.width,
            "height": asset.height,
            "source_url": asset.source_url,
            "cover_url": asset.cover_url,
            "metadata": metadata,  # 完整 metadata
        })
    
    return result


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
    source_type: Optional[str] = Query(None, description="来源类型：upload/parse/ai_generated/import"),
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
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    
    # 统一处理空字符串 -> None，并转大写匹配数据库
    assets, total = await service.list_assets(
        asset_type=asset_type.upper() if asset_type else None,
        platform=platform if platform else None,
        source_type=source_type if source_type else None,
        status=status.upper() if status else None,
        search=search,
        tags=tag_list,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    return AssetListResponse(
        success=True,
        data=[_asset_to_dict(a, include_metadata=False) for a in assets],
        total=total,
        page=page,
        page_size=page_size,
    )


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

    if asset.status != "READY":
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


@router.get("/{asset_id}/stream", summary="播放资产视频文件")
async def stream_asset(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    if asset.status != "READY":
        raise HTTPException(status_code=400, detail=f"资产状态为 {asset.status}，无法播放")
    if (asset.type or "").lower() != "video":
        raise HTTPException(status_code=400, detail="当前资产不是视频")
    if not asset.file_path or not os.path.exists(asset.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path=asset.file_path, media_type=asset.mime_type or "video/mp4")


def _get_course_episode_file(asset: Asset, episode_index: int) -> str:
    metadata = {}
    if asset.metadata_json:
        try:
            metadata = json.loads(asset.metadata_json)
        except Exception:
            metadata = {}

    episodes = metadata.get("episodes") or []
    episode = next((item for item in episodes if item.get("index") == episode_index), None)
    if not episode and 0 <= episode_index - 1 < len(episodes):
        episode = episodes[episode_index - 1]
    if not episode:
        raise HTTPException(status_code=404, detail="章节不存在")

    file_path = episode.get("file_path") or ""
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="章节文件不存在")

    return file_path


def _asset_metadata(asset: Asset) -> dict:
    if not asset.metadata_json:
        return {}
    try:
        return json.loads(asset.metadata_json)
    except Exception:
        return {}


def _get_course_episode(asset: Asset, episode_index: int) -> dict:
    metadata = _asset_metadata(asset)
    episodes = metadata.get("episodes") or []
    episode = next((item for item in episodes if item.get("index") == episode_index), None)
    if not episode and 0 <= episode_index - 1 < len(episodes):
        episode = episodes[episode_index - 1]
    if not episode:
        raise HTTPException(status_code=404, detail="章节不存在")
    return episode


def _sidecar_path_from_meta(meta: dict, kind: str, subtitle_index: int = 0) -> str:
    if kind == "subtitle":
        paths = meta.get("subtitle_paths") or []
        if not isinstance(paths, list) or not (0 <= subtitle_index < len(paths)):
            raise HTTPException(status_code=404, detail="字幕不存在")
        path = paths[subtitle_index]
    elif kind == "danmaku":
        path = meta.get("danmaku_path") or ""
    else:
        path = ""

    if not isinstance(path, str) or not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="sidecar 文件不存在")
    return path


def _subtitle_to_vtt(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8-sig", errors="ignore")
    if text.lstrip().startswith("WEBVTT"):
        return text
    lines = []
    for line in text.splitlines():
        if "-->" in line:
            line = line.replace(",", ".")
        lines.append(line)
    return "WEBVTT\n\n" + "\n".join(lines) + "\n"


@router.get("/{asset_id}/sidecars/subtitles/{subtitle_index}.vtt", summary="读取资产字幕")
async def get_asset_subtitle(
    asset_id: str,
    subtitle_index: int,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    path = _sidecar_path_from_meta(_asset_metadata(asset), "subtitle", subtitle_index)
    return Response(content=_subtitle_to_vtt(path), media_type="text/vtt; charset=utf-8")


@router.get("/{asset_id}/sidecars/danmaku", summary="读取资产弹幕")
async def get_asset_danmaku(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    path = _sidecar_path_from_meta(_asset_metadata(asset), "danmaku")
    return Response(content=Path(path).read_text(encoding="utf-8", errors="ignore"), media_type="application/json; charset=utf-8")


@router.get("/{asset_id}/course-episodes/{episode_index}/sidecars/subtitles/{subtitle_index}.vtt", summary="读取课程章节字幕")
async def get_course_episode_subtitle(
    asset_id: str,
    episode_index: int,
    subtitle_index: int,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    episode = _get_course_episode(asset, episode_index)
    path = _sidecar_path_from_meta(episode, "subtitle", subtitle_index)
    return Response(content=_subtitle_to_vtt(path), media_type="text/vtt; charset=utf-8")


@router.get("/{asset_id}/course-episodes/{episode_index}/sidecars/danmaku", summary="读取课程章节弹幕")
async def get_course_episode_danmaku(
    asset_id: str,
    episode_index: int,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    episode = _get_course_episode(asset, episode_index)
    path = _sidecar_path_from_meta(episode, "danmaku")
    return Response(content=Path(path).read_text(encoding="utf-8", errors="ignore"), media_type="application/json; charset=utf-8")


@router.get("/{asset_id}/course-episodes/{episode_index}/download", summary="下载课程章节文件")
async def download_course_episode_asset(
    asset_id: str,
    episode_index: int,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    file_path = _get_course_episode_file(asset, episode_index)

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=os.path.basename(file_path),
    )


@router.get("/{asset_id}/course-episodes/{episode_index}/stream", summary="播放课程章节文件")
async def stream_course_episode_asset(
    asset_id: str,
    episode_index: int,
    service: AssetService = Depends(get_asset_service),
):
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    file_path = _get_course_episode_file(asset, episode_index)
    return FileResponse(path=file_path, media_type="video/mp4")


# ---------------------------------------------------------------------------
# 标签管理（必须在泛型路由之前）
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

async def _fetch_image(image_source: str, platform: str = "") -> Response:
    """
    通用图片获取逻辑，支持本地文件和远程 URL。
    处理 base64 数据、文件路径（Windows/Linux）和远程 URL。
    """
    import base64
    
    # base64 数据
    if image_source.startswith("data:"):
        header, data = image_source.split(",", 1)
        mime_type = header.split(";")[0].replace("data:", "") or "image/png"
        try:
            binary_data = base64.b64decode(data)
            return Response(content=binary_data, media_type=mime_type, headers={"Cache-Control": "public, max-age=86400"})
        except Exception:
            pass
    
    # 检查是否是本地文件（支持 Windows 和 Linux 路径）
    # Windows: F:\path\to\file.png, C:/path/to/file.png
    # Linux: /path/to/file.png
    is_local_path = False
    if os.path.exists(image_source) and os.path.isfile(image_source):
        is_local_path = True
    elif len(image_source) > 1 and (
        (image_source[1] == ":" and image_source[0].isalpha()) or  # Windows: F:\...
        image_source.startswith("/")  # Unix: /...
    ):
        # 尝试扩展路径（处理相对路径情况）
        expanded_path = os.path.expanduser(os.path.expandvars(image_source))
        if os.path.exists(expanded_path) and os.path.isfile(expanded_path):
            image_source = expanded_path
            is_local_path = True
    
    if is_local_path:
        thumb_path = Path(image_source)
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
        media_type = mime_map.get(thumb_path.suffix.lower(), "image/png")
        return FileResponse(thumb_path, media_type=media_type)
    
    # 远程 URL（必须包含协议）
    if image_source.startswith("http://") or image_source.startswith("https://"):
        from app.api.v1.proxy import fetch_remote_image_response
        return await fetch_remote_image_response(image_source, fallback_label="NO IMAGE")
    
    logger.warning(f"不支持的图片来源，返回占位图: {image_source[:100]}")
    from app.api.v1.proxy import placeholder_image_response
    return placeholder_image_response("NO IMAGE")


@router.get("/{asset_id}/thumbnail", summary="代理加载封面图")
async def proxy_thumbnail(
    asset_id: str,
    original: bool = Query(False, description="是否返回原始参考图（而非生成的图）"),
    service: AssetService = Depends(get_asset_service),
):
    """
    通过后端代理加载图片，解决跨域/防盗链问题。
    - 默认返回生成的图（cover_url）
    - original=true 返回原始参考图（用于再次生成时的参考）
    支持本地文件路径、远程 URL 和 base64 数据。
    """
    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    
    # 解析 metadata
    metadata = {}
    if asset.metadata_json:
        try:
            metadata = json.loads(asset.metadata_json)
        except Exception:
            pass
    
    # 如果请求原始参考图
    if original:
        source_image = metadata.get("source_image")
        if source_image:
            return await _fetch_image(source_image, asset.platform or "")
        
        reference_images = metadata.get("reference_images", [])
        if reference_images and len(reference_images) > 0:
            return await _fetch_image(reference_images[0], asset.platform or "")
    
    # 默认返回生成的封面图
    if asset.cover_url:
        return await _fetch_image(asset.cover_url, asset.platform or "")
    
    from app.api.v1.proxy import placeholder_image_response
    return placeholder_image_response("NO IMAGE")


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
    return AssetResponse(success=True, data=_asset_to_dict(asset, include_metadata=True))


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
    mode: str = Field("soft", description="删除模式：soft=软删除 / del_file=删文件+软删记录 / hard=永久删除")
    restore: bool = Field(False, description="恢复已软删除的资产")


@router.delete("/{asset_id}", summary="删除资产")
async def delete_asset(
    asset_id: str,
    mode: str = Query("soft", description="soft / del_file / hard"),
    service: AssetService = Depends(get_asset_service),
):
    ok = await service.delete(asset_id, mode=mode)
    if not ok:
        raise HTTPException(status_code=404, detail="资产不存在")
    return {"success": True, "message": f"已{mode}删除"}


@router.post("/{asset_id}/restore", summary="恢复软删除的资产")
async def restore_asset(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    ok = await service.restore(asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="资产不存在或未处于软删除状态")
    return {"success": True, "message": "已恢复"}
