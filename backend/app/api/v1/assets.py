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

import io
import json
import logging
import mimetypes
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.database import get_async_session
from app.db.models.asset_hub import AssetNode, AssetType, Tag
from app.core.ffmpeg import get_ffmpeg_service
from app.services.asset_hub import AssetHubFacade
from app.services.asset_hub.node_service import AssetNodeService
from app.services.asset_hub.representation_service import AssetRepresentationService
from app.services.asset_hub.version_service import AssetVersionService

router = APIRouter()
logger = logging.getLogger("ylcraft.assets")

TYPE_TAGS = {"类型", "角色", "角色立绘", "背景", "画风", "道具", "场景", "分镜", "漫画页"}
STYLE_TAGS = {"风格", "写实", "动漫", "国风", "赛博朋克", "水墨"}
SOURCE_TAGS = {"来源", "AI生成", "上传", "采集", "解析"}
STATUS_TAGS = {"状态", "草稿", "成品", "已弃用"}
VIRTUAL_TAGS = TYPE_TAGS | STYLE_TAGS | SOURCE_TAGS | STATUS_TAGS


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_asset_session():
    """获取资产中枢数据库会话"""
    async with get_async_session() as session:
        yield session


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


def _tag_to_dict(tag: Tag) -> dict:
    return {
        "id": str(tag.id),
        "name": tag.name,
        "color": tag.color or "#1890ff",
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


def _asset_type_value(asset_type) -> str:
    if hasattr(asset_type, "value"):
        return str(asset_type.value)
    value = str(asset_type or "")
    if "." in value:
        value = value.rsplit(".", 1)[-1]
    return value.lower()


def _text_blob(*values) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            try:
                parts.append(json.dumps(value, ensure_ascii=False))
            except Exception:
                parts.append(str(value))
        else:
            parts.append(str(value))
    return " ".join(parts).lower()


def _card_matches_virtual_tag(card: dict, tag: str) -> bool:
    tag = (tag or "").strip()
    tags = [str(item) for item in (card.get("tags") or [])]
    meta = card.get("metadata") or {}
    node_meta = meta.get("node_metadata") or {}
    ai_params = meta.get("ai_params") or {}
    lineage = meta.get("lineage") or {}
    asset_type = str(card.get("type") or "").lower()
    source_type = str(card.get("source_type") or "").lower()
    status = str(card.get("status") or "").lower()
    source = str(node_meta.get("source") or lineage.get("source") or ai_params.get("source") or "").lower()
    blob = _text_blob(card.get("title"), tags, meta.get("prompt"), ai_params.get("prompt"), node_meta, lineage)

    if tag == "角色":
        return asset_type == "character" or "character" in blob or "角色" in blob
    if tag == "角色立绘":
        return asset_type == "character" or source_type == "character_portrait" or "character_portrait" in tags or "立绘" in blob
    if tag == "背景":
        return "背景" in blob or "background" in blob
    if tag == "画风":
        return any(word in blob for word in ("画风", "风格", "style"))
    if tag == "道具":
        return any(word in blob for word in ("道具", "prop", "props"))
    if tag == "场景":
        return any(word in blob for word in ("场景", "scene"))
    if tag == "分镜":
        return any(word in blob for word in ("分镜", "storyboard"))
    if tag == "漫画页":
        return any(word in blob for word in ("漫画页", "comic page", "comic_panel", "comic-panel"))
    if tag == "类型":
        return any(_card_matches_virtual_tag(card, child) for child in TYPE_TAGS - {"类型"})

    if tag == "写实":
        return any(word in blob for word in ("写实", "真实", "realistic", "photo", "photoreal"))
    if tag == "动漫":
        return any(word in blob for word in ("动漫", "漫画", "anime", "manga", "二次元"))
    if tag == "国风":
        return any(word in blob for word in ("国风", "古风", "中式", "chinese style", "wuxia"))
    if tag == "赛博朋克":
        return any(word in blob for word in ("赛博朋克", "cyberpunk"))
    if tag == "水墨":
        return any(word in blob for word in ("水墨", "ink wash", "ink painting"))
    if tag == "风格":
        return any(_card_matches_virtual_tag(card, child) for child in STYLE_TAGS - {"风格"})

    if tag == "AI生成":
        return source_type in {"ai_generated", "image_generation", "character_portrait"} or source in {"image_generation", "character_portrait"} or "ai生成" in blob
    if tag == "上传":
        return source_type in {"upload", "import", "imported_file"}
    if tag == "采集":
        return source_type in {"download", "torrent", "novel_download", "wechat_mp", "parse"} or source in {"download", "torrent", "crawler"}
    if tag == "解析":
        return source_type in {"parse", "download", "torrent"} or source in {"parse", "download", "torrent"}
    if tag == "来源":
        return any(_card_matches_virtual_tag(card, child) for child in SOURCE_TAGS - {"来源"})

    if tag == "草稿":
        return status in {"draft", "pending", "parsed", "processing"}
    if tag == "成品":
        return status in {"ready", "completed", "done", "bookshelf"}
    if tag == "已弃用":
        return status in {"deprecated", "discarded", "deleted", "archived"}
    if tag == "状态":
        return any(_card_matches_virtual_tag(card, child) for child in STATUS_TAGS - {"状态"})

    return False


def _card_matches_tag_filter(card: dict, tag: str) -> bool:
    if tag in VIRTUAL_TAGS:
        return _card_matches_virtual_tag(card, tag)
    return tag in (card.get("tags") or [])


def _is_novel_asset_hub(node_meta: dict, lineage: dict, params: dict) -> bool:
    source_type = str(node_meta.get("source_type") or lineage.get("source_type") or params.get("source_type") or "").lower()
    source = str(node_meta.get("source") or lineage.get("source") or params.get("source") or "").lower()
    if source_type not in {"novel", "novel_bookshelf", "novel_download"} and source not in {"novel_bookshelf", "novel_download"}:
        return False
    return any(
        key in node_meta
        for key in ("book_url", "chapters", "chapter_count", "catalogs", "novel_title")
    )


def _type_from_representation(node: AssetNode, mime_type: str, *, node_meta: dict, lineage: dict, params: dict) -> str:
    node_type = _asset_type_value(node.asset_type)
    if _is_novel_asset_hub(node_meta, lineage, params):
        return "novel"
    if node_type == AssetType.COLLECTION.value:
        return "collection"
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("text/") or mime_type in {"application/json", "application/epub+zip"}:
        return "text"
    return node_type


def _project_asset_context(card: dict) -> dict:
    """Read project provenance from the three Asset Hub metadata layers.

    Older project image paths placed fields in lineage or AI parameters while
    text projections place them on the node.  The list endpoint needs one
    stable view without forcing each producer to duplicate metadata.
    """
    metadata = _dict_value(card.get("metadata"))
    node_meta = _dict_value(metadata.get("node_metadata"))
    lineage = _dict_value(metadata.get("lineage"))
    params = _dict_value(metadata.get("ai_params"))

    def value(*keys: str):
        for source in (node_meta, lineage, params):
            for key in keys:
                candidate = source.get(key)
                if candidate not in (None, ""):
                    return candidate
        return ""

    project_id = str(value("project_id"))
    asset_role = str(value("asset_role", "role", "asset_kind"))
    if not asset_role and project_id:
        asset_role = "text" if str(card.get("type") or "").lower() == "text" else "output"

    return {
        "project_id": project_id,
        "project_title": value("project_title"),
        "asset_role": asset_role,
        "source_stage": str(value("source_stage", "stage", "content_type", "source_type")),
        "content_id": str(value("content_id", "project_content_id")),
        "content_version": value("content_version", "project_content_version"),
        "chapter_number": value("chapter_number", "episode_number"),
    }


async def _asset_hub_card(
    session,
    node: AssetNode,
    include_metadata: bool = False,
) -> Optional[dict]:
    version_service = AssetVersionService(session)
    rep_service = AssetRepresentationService(session)
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

    is_novel = _is_novel_asset_hub(node_meta, lineage, params)
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
    if is_novel:
        metadata.update(
            {
                "novel_title": node_meta.get("novel_title") or title,
                "author": node_meta.get("author") or "",
                "cover_url": node.thumbnail_url or node_meta.get("cover_url") or "",
                "book_url": node_meta.get("book_url") or node_meta.get("source_url") or "",
                "toc_url": node_meta.get("toc_url") or "",
                "source_id": node_meta.get("source_id") or "",
                "source_name": node_meta.get("source_name") or node_meta.get("source_site") or "",
                "source_url": node_meta.get("source_url") or "",
                "chapters": node_meta.get("chapters") or [],
                "chapter_count": node_meta.get("chapter_count") or 0,
                "catalogs": node_meta.get("catalogs") or {},
                "downloaded_chapter_indices": node_meta.get("downloaded_chapter_indices") or [],
                "last_read_chapter": node_meta.get("last_read_chapter") or 0,
                "last_read_position": node_meta.get("last_read_position") or 0,
                "content_path": node_meta.get("content_path") or "",
                "kind": node_meta.get("kind") or "",
                "intro": node_meta.get("intro") or "",
                "status": node_meta.get("status") or "bookshelf",
            }
        )
    if node_meta.get("type") == "paid_course":
        metadata.update(node_meta)

    mime_type = rep.mime_type or mimetypes.guess_type(rep.file_path)[0] or "application/octet-stream"
    asset_type = _type_from_representation(node, mime_type, node_meta=node_meta, lineage=lineage, params=params)
    thumbnail_source = node.thumbnail_url or (rep.file_path if mime_type.startswith("image/") else "")
    thumbnail_url = _hub_file_url(thumbnail_source) if thumbnail_source else None
    status_value = str(node_meta.get("status") or "READY")
    status = status_value if is_novel else status_value.upper()

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
    project_context = _project_asset_context(data)
    if project_context["project_id"]:
        metadata["project_context"] = project_context
    if include_metadata:
        model_files = _list_model_sidecar_files(rep.file_path, str(node.id)) if asset_type == "3d_model" else []
        data.update({
            "description": node_meta.get("description", ""),
            "file_path": rep.file_path,
            "mime_type": mime_type,
            "metadata": metadata,
        })
        if model_files:
            data["files"] = model_files
    return data


async def _list_asset_hub_cards(
    session,
    asset_type: Optional[str] = None,
    platform: Optional[str] = None,
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    tags: Optional[list[str]] = None,
    project_id: Optional[str] = None,
    asset_role: Optional[str] = None,
    source_stage: Optional[str] = None,
) -> list[dict]:
    normalized_type = (asset_type or "").lower()
    type_map = {item.value: item for item in AssetType}
    if normalized_type == "novel":
        node_types = [AssetType.TEXT]
    elif normalized_type and normalized_type not in type_map:
        return []
    else:
        node_types = [type_map[normalized_type]] if normalized_type else list(AssetType)

    node_service = AssetNodeService(session)

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
        card = await _asset_hub_card(session, node)
        if not card:
            continue
        if normalized_type == "novel" and card.get("type") != "novel":
            continue
        if status and str(card.get("status") or "").upper() != status.upper():
            continue
        if source_type and card.get("source_type") != source_type:
            continue
        if platform and card.get("platform") != platform:
            continue
        if tag_filters and not all(_card_matches_tag_filter(card, tag) for tag in tag_filters):
            continue
        project_context = _project_asset_context(card)
        if project_id and project_context["project_id"] != project_id:
            continue
        if asset_role and project_context["asset_role"].lower() != asset_role.lower():
            continue
        if source_stage and project_context["source_stage"].lower() != source_stage.lower():
            continue
        cards.append(card)
    return cards


async def _get_asset_hub_card(
    session,
    asset_id: str,
    include_metadata: bool = True,
) -> Optional[dict]:
    if session is None or not hasattr(session, "get"):
        return None

    node = await session.get(AssetNode, asset_id)
    if not node:
        return None
    card = await _asset_hub_card(session, node, include_metadata=include_metadata)
    if card:
        card.pop("_sort_created_at", None)
    return card


async def _get_asset_hub_primary(
    session,
    asset_id: str,
) -> Optional[tuple[AssetNode, object, object]]:
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
    session,
    asset_id: str,
    mode: str,
) -> bool:
    primary = await _get_asset_hub_primary(session, asset_id)
    if not primary:
        return False
    node, _version, rep = primary

    if mode in {"del_file", "hard"} and rep.file_path:
        _delete_asset_file_if_exists(rep.file_path)

    node_meta = dict(_dict_value(node.metadata_json))
    node_meta["status"] = "DELETED"
    node_meta["deleted_at"] = datetime.now().isoformat()
    node_meta["delete_mode"] = mode
    node.metadata_json = node_meta
    node.updated_at = datetime.utcnow() if hasattr(datetime, "utcnow") else datetime.now()
    session.add(node)

    await session.commit()
    return True


