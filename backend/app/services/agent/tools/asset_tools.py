"""Asset Hub tools exposed to the Agent Center."""

from __future__ import annotations

import logging
from typing import Optional

from app.db.database import AsyncSessionLocal
from app.db.models.asset_hub import AssetType
from app.services.agent.registry import register_tool
from app.services.asset_hub import (
    AssetNodeService,
    AssetRepresentationService,
    AssetVersionService,
)

logger = logging.getLogger("ylcraft.agent.tools.asset")


def _asset_type(value: Optional[str]) -> AssetType | None:
    if not value:
        return None
    normalized = value.lower()
    aliases = {
        "img": "image",
        "picture": "image",
        "photo": "image",
        "document": "text",
        "doc": "text",
        "bgm": "audio",
        "music": "audio",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return AssetType(normalized)
    except ValueError:
        return None


async def _node_to_tool_dict(session, node) -> dict:
    version_service = AssetVersionService(session)
    rep_service = AssetRepresentationService(session)
    latest = await version_service.get_latest_version(str(node.id))
    rep = await rep_service.get_primary(str(latest.id)) if latest else None
    metadata = node.metadata_json or {}
    return {
        "id": str(node.id),
        "title": node.name,
        "type": node.asset_type.value if hasattr(node.asset_type, "value") else str(node.asset_type),
        "thumbnail_url": node.thumbnail_url,
        "tags": node.tags_json or [],
        "metadata": metadata,
        "status": metadata.get("status", "READY"),
        "file_path": getattr(rep, "file_path", "") if rep else "",
        "mime_type": getattr(rep, "mime_type", "") if rep else "",
        "file_size": getattr(rep, "file_size", 0) if rep else 0,
        "width": getattr(rep, "width", None) if rep else None,
        "height": getattr(rep, "height", None) if rep else None,
        "duration": getattr(rep, "duration", None) if rep else None,
        "version_id": str(latest.id) if latest else "",
        "version_number": getattr(latest, "version_number", None) if latest else None,
    }


@register_tool(
    name="search_assets",
    description="搜索素材库中的图片、视频、音频、文本等资产。",
    category="asset",
    examples=["搜索主角立绘", "查找可用的背景参考图", "搜索时长大于 1 分钟的视频素材"],
    input_schema_note=(
        "query 可为空；asset_type 支持 image/video/audio/text/model/character 等，也支持 img/photo/bgm/music/doc 别名；"
        "tags 为需要同时命中的标签；status 默认 READY，可传 all 不过滤；limit 最大 50。"
    ),
    output_schema_note="返回 success、assets、total、matched_total；assets 含 id/title/type/tags/status/file_path/mime_type/尺寸/时长/版本。",
    risk_level="read",
    output_type="asset_search_results",
)
async def search_assets(
    query: str = "",
    asset_type: Optional[str] = None,
    tags: Optional[list[str]] = None,
    status: str = "READY",
    limit: int = 10,
):
    async with AsyncSessionLocal() as session:
        node_service = AssetNodeService(session)
        results, total = await node_service.list_nodes(
            asset_type=_asset_type(asset_type),
            keyword=query or None,
            page=1,
            page_size=max(1, min(int(limit or 10), 50)),
        )
        if tags:
            wanted = {str(tag).lower() for tag in tags if str(tag or "").strip()}
            filtered = []
            for node in results:
                names = {tag.name.lower() for tag in await node_service.get_tags(str(node.id))}
                names.update(str(tag).lower() for tag in (node.tags_json or []))
                if wanted.issubset(names):
                    filtered.append(node)
            results = filtered
        assets = [await _node_to_tool_dict(session, node) for node in results]
        if status and status.lower() != "all":
            assets = [item for item in assets if str(item.get("status") or "READY").upper() == status.upper()]
        return {
            "success": True,
            "assets": assets,
            "total": len(assets),
            "matched_total": total,
        }


@register_tool(
    name="get_asset_detail",
    description="获取素材库资产详情。",
    category="asset",
    examples=["获取 asset_123 的详细信息", "查看这张参考图的本地文件路径"],
    input_schema_note="必须提供 asset_id，通常来自素材库搜索、项目引用或生图返回的资产 id。",
    output_schema_note="返回 success 和 asset；asset 含主文件路径、缩略图、标签、元数据、版本信息和媒体属性。",
    risk_level="read",
    output_type="asset_detail",
)
async def get_asset_detail(asset_id: str):
    async with AsyncSessionLocal() as session:
        node_service = AssetNodeService(session)
        asset = await node_service.get(asset_id)
        if not asset:
            return {"success": False, "message": "资产不存在"}
        return {
            "success": True,
            "asset": await _node_to_tool_dict(session, asset),
        }


@register_tool(
    name="download_asset",
    description="返回素材库资产的本地可访问文件引用。",
    category="asset",
    requires_progress=True,
    input_schema_note="必须提供 asset_id；只返回本地可访问文件路径，不会复制、下载或删除原文件。",
    output_schema_note="返回 asset_id、file_path、mime_type、file_size，可供后续剪辑、字幕、BGM 或参考图工具继续使用。",
    risk_level="read",
    output_type="asset_file_reference",
)
async def download_asset(asset_id: str):
    async with AsyncSessionLocal() as session:
        node_service = AssetNodeService(session)
        node = await node_service.get(asset_id)
        if not node:
            return {"success": False, "message": "资产不存在"}
        data = await _node_to_tool_dict(session, node)
        file_path = data.get("file_path")
        if not file_path:
            return {"success": False, "message": "资产没有可用文件路径"}
        return {
            "success": True,
            "asset_id": asset_id,
            "file_path": file_path,
            "mime_type": data.get("mime_type", ""),
            "file_size": data.get("file_size", 0),
        }


@register_tool(
    name="add_asset_tag",
    description="为素材库资产添加标签。",
    category="asset",
    input_schema_note="必须提供 asset_id 和单个 tag；tag 建议使用短中文名或业务标签。",
    output_schema_note="返回 success/message；会写入素材标签关系，便于后续筛选和智能体检索。",
    risk_level="write",
    output_type="asset_mutation_result",
)
async def add_asset_tag(asset_id: str, tag: str):
    async with AsyncSessionLocal() as session:
        node_service = AssetNodeService(session)
        asset = await node_service.get(asset_id)
        if not asset:
            return {"success": False, "message": "资产不存在"}
        await node_service.add_tags(asset_id, [tag])
        await session.commit()
        return {
            "success": True,
            "message": "标签已添加",
        }


@register_tool(
    name="delete_asset",
    description="把素材库资产标记为已删除。",
    category="asset",
    examples=["删除这个视频素材", "把那张图片标记为已删除"],
    input_schema_note="必须提供 asset_id；当前实现为标记 DELETED，不直接移除磁盘文件。",
    output_schema_note="返回 success/message；删除后素材在默认 search_assets(status=READY) 中会被过滤。",
    risk_level="delete",
    output_type="asset_mutation_result",
)
async def delete_asset(asset_id: str):
    async with AsyncSessionLocal() as session:
        node_service = AssetNodeService(session)
        asset = await node_service.get(asset_id)
        if not asset:
            return {"success": False, "message": "删除失败，资产可能不存在"}
        await node_service.update(
            asset_id,
            metadata={
                "status": "DELETED",
                "deleted_by": "agent_tool",
            },
        )
        await session.commit()
        return {
            "success": True,
            "message": "资产已标记为删除",
        }
