"""
YLCraft — 素材库工具

为 Agent 提供素材库操作工具。
"""

from __future__ import annotations

import logging
from typing import Optional

from app.db.models.asset_hub import AssetType
from app.services.agent.registry import register_tool
from app.services.asset_hub import (
    AssetNodeService,
    AssetRepresentationService,
    AssetVersionService,
)
from app.db.database import AsyncSessionLocal

logger = logging.getLogger("ylcraft.agent.tools.asset")


def _asset_type(value: Optional[str]) -> AssetType | None:
    if not value:
        return None
    normalized = value.lower()
    aliases = {
        "img": "image",
        "picture": "image",
        "document": "text",
        "doc": "text",
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
    description="搜索素材库中的视频、图片、音频等资产",
    category="asset",
    examples=["搜索搞笑猫咪视频", "找找有没有美食素材", "搜索时长大于 1 分钟的视频"],
)
async def search_assets(
    query: str,
    asset_type: Optional[str] = None,
    tags: Optional[list[str]] = None,
    limit: int = 10,
):
    """
    搜索素材库

    Args:
        query: 搜索关键词
        asset_type: 资产类型（VIDEO/IMAGE/AUDIO/SUBTITLE/BGM）
        tags: 标签过滤
        limit: 返回数量限制
    """
    async with AsyncSessionLocal() as session:
        node_service = AssetNodeService(session)
        results, total = await node_service.list_nodes(
            asset_type=_asset_type(asset_type),
            keyword=query or None,
            page=1,
            page_size=max(1, min(limit, 50)),
        )
        if tags:
            wanted = {tag.lower() for tag in tags}
            filtered = []
            for node in results:
                names = {tag.name.lower() for tag in await node_service.get_tags(str(node.id))}
                names.update(str(tag).lower() for tag in (node.tags_json or []))
                if wanted.issubset(names):
                    filtered.append(node)
            results = filtered
        return {
            "success": True,
            "assets": [await _node_to_tool_dict(session, node) for node in results],
            "total": len(results),
            "matched_total": total,
        }


@register_tool(
    name="get_asset_detail",
    description="获取资产详情",
    category="asset",
    examples=["获取 asset_123 的详细信息"],
)
async def get_asset_detail(asset_id: str):
    """
    获取资产详情

    Args:
        asset_id: 资产 ID
    """
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
    description="下载资产文件到本地",
    category="asset",
    requires_progress=True,
)
async def download_asset(asset_id: str):
    """
    下载资产文件

    Args:
        asset_id: 资产 ID
    """
    async with AsyncSessionLocal() as session:
        node_service = AssetNodeService(session)
        node = await node_service.get(asset_id)
        if not node:
            return {"success": False, "message": "资产不存在"}
        data = await _node_to_tool_dict(session, node)
        file_path = data.get("file_path")
        if not file_path:
            return {"success": False, "message": "资产没有可下载文件"}
        return {
            "success": True,
            "asset_id": asset_id,
            "file_path": file_path,
            "mime_type": data.get("mime_type", ""),
            "file_size": data.get("file_size", 0),
        }


@register_tool(
    name="add_asset_tag",
    description="为资产添加标签",
    category="asset",
)
async def add_asset_tag(asset_id: str, tag: str):
    """
    为资产添加标签

    Args:
        asset_id: 资产 ID
        tag: 标签名称
    """
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
    description="删除素材库中的资产",
    category="asset",
    examples=["删除这个视频素材", "把那张图片删掉"],
)
async def delete_asset(asset_id: str):
    """
    删除资产

    Args:
        asset_id: 资产 ID
    """
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
            "message": "资产已删除",
        }