async def _restore_asset_hub_node(session, asset_id: str) -> bool:
    node = await session.get(AssetNode, asset_id)
    if not node:
        return False
    node_meta = dict(_dict_value(node.metadata_json))
    if not (node_meta.get("deleted_at") or str(node_meta.get("status", "")).upper() == "DELETED"):
        return False

    node_meta.pop("deleted_at", None)
    node_meta.pop("delete_mode", None)
    node_meta["status"] = "READY"
    node.metadata_json = node_meta
    node.updated_at = datetime.utcnow()
    session.add(node)

    await session.commit()
    return True


# ---------------------------------------------------------------------------
# 资产列表 GET /api/v1/assets
# ---------------------------------------------------------------------------

@router.get("", response_model=AssetListResponse, summary="素材资产列表")
async def list_assets(
    session = Depends(get_asset_session),
    asset_type: Optional[str] = Query(None, description="素材类型：video/image/audio/document"),
    platform: Optional[str] = Query(None, description="平台：douyin/kuaishou/bilibili/..."),
    source_type: Optional[str] = Query(None, description="来源类型：upload/parse/ai_generated/import"),
    project_id: Optional[str] = Query(None, description="创作项目 ID（可与其他筛选组合）"),
    asset_role: Optional[str] = Query(None, description="项目资产角色：text/character/background/reference/..."),
    source_stage: Optional[str] = Query(None, description="项目来源阶段：novel_body/script/storyboard/..."),
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
    
    try:
        hub_cards = await _list_asset_hub_cards(
            session,
            asset_type=asset_type,
            platform=platform if platform else None,
            source_type=source_type if source_type else None,
            status=status.upper() if status else None,
            search=search,
            tags=tag_list,
            project_id=project_id,
            asset_role=asset_role,
            source_stage=source_stage,
        )
    except Exception as exc:
        logger.warning("[assets] asset_hub merge failed: %s", exc, exc_info=True)
        hub_cards = []

    merged = [*hub_cards]
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


def _delete_asset_file_if_exists(path_value: str) -> None:
    """Delete an asset file when it still exists; never raise for a missing file."""
    if not path_value or path_value.startswith(("http://", "https://", "data:")):
        return
    path = Path(os.path.expandvars(os.path.expanduser(path_value))).resolve()
    if not path.is_file():
        return  # 文件已不存在，跳过

    allowed = False
    for root in _asset_file_allowed_roots():
        if path == root or root in path.parents:
            allowed = True
            break
    if not allowed and _is_allowed_temp_asset_path(path):
        allowed = True
    if not allowed:
        logger.warning("[assets] skip deleting file outside allowed roots: %s", path)
        return

    try:
        path.unlink()
    except OSError as exc:
        logger.warning("[assets] failed to delete Asset Hub file %s: %s", path, exc)


def _list_model_sidecar_files(file_path: str, asset_id: str) -> list[dict]:
    """List a multi-file 3D model directory (OBJ + MTL + textures) as URLs.

    OBJ 模型拆成 obj + mtl + 贴图，前端 MTLLoader 需要按相对路径取配套文件。
    单文件模型（GLB/GLTF）目录里通常只有一个文件，返回空列表即可。
    """
    path = Path(file_path).resolve()
    base = path.parent
    files: list[dict] = []
    try:
        for child in sorted(base.iterdir()):
            if child.is_file():
                files.append({
                    "name": child.name,
                    "url": f"/api/v1/assets/{asset_id}/files/{quote(child.name)}",
                })
    except OSError:
        return []
    return files if len(files) > 1 else []


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
    session = Depends(get_asset_session),
):
    """
    返回资产文件（流式响应，不阻塞）。
    资产必须处于 READY 状态。
    """
    hub_primary = await _get_asset_hub_primary(session, asset_id)
    if hub_primary:
        _node, _version, rep = hub_primary
        return _asset_hub_file_response(rep)

    raise HTTPException(status_code=404, detail="资产不存在")


