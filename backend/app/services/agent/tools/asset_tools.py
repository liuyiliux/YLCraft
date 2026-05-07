"""
YLCraft — 素材库工具

为 Agent 提供素材库操作工具。
"""

from __future__ import annotations

import logging
from typing import Optional

from app.services.agent.registry import register_tool
from app.services.asset.service import AssetService
from app.db.database import AsyncSessionLocal

logger = logging.getLogger("ylcraft.agent.tools.asset")


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
        service = AssetService(session)
        # 注意：实际实现需要根据 AssetService 的实际接口调整
        results = await service.search(query, asset_type=asset_type, tags=tags, limit=limit)
        return {
            "success": True,
            "assets": [r.to_dict() for r in results],
            "total": len(results),
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
        service = AssetService(session)
        asset = await service.get(asset_id)
        if not asset:
            return {"success": False, "message": "资产不存在"}
        return {
            "success": True,
            "asset": asset.to_dict(),
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
        service = AssetService(session)
        result = await service.download(asset_id)
        return result


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
        service = AssetService(session)
        ok = await service.add_tag(asset_id, tag)
        return {
            "success": ok,
            "message": "标签已添加" if ok else "添加失败",
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
        service = AssetService(session)
        ok = await service.delete(asset_id)
        return {
            "success": ok,
            "message": "资产已删除" if ok else "删除失败，资产可能不存在",
        }
