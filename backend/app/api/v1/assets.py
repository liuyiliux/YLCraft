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
import mimetypes
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse, FileResponse, Response
from pydantic import BaseModel, Field

from app.db.database import get_async_session
from app.db.models.asset import Asset, AssetTag
from app.db.models.asset_hub import AssetNode, AssetType
from app.services.asset.document_metadata import extract_document_cover_source, is_readable_document_asset
from app.services.asset.service import AssetService
from app.services.asset_hub.node_service import AssetNodeService
from app.services.asset_hub.representation_service import AssetRepresentationService
from app.services.asset_hub.version_service import AssetVersionService

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
    
    readable_document = is_readable_document_asset(asset.type, asset.file_path)
    title = asset.title
    if readable_document and asset.file_path:
        file_name = Path(asset.file_path).name
        if title == file_name:
            title = Path(asset.file_path).stem

    # 基础字段（列表和详情都需要）
    result = {
        "id": asset.id,
        "type": asset.type,
        "title": title,
        "platform": asset.platform,
        "author": asset.author,
        "status": asset.status,
        "source_type": asset.source_type,
        "source_url": asset.source_url,
        "tags": json.loads(asset.tags) if asset.tags else [],
        "created_at": _format_datetime(asset.created_at),
        "updated_at": _format_datetime(asset.updated_at),
        "downloaded_at": _format_datetime(asset.updated_at) if asset.status == "READY" else None,
        "thumbnail_url": f"/api/v1/assets/{asset.id}/thumbnail" if (asset.cover_url or readable_document) else None,
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


def _format_asset_datetime(dt) -> Optional[str]:
    if not dt:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _hub_file_url(path_or_url: str) -> str:
    if not path_or_url:
        return ""
    if path_or_url.startswith(("/api/", "http://", "https://", "data:")):
        return path_or_url
    return f"/api/v1/assets/download?path={quote(path_or_url)}"


def _resolution_label(width: Optional[int], height: Optional[int]) -> Optional[str]:
    if not width or not height:
        return None
    if height >= 2160:
        label = "4K"
    elif height >= 1440:
        label = "2K"
    elif height >= 1080:
        label = "1080P"
    elif height >= 720:
        label = "720P"
    elif height >= 480:
        label = "480P"
    else:
        label = ""
    return f"{width}x{height} ({label})" if label else f"{width}x{height}"


def _dict_value(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _list_value(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _legacy_asset_hub_node_id(asset: Asset | None) -> str:
    if not asset:
        return ""
    metadata = _dict_value(asset.metadata_json)
    return str(metadata.get("asset_hub_node_id") or "")


def _asset_type_value(asset_type) -> str:
    if hasattr(asset_type, "value"):
        return str(asset_type.value)
    value = str(asset_type or "")
    if "." in value:
        value = value.rsplit(".", 1)[-1]
    return value.lower()


def _type_from_representation(node: AssetNode, mime_type: str) -> str:
    node_type = _asset_type_value(node.asset_type)
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("text/") or mime_type in {"application/json", "application/epub+zip"}:
        return "text"
    return node_type


async def _asset_hub_card(
    service: AssetService,
    node: AssetNode,
    include_metadata: bool = False,
) -> Optional[dict]:
    version_service = AssetVersionService(service.session)
    rep_service = AssetRepresentationService(service.session)
    version = await version_service.get_latest_version(str(node.id))
    if not version:
        return None
    rep = await rep_service.get_primary(str(version.id))
    if not rep:
        return None

    params = _dict_value(version.params_json)
    lineage = _dict_value(version.lineage_json)
    node_meta = _dict_value(node.metadata_json)
    if node_meta.get("deleted_at") or str(node_meta.get("status", "")).upper() == "DELETED":
        return None

    file_url = _hub_file_url(rep.file_path)
    source = node_meta.get("source") or lineage.get("source") or params.get("source") or "asset_hub"
    source_type = node_meta.get("source_type")
    if not source_type:
        source_type = "ai_generated" if source in {"image_generation", "character_portrait"} else source
    provider = (
        params.get("provider")
        or node_meta.get("provider")
        or node_meta.get("platform")
        or source
        or "asset-hub"
    )
    model = version.model_used or params.get("model") or ""
    title = node.name or (version.prompt_used or Path(rep.file_path).stem or "Asset Hub Asset")[:80]
    tags = _list_value(node.tags_json)
    if _asset_type_value(node.asset_type) == AssetType.CHARACTER.value and "character_portrait" not in tags:
        tags.append("character_portrait")
    if provider and provider not in tags:
        tags.append(str(provider))
    if model and model not in tags:
        tags.append(str(model))

    metadata = {
        "prompt": version.prompt_used or "",
        "negative_prompt": params.get("negative_prompt", ""),
        "model": model,
        "size": params.get("size", ""),
        "provider": provider,
        "asset_hub": True,
        "node_id": str(node.id),
        "version_id": str(version.id),
        "version_number": version.version_number,
        "lineage": lineage,
        "node_metadata": node_meta,
        "has_reference_images": False,
        "reference_images_count": 0,
        "has_source_image": False,
        "ai_params": params,
    }

    mime_type = rep.mime_type or mimetypes.guess_type(rep.file_path)[0] or "application/octet-stream"
    asset_type = _type_from_representation(node, mime_type)
    thumbnail_source = node.thumbnail_url or (rep.file_path if mime_type.startswith("image/") else "")
    thumbnail_url = _hub_file_url(thumbnail_source) if thumbnail_source else None
    status = str(node_meta.get("status") or "READY").upper()

    data = {
        "id": str(node.id),
        "type": asset_type,
        "title": title,
        "platform": provider,
        "author": node_meta.get("author") or (f"AI ({model})" if model else "Asset Hub"),
        "status": status,
        "source_type": source_type,
        "source_url": node_meta.get("source_url") or lineage.get("source_url") or file_url,
        "cover_url": thumbnail_url or "",
        "thumbnail_url": thumbnail_url,
        "tags": tags,
        "created_at": _format_asset_datetime(version.created_at or node.created_at),
        "updated_at": _format_asset_datetime(node.updated_at or version.created_at),
        "downloaded_at": _format_asset_datetime(version.created_at or node.created_at),
        "duration": rep.duration or 0,
        "width": rep.width or 0,
        "height": rep.height or 0,
        "file_size": rep.file_size or 0,
        "resolution": _resolution_label(rep.width, rep.height),
        "metadata": metadata,
        "_sort_created_at": version.created_at or node.created_at,
    }
    if include_metadata:
        data.update({
            "description": node_meta.get("description", ""),
            "file_path": rep.file_path,
            "mime_type": mime_type,
            "metadata": metadata,
        })
    return data


async def _list_asset_hub_cards(
    service: AssetService,
    asset_type: Optional[str] = None,
    platform: Optional[str] = None,
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> list[dict]:
    normalized_type = (asset_type or "").lower()
    type_map = {item.value: item for item in AssetType}
    if normalized_type and normalized_type not in type_map:
        return []

    node_service = AssetNodeService(service.session)
    node_types = [type_map[normalized_type]] if normalized_type else list(AssetType)

    nodes = []
    for node_type in node_types:
        type_nodes, _ = await node_service.list_nodes(
            asset_type=node_type,
            keyword=search,
            page=1,
            page_size=1000,
        )
        nodes.extend(type_nodes)

    cards: list[dict] = []
    tag_filters = [tag for tag in (tags or []) if tag]
    for node in nodes:
        card = await _asset_hub_card(service, node)
        if not card:
            continue
        if status and str(card.get("status") or "").upper() != status.upper():
            continue
        if source_type and card.get("source_type") != source_type:
            continue
        if platform and card.get("platform") != platform:
            continue
        if tag_filters and not all(tag in (card.get("tags") or []) for tag in tag_filters):
            continue
        cards.append(card)
    return cards


async def _get_asset_hub_card(
    service: AssetService,
    asset_id: str,
    include_metadata: bool = True,
) -> Optional[dict]:
    session = getattr(service, "session", None)
    if session is None or not hasattr(session, "get"):
        return None

    node = await session.get(AssetNode, asset_id)
    if not node:
        return None
    card = await _asset_hub_card(service, node, include_metadata=include_metadata)
    if card:
        card.pop("_sort_created_at", None)
    return card


async def _get_asset_hub_primary(
    service: AssetService,
    asset_id: str,
) -> Optional[tuple[AssetNode, object, object]]:
    session = getattr(service, "session", None)
    if session is None or not hasattr(session, "get"):
        return None

    node = await session.get(AssetNode, asset_id)
    if not node:
        return None
    node_meta = _dict_value(node.metadata_json)
    if node_meta.get("deleted_at") or str(node_meta.get("status", "")).upper() == "DELETED":
        return None

    version = await AssetVersionService(session).get_latest_version(str(node.id))
    if not version:
        return None
    rep = await AssetRepresentationService(session).get_primary(str(version.id))
    if not rep:
        return None
    return node, version, rep


def _asset_hub_file_response(rep, *, inline: bool = False) -> FileResponse:
    path = _resolve_asset_file_path(rep.file_path)
    media_type = rep.mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {"Cache-Control": "public, max-age=86400"} if inline else None
    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=None if inline else path.name,
        headers=headers,
    )


async def _soft_delete_asset_hub_node(
    service: AssetService,
    asset_id: str,
    mode: str,
) -> bool:
    primary = await _get_asset_hub_primary(service, asset_id)
    if not primary:
        return False
    node, _version, rep = primary

    if mode in {"del_file", "hard"} and rep.file_path:
        try:
            path = _resolve_asset_file_path(rep.file_path)
            if path.exists():
                path.unlink()
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("[assets] failed to delete Asset Hub file %s: %s", rep.file_path, exc)

    node_meta = _dict_value(node.metadata_json)
    node_meta["status"] = "DELETED"
    node_meta["deleted_at"] = datetime.now().isoformat()
    node_meta["delete_mode"] = mode
    node.metadata_json = node_meta
    node.updated_at = datetime.utcnow() if hasattr(datetime, "utcnow") else datetime.now()
    service.session.add(node)

    legacy_asset_id = str(node_meta.get("legacy_asset_id") or "")
    if legacy_asset_id:
        legacy_asset = await service.get_by_id(legacy_asset_id)
        if legacy_asset:
            legacy_asset.status = "DELETED"
            legacy_asset.deleted_at = datetime.now()
            legacy_asset.updated_at = datetime.now()
            service.session.add(legacy_asset)

    await service.session.commit()
    return True


async def _restore_asset_hub_node(service: AssetService, asset_id: str) -> bool:
    node = await service.session.get(AssetNode, asset_id)
    if not node:
        return False
    node_meta = _dict_value(node.metadata_json)
    if not (node_meta.get("deleted_at") or str(node_meta.get("status", "")).upper() == "DELETED"):
        return False

    node_meta.pop("deleted_at", None)
    node_meta.pop("delete_mode", None)
    node_meta["status"] = "READY"
    node.metadata_json = node_meta
    node.updated_at = datetime.utcnow()
    service.session.add(node)

    legacy_asset_id = str(node_meta.get("legacy_asset_id") or "")
    if legacy_asset_id:
        legacy_asset = await service.get_by_id(legacy_asset_id)
        if legacy_asset and legacy_asset.status == "DELETED":
            legacy_asset.status = "READY"
            legacy_asset.deleted_at = None
            legacy_asset.updated_at = datetime.now()
            service.session.add(legacy_asset)

    await service.session.commit()
    return True


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
    assets, _old_total = await service.list_assets(
        asset_type=asset_type.upper() if asset_type else None,
        platform=platform if platform else None,
        source_type=source_type if source_type else None,
        status=status.upper() if status else None,
        search=search,
        tags=tag_list,
        sort_by=sort_by,
        sort_order=sort_order,
        page=1,
        page_size=1000,
    )
    old_cards = [_asset_to_dict(a, include_metadata=False) for a in assets]
    try:
        hub_cards = await _list_asset_hub_cards(
            service,
            asset_type=asset_type,
            platform=platform if platform else None,
            source_type=source_type if source_type else None,
            status=status.upper() if status else None,
            search=search,
            tags=tag_list,
        )
    except Exception as exc:
        logger.warning("[assets] asset_hub merge failed: %s", exc, exc_info=True)
        hub_cards = []

    migrated_legacy_ids = {
        str((card.get("metadata") or {}).get("node_metadata", {}).get("legacy_asset_id"))
        for card in hub_cards
        if (card.get("metadata") or {}).get("node_metadata", {}).get("legacy_asset_id")
    }
    if migrated_legacy_ids:
        old_cards = [card for card in old_cards if str(card.get("id")) not in migrated_legacy_ids]

    merged = [*hub_cards, *old_cards]
    reverse = sort_order != "asc"
    if sort_by in {"created_at", "updated_at", "downloaded_at"}:
        def sort_datetime_value(item: dict) -> str:
            value = item.get("_sort_created_at") or item.get(sort_by) or ""
            if isinstance(value, datetime):
                return value.isoformat()
            return str(value)

        merged.sort(key=sort_datetime_value, reverse=reverse)
    elif sort_by in {"file_size", "duration", "width", "height"}:
        merged.sort(key=lambda item: item.get(sort_by) or 0, reverse=reverse)
    else:
        merged.sort(key=lambda item: str(item.get(sort_by) or ""), reverse=reverse)

    total = len(merged)
    offset = (page - 1) * page_size
    page_items = merged[offset: offset + page_size]
    for item in page_items:
        item.pop("_sort_created_at", None)

    return AssetListResponse(
        success=True,
        data=page_items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# 下载资产文件 GET /api/v1/assets/:id/download
# ---------------------------------------------------------------------------

def _asset_file_allowed_roots() -> list[Path]:
    from app.core.config import ensure_download_path

    backend_dir = Path(__file__).resolve().parents[3]
    project_dir = backend_dir.parent
    roots = [
        backend_dir / "app" / "storage",
        backend_dir / "storage",
        backend_dir / "downloads",
        backend_dir / "uploads",
        project_dir / "storage",
        project_dir / "downloads",
        project_dir / "uploads",
        ensure_download_path(),
    ]
    return [root.resolve() for root in roots if root]


def _is_allowed_temp_asset_path(path: Path) -> bool:
    temp_root = Path(tempfile.gettempdir()).resolve()
    allowed_prefixes = ("ylcraft_uploads", "narrato_out_", "moe_out_", "cutclaw_out_")
    for parent in (path, *path.parents):
        if parent.parent == temp_root and parent.name.startswith(allowed_prefixes):
            return True
    return False


def _resolve_asset_file_path(path_value: str) -> Path:
    if not path_value or path_value.startswith(("http://", "https://", "data:")):
        raise HTTPException(status_code=400, detail="不支持的本地文件路径")

    path = Path(os.path.expandvars(os.path.expanduser(path_value))).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    allowed = False
    for root in _asset_file_allowed_roots():
        if path == root or root in path.parents:
            allowed = True
            break
    if not allowed and _is_allowed_temp_asset_path(path):
        allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="文件不在允许访问的目录内")
    return path


@router.get("/download", summary="下载/预览本地文件")
@router.get("/file", summary="预览本地文件")
async def download_local_asset_file(
    request: Request,
    path: str = Query(..., description="本地文件路径"),
    inline: bool = Query(True, description="是否直接预览"),
):
    file_path = _resolve_asset_file_path(path)
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    if inline and media_type.startswith("video/"):
        return _range_file_response(request, str(file_path), media_type)

    headers = {"Cache-Control": "public, max-age=86400"} if inline else None
    if inline:
        return FileResponse(path=str(file_path), media_type=media_type, headers=headers)
    return FileResponse(path=str(file_path), media_type=media_type, filename=file_path.name)


@router.get("/{asset_id}/download", summary="下载资产文件")
async def download_asset(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    """
    返回资产文件（流式响应，不阻塞）。
    资产必须处于 READY 状态。
    """
    hub_primary = await _get_asset_hub_primary(service, asset_id)
    if hub_primary:
        _node, _version, rep = hub_primary
        return _asset_hub_file_response(rep)

    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    legacy_hub_id = _legacy_asset_hub_node_id(asset)
    if legacy_hub_id:
        hub_primary = await _get_asset_hub_primary(service, legacy_hub_id)
        if hub_primary:
            _node, _version, rep = hub_primary
            return _asset_hub_file_response(rep)

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
    request: Request,
    service: AssetService = Depends(get_asset_service),
):
    hub_primary = await _get_asset_hub_primary(service, asset_id)
    if hub_primary:
        node, _version, rep = hub_primary
        media_type = rep.mime_type or mimetypes.guess_type(rep.file_path)[0] or "application/octet-stream"
        if _type_from_representation(node, media_type) != "video":
            raise HTTPException(status_code=400, detail="当前资产不是视频")
        path = _resolve_asset_file_path(rep.file_path)
        return _range_file_response(request, str(path), media_type)

    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    legacy_hub_id = _legacy_asset_hub_node_id(asset)
    if legacy_hub_id:
        hub_primary = await _get_asset_hub_primary(service, legacy_hub_id)
        if hub_primary:
            node, _version, rep = hub_primary
            media_type = rep.mime_type or mimetypes.guess_type(rep.file_path)[0] or "application/octet-stream"
            if _type_from_representation(node, media_type) != "video":
                raise HTTPException(status_code=400, detail="当前资产不是视频")
            path = _resolve_asset_file_path(rep.file_path)
            return _range_file_response(request, str(path), media_type)

    if asset.status != "READY":
        raise HTTPException(status_code=400, detail=f"资产状态为 {asset.status}，无法播放")
    if (asset.type or "").lower() != "video":
        raise HTTPException(status_code=400, detail="当前资产不是视频")
    if not asset.file_path or not os.path.exists(asset.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return _range_file_response(request, asset.file_path, asset.mime_type or "video/mp4")


def _range_file_response(request: Request, file_path: str, media_type: str) -> Response:
    path = Path(file_path)
    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path=file_path,
            media_type=media_type,
            headers={"Accept-Ranges": "bytes"},
        )

    try:
        units, value = range_header.split("=", 1)
        if units.strip().lower() != "bytes":
            raise ValueError("unsupported range unit")
        start_s, end_s = value.split("-", 1)
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
        end = min(end, file_size - 1)
        if start < 0 or end < start or start >= file_size:
            raise ValueError("invalid range")
    except Exception:
        return Response(
            status_code=416,
            headers={
                "Content-Range": f"bytes */{file_size}",
                "Accept-Ranges": "bytes",
            },
        )

    chunk_size = end - start + 1

    async def iter_file():
        with path.open("rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_file(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
        },
    )


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
    hub_primary = await _get_asset_hub_primary(service, asset_id)
    if hub_primary:
        node, _version, rep = hub_primary
        source = node.thumbnail_url or (rep.file_path if (rep.mime_type or "").startswith("image/") else "")
        if source:
            return await _fetch_image(source, "")

    asset = await service.get_by_id(asset_id)
    if not asset:
        hub_asset = await _get_asset_hub_card(service, asset_id, include_metadata=True)
        if hub_asset and hub_asset.get("source_url"):
            return await _fetch_image(hub_asset["source_url"], hub_asset.get("platform") or "")
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    legacy_hub_id = _legacy_asset_hub_node_id(asset)
    if legacy_hub_id:
        hub_primary = await _get_asset_hub_primary(service, legacy_hub_id)
        if hub_primary:
            node, _version, rep = hub_primary
            source = node.thumbnail_url or (rep.file_path if (rep.mime_type or "").startswith("image/") else "")
            if source:
                return await _fetch_image(source, "")
    
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

    if is_readable_document_asset(asset.type, asset.file_path):
        cover_source = extract_document_cover_source(asset.file_path)
        if cover_source:
            return await _fetch_image(cover_source, asset.platform or "")
    
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
    hub_asset = await _get_asset_hub_card(service, asset_id, include_metadata=True)
    if hub_asset:
        return AssetResponse(success=True, data=hub_asset)

    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    legacy_hub_id = _legacy_asset_hub_node_id(asset)
    if legacy_hub_id:
        hub_asset = await _get_asset_hub_card(service, legacy_hub_id, include_metadata=True)
        if hub_asset:
            return AssetResponse(success=True, data=hub_asset)
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
    node = await service.session.get(AssetNode, asset_id)
    if node:
        node_meta = _dict_value(node.metadata_json)
        if node_meta.get("deleted_at") or str(node_meta.get("status", "")).upper() == "DELETED":
            raise HTTPException(status_code=404, detail="资产不存在")
        if req.title is not None:
            node.name = req.title
        if req.description is not None:
            node_meta["description"] = req.description
            node.metadata_json = node_meta
        if req.tags is not None:
            node.tags_json = req.tags
        node.updated_at = datetime.utcnow()
        service.session.add(node)
        await service.session.commit()
        await service.session.refresh(node)
        hub_asset = await _get_asset_hub_card(service, asset_id, include_metadata=True)
        if hub_asset:
            return AssetResponse(success=True, data=hub_asset)

    asset = await service.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    legacy_hub_id = _legacy_asset_hub_node_id(asset)
    if legacy_hub_id:
        node = await service.session.get(AssetNode, legacy_hub_id)
        if node:
            if req.title is not None:
                node.name = req.title
            node_meta = _dict_value(node.metadata_json)
            if req.description is not None:
                node_meta["description"] = req.description
                node.metadata_json = node_meta
            if req.tags is not None:
                node.tags_json = req.tags
            node.updated_at = datetime.utcnow()
            service.session.add(node)
            await service.session.commit()
            await service.session.refresh(node)
            hub_asset = await _get_asset_hub_card(service, legacy_hub_id, include_metadata=True)
            if hub_asset:
                return AssetResponse(success=True, data=hub_asset)

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
    if mode not in {"soft", "del_file", "hard"}:
        raise HTTPException(status_code=400, detail="不支持的删除模式")

    hub_deleted = await _soft_delete_asset_hub_node(service, asset_id, mode=mode)
    if hub_deleted:
        return {"success": True, "message": f"已{mode}删除"}

    asset = await service.get_by_id(asset_id)
    legacy_hub_id = _legacy_asset_hub_node_id(asset)
    if legacy_hub_id:
        hub_deleted = await _soft_delete_asset_hub_node(service, legacy_hub_id, mode=mode)
        if hub_deleted:
            return {"success": True, "message": f"已{mode}删除"}

    ok = await service.delete(asset_id, mode=mode)
    if not ok:
        raise HTTPException(status_code=404, detail="资产不存在")
    return {"success": True, "message": f"已{mode}删除"}


@router.post("/{asset_id}/restore", summary="恢复软删除的资产")
async def restore_asset(
    asset_id: str,
    service: AssetService = Depends(get_asset_service),
):
    hub_restored = await _restore_asset_hub_node(service, asset_id)
    if hub_restored:
        return {"success": True, "message": "已恢复"}

    asset = await service.get_by_id(asset_id)
    legacy_hub_id = _legacy_asset_hub_node_id(asset)
    if legacy_hub_id:
        hub_restored = await _restore_asset_hub_node(service, legacy_hub_id)
        if hub_restored:
            return {"success": True, "message": "已恢复"}

    ok = await service.restore(asset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="资产不存在或未处于软删除状态")
    return {"success": True, "message": "已恢复"}