@router.get("/{asset_id}/files/{filename:path}", summary="下载/预览资产的配套文件")
async def asset_sidecar_file(
    asset_id: str,
    filename: str,
    session = Depends(get_asset_session),
):
    """Serve a sibling file of a multi-file asset (OBJ 的 mtl/贴图等).

    OBJ 模型需要 obj + mtl + 贴图一起加载；该端点按文件名从主文件所在目录
    提供配套文件，供前端 MTLLoader 以相对路径解析。
    """
    hub_primary = await _get_asset_hub_primary(session, asset_id)
    if not hub_primary:
        raise HTTPException(status_code=404, detail="资产不存在")
    _node, _version, rep = hub_primary

    base = Path(rep.file_path).resolve().parent
    target = (base / filename).resolve()
    if target != base and base not in target.parents:
        raise HTTPException(status_code=403, detail="非法文件路径")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    path = _resolve_asset_file_path(str(target))
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(path=str(path), media_type=media_type, filename=target.name)


def _model3d_upload_dir() -> Path:
    directory = Path(__file__).resolve().parents[3] / "storage" / "model3d" / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def _import_uploaded_model(filename: str, content: bytes, title: str, session) -> dict:
    """解包/定位上传的 3D 模型文件并写入 Asset Hub。"""
    upload_dir = _model3d_upload_dir() / uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)

    lower_name = filename.lower()
    if lower_name.endswith(".zip") or content[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                archive.extractall(upload_dir)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="不是有效的 ZIP 文件")
    else:
        ext = Path(filename).suffix.lower()
        if ext not in {".obj", ".glb", ".gltf", ".fbx", ".usdz"}:
            raise HTTPException(status_code=400, detail="仅支持 OBJ/GLB/GLTF/FBX/USDZ 或包含这些文件的 ZIP")
        (upload_dir / filename).write_bytes(content)

    order = {".glb": 0, ".gltf": 1, ".obj": 2, ".fbx": 3, ".usdz": 4}
    candidates = [p for p in upload_dir.rglob("*") if p.is_file() and p.suffix.lower() in order]
    if not candidates:
        raise HTTPException(status_code=400, detail="压缩包内未找到 3D 模型文件（OBJ/GLB/GLTF/FBX/USDZ）")
    candidates.sort(key=lambda p: (order[p.suffix.lower()], -p.stat().st_size))
    model_path = candidates[0]

    created = await AssetHubFacade(session).create_imported_file(
        file_path=str(model_path),
        title=(title or model_path.stem or "上传的 3D 模型")[:120],
        asset_type=AssetType.THREE_D_MODEL,
        source="upload",
        source_url="",
        metadata={"original_filename": filename, "upload": True},
        tags=["upload", "3d_model"],
    )
    return {"success": True, "asset_id": created.node_id}


@router.post("/upload-model3d", summary="上传 3D 模型（ZIP 或单文件）入库")
async def upload_model3d(
    file: UploadFile = File(...),
    title: str = Form(""),
    session = Depends(get_asset_session),
):
    """上传 OBJ/GLB/GLTF 等 3D 模型包并写入 Asset Hub。

    支持 ZIP（内含 obj + mtl + 贴图）或单个模型文件。OBJ 的配套 mtl/贴图
    会作为同级文件保留，供前端 MTLLoader 按相对路径解析。
    """
    filename = file.filename or "model.zip"
    content = await file.read()
    return await _import_uploaded_model(filename, content, title, session)


def _upload_assets_dir() -> Path:
    directory = Path(__file__).resolve().parents[3] / "storage" / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


_UPLOAD_EXT_TO_TYPE: dict[str, AssetType] = {
    ".png": AssetType.IMAGE, ".jpg": AssetType.IMAGE, ".jpeg": AssetType.IMAGE,
    ".webp": AssetType.IMAGE, ".gif": AssetType.IMAGE, ".bmp": AssetType.IMAGE, ".svg": AssetType.IMAGE,
    ".mp4": AssetType.VIDEO, ".mov": AssetType.VIDEO, ".webm": AssetType.VIDEO, ".mkv": AssetType.VIDEO,
    ".mp3": AssetType.AUDIO, ".wav": AssetType.AUDIO, ".ogg": AssetType.AUDIO, ".flac": AssetType.AUDIO,
    ".txt": AssetType.TEXT, ".md": AssetType.TEXT, ".json": AssetType.TEXT, ".csv": AssetType.TEXT,
}


async def _video_thumbnail_file(video_path: Path) -> str:
    """用 ffmpeg 截取视频第一帧作为缩略图，失败返回空字符串。"""
    try:
        thumb_dir = Path(__file__).resolve().parents[3] / "storage" / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{video_path.stem}.jpg"
        await get_ffmpeg_service().create_thumbnail(video_path, thumb_path, time=0.5, width=480)
        return str(thumb_path)
    except Exception as exc:
        logger.warning("[assets] video thumbnail failed: %s", exc)
        return ""


@router.post("/upload", summary="本地上传素材入库")
async def upload_asset(
    file: UploadFile = File(...),
    title: str = Form(""),
    session = Depends(get_asset_session),
):
    """上传本地素材（图片/视频/音频/文本）入库。

    3D 模型（glb/gltf/obj/fbx/usdz/zip）走 upload-model3d 的解包逻辑。
    """
    filename = file.filename or "upload"
    content = await file.read()
    ext = Path(filename).suffix.lower()

    if ext in {".glb", ".gltf", ".obj", ".fbx", ".usdz", ".zip"} or content[:2] == b"PK":
        return await _import_uploaded_model(filename, content, title, session)

    asset_type = _UPLOAD_EXT_TO_TYPE.get(ext)
    if asset_type is None:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext or '未知'}")

    upload_dir = _upload_assets_dir() / uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / filename
    target.write_bytes(content)

    thumbnail = ""
    if asset_type == AssetType.VIDEO:
        thumbnail = await _video_thumbnail_file(target)

    created = await AssetHubFacade(session).create_imported_file(
        file_path=str(target),
        title=(title or Path(filename).stem or "上传素材")[:120],
        asset_type=asset_type,
        source="upload",
        source_url="",
        thumbnail_url=thumbnail or "",
        metadata={"original_filename": filename, "upload": True},
        tags=["upload", str(asset_type.value)],
    )
    return {"success": True, "asset_id": created.node_id}


@router.get("/{asset_id}/stream", summary="播放资产视频文件")
async def stream_asset(
    asset_id: str,
    request: Request,
    session = Depends(get_asset_session),
):
    hub_primary = await _get_asset_hub_primary(session, asset_id)
    if hub_primary:
        node, _version, rep = hub_primary
        media_type = rep.mime_type or mimetypes.guess_type(rep.file_path)[0] or "application/octet-stream"
        node_meta = _dict_value(node.metadata_json)
        params = _dict_value(_version.params_json)
        lineage = _dict_value(_version.lineage_json)
        if _type_from_representation(node, media_type, node_meta=node_meta, lineage=lineage, params=params) != "video":
            raise HTTPException(status_code=400, detail="当前资产不是视频")
        path = _resolve_asset_file_path(rep.file_path)
        return _range_file_response(request, str(path), media_type)

    raise HTTPException(status_code=404, detail="资产不存在")


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


async def _get_course_episode(session, asset_id: str, episode_index: int) -> dict:
    node = await session.get(AssetNode, asset_id)
    if not node:
        raise HTTPException(status_code=404, detail="资产不存在")
    metadata = _dict_value(node.metadata_json)
    if metadata.get("type") != "paid_course":
        raise HTTPException(status_code=400, detail="当前资产不是课程")
    episodes = metadata.get("episodes") or []
    episode = next((item for item in episodes if item.get("index") == episode_index), None)
    if not episode and 0 <= episode_index - 1 < len(episodes):
        episode = episodes[episode_index - 1]
    if not episode:
        raise HTTPException(status_code=404, detail="章节不存在")
    return episode


async def _get_course_episode_file(session, asset_id: str, episode_index: int) -> str:
    episode = await _get_course_episode(session, asset_id, episode_index)
    file_path = episode.get("file_path") or ""
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="章节文件不存在")
    return file_path


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
    session = Depends(get_asset_session),
):
    node = await session.get(AssetNode, asset_id)
    if not node:
        raise HTTPException(status_code=404, detail="资产不存在")
    path = _sidecar_path_from_meta(_dict_value(node.metadata_json), "subtitle", subtitle_index)
    return Response(content=_subtitle_to_vtt(path), media_type="text/vtt; charset=utf-8")


@router.get("/{asset_id}/sidecars/danmaku", summary="读取资产弹幕")
async def get_asset_danmaku(
    asset_id: str,
    session = Depends(get_asset_session),
):
    node = await session.get(AssetNode, asset_id)
    if not node:
        raise HTTPException(status_code=404, detail="资产不存在")
    path = _sidecar_path_from_meta(_dict_value(node.metadata_json), "danmaku")
    return Response(content=Path(path).read_text(encoding="utf-8", errors="ignore"), media_type="application/json; charset=utf-8")


@router.get("/{asset_id}/course-episodes/{episode_index}/sidecars/subtitles/{subtitle_index}.vtt", summary="读取课程章节字幕")
async def get_course_episode_subtitle(
    asset_id: str,
    episode_index: int,
    subtitle_index: int,
    session = Depends(get_asset_session),
):
    episode = await _get_course_episode(session, asset_id, episode_index)
    path = _sidecar_path_from_meta(episode, "subtitle", subtitle_index)
    return Response(content=_subtitle_to_vtt(path), media_type="text/vtt; charset=utf-8")


@router.get("/{asset_id}/course-episodes/{episode_index}/sidecars/danmaku", summary="读取课程章节弹幕")
async def get_course_episode_danmaku(
    asset_id: str,
    episode_index: int,
    session = Depends(get_asset_session),
):
    episode = await _get_course_episode(session, asset_id, episode_index)
    path = _sidecar_path_from_meta(episode, "danmaku")
    return Response(content=Path(path).read_text(encoding="utf-8", errors="ignore"), media_type="application/json; charset=utf-8")


@router.get("/{asset_id}/course-episodes/{episode_index}/download", summary="下载课程章节文件")
async def download_course_episode_asset(
    asset_id: str,
    episode_index: int,
    session = Depends(get_asset_session),
):
    file_path = await _get_course_episode_file(session, asset_id, episode_index)

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=os.path.basename(file_path),
    )


@router.get("/{asset_id}/course-episodes/{episode_index}/stream", summary="播放课程章节文件")
async def stream_course_episode_asset(
    asset_id: str,
    episode_index: int,
    session = Depends(get_asset_session),
):
    file_path = await _get_course_episode_file(session, asset_id, episode_index)
    return FileResponse(path=file_path, media_type="video/mp4")


# ---------------------------------------------------------------------------
# 标签管理（必须在泛型路由之前）
# ---------------------------------------------------------------------------

class CreateTagRequest(BaseModel):
    name: str
    color: str = "#1890ff"


@router.get("/tags", response_model=TagListResponse, summary="标签列表")
async def list_tags(
    session = Depends(get_asset_session),
):
    result = await session.execute(select(Tag).order_by(Tag.created_at.desc()))
    tags = list(result.scalars().all())
    return TagListResponse(success=True, data=[_tag_to_dict(t) for t in tags])


@router.post("/tags", response_model=TagResponse, summary="创建标签")
async def create_tag(
    req: CreateTagRequest,
    session = Depends(get_asset_session),
):
    result = await session.execute(select(Tag).where(Tag.name == req.name).limit(1))
    tag = result.scalar_one_or_none()
    if not tag:
        tag = Tag(
            id=str(uuid4()),
            name=req.name,
            color=req.color,
            parent_id=None,
            level=0,
            path=f"root/{req.name}",
            asset_count=0,
        )
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
    elif req.color and tag.color != req.color:
        tag.color = req.color
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
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


@router.post("/{asset_id}/thumbnail", summary="设置资产缩略图")
async def set_asset_thumbnail(
    asset_id: str,
    file: UploadFile = File(...),
    session = Depends(get_asset_session),
):
    """保存前端渲染出的模型截图作为资产缩略图。"""
    content = await file.read()
    directory = Path(__file__).resolve().parents[3] / "storage" / "thumbnails"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{asset_id}.png"
    target.write_bytes(content)

    node = await session.get(AssetNode, asset_id)
    if not node:
        raise HTTPException(status_code=404, detail="资产不存在")
    node.thumbnail_url = str(target)
    node.updated_at = datetime.utcnow() if hasattr(datetime, "utcnow") else datetime.now()
    session.add(node)
    await session.commit()
    return {"success": True, "thumbnail_url": _hub_file_url(str(target))}


@router.get("/{asset_id}/thumbnail", summary="代理加载封面图")
async def proxy_thumbnail(
    asset_id: str,
    original: bool = Query(False, description="是否返回原始参考图（而非生成的图）"),
    session = Depends(get_asset_session),
):
    """
    通过后端代理加载图片，解决跨域/防盗链问题。
    - 默认返回生成的图（cover_url）
    - original=true 返回原始参考图（用于再次生成时的参考）
    支持本地文件路径、远程 URL 和 base64 数据。
    """
    hub_primary = await _get_asset_hub_primary(session, asset_id)
    if hub_primary:
        node, _version, rep = hub_primary
        node_meta = _dict_value(getattr(node, "metadata_json", {}))
        if original:
            source_image = node_meta.get("source_image")
            if source_image:
                return await _fetch_image(source_image, node_meta.get("platform") or "")
            reference_images = node_meta.get("reference_images") or []
            if reference_images:
                return await _fetch_image(reference_images[0], node_meta.get("platform") or "")
        source = node.thumbnail_url or (rep.file_path if (rep.mime_type or "").startswith("image/") else "")
        if source:
            return await _fetch_image(source, "")

    from app.api.v1.proxy import placeholder_image_response
    return placeholder_image_response("NO IMAGE")


# ---------------------------------------------------------------------------
# 资产详情 GET /api/v1/assets/:id
# ---------------------------------------------------------------------------

@router.get("/{asset_id}", response_model=AssetResponse, summary="资产详情")
async def get_asset(
    asset_id: str,
    session = Depends(get_asset_session),
):
    hub_asset = await _get_asset_hub_card(session, asset_id, include_metadata=True)
    if hub_asset:
        return AssetResponse(success=True, data=hub_asset)

    raise HTTPException(status_code=404, detail="资产不存在")


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
    session = Depends(get_asset_session),
):
    node = await session.get(AssetNode, asset_id)
    if not node:
        raise HTTPException(status_code=404, detail="资产不存在")
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
    session.add(node)
    await session.commit()
    await session.refresh(node)
    hub_asset = await _get_asset_hub_card(session, asset_id, include_metadata=True)
    if hub_asset:
        return AssetResponse(success=True, data=hub_asset)

    raise HTTPException(status_code=404, detail="资产不存在")


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
    session = Depends(get_asset_session),
):
    if mode not in {"soft", "del_file", "hard"}:
        raise HTTPException(status_code=400, detail="不支持的删除模式")

    hub_deleted = await _soft_delete_asset_hub_node(session, asset_id, mode=mode)
    if hub_deleted:
        return {"success": True, "message": f"已{mode}删除"}

    raise HTTPException(status_code=404, detail="资产不存在")


@router.post("/{asset_id}/restore", summary="恢复软删除的资产")
async def restore_asset(
    asset_id: str,
    session = Depends(get_asset_session),
):
    hub_restored = await _restore_asset_hub_node(session, asset_id)
    if hub_restored:
        return {"success": True, "message": "已恢复"}

    raise HTTPException(status_code=404, detail="资产不存在或未处于软删除状态")
