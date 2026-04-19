"""
YLCraft — AssetService CRUD 实现

支持素材资产的完整 CRUD、标签管理、软删除。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset, AssetTag, AssetType, AssetStatus

logger = logging.getLogger("ylcraft.asset_service")


class AssetService:
    """素材资产 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # 资产 CRUD
    # -------------------------------------------------------------------------

    async def list_assets(
        self,
        asset_type: AssetType | None = None,
        platform: str | None = None,
        status: AssetStatus | None = None,
        search: str | None = None,
        tags: list[str] | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Asset], int]:
        """
        多条件分页查询资产。
        返回 (资产列表, 总数)
        """
        conditions = []
        if asset_type:
            conditions.append(Asset.asset_type == asset_type.value)
        if platform:
            conditions.append(Asset.platform == platform)
        if status:
            conditions.append(Asset.status == status.value)
        if search:
            conditions.append(Asset.title.contains(search))

        query = select(Asset)
        if conditions:
            for cond in conditions:
                query = query.where(cond)

        # 标签过滤（JSON 数组包含）
        if tags:
            for tag in tags:
                conditions.append(Asset.tags.contains(tag))

        # 总数
        count_query = select(func.count(Asset.id))
        if conditions:
            for cond in conditions:
                count_query = count_query.where(cond)
        total = (await self.session.execute(count_query)).scalar_one()

        # 排序
        sort_column = getattr(Asset, sort_by, Asset.created_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.session.execute(query)
        assets = result.scalars().all()
        return list(assets), total

    async def get_by_id(self, asset_id: str) -> Asset | None:
        """根据 ID 获取资产"""
        result = await self.session.execute(
            select(Asset).where(Asset.id == asset_id)
        )
        return result.scalar_one_or_none()

    async def get_by_url(self, url: str) -> Asset | None:
        """根据 source_url 查找资产（用于去重）"""
        result = await self.session.execute(
            select(Asset).where(Asset.source_url == url)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Asset:
        """创建资产记录"""
        asset = Asset(**kwargs)
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        return asset

    async def create_from_parse(
        self,
        source_url: str,
        title: str,
        platform: str,
        author: str = "",
        cover_url: str = "",
        duration: int = 0,
        metadata: dict | None = None,
        asset_type: AssetType = AssetType.VIDEO,
    ) -> Asset:
        """
        从解析结果创建资产记录（status=PARSED）。

        用于 parse 接口：解析完成后先创建资产占位，
        下载完成后再更新为 READY。
        """
        # 检查是否已存在（URL 去重）
        existing = await self.get_by_url(source_url)
        if existing:
            # 已存在则更新元信息
            existing.title = title
            existing.author = author
            if cover_url:
                existing.thumbnail_path = cover_url
            if duration:
                existing.duration = duration
            if metadata:
                existing.metadata_json = json.dumps(metadata, ensure_ascii=False)
            existing.updated_at = datetime.now()
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        # 新建记录
        asset = Asset(
            asset_type=asset_type,
            title=title,
            source_url=source_url,
            platform=platform,
            author=author,
            thumbnail_path=cover_url,  # cover_url → thumbnail_path
            duration=duration,
            status=AssetStatus.PARSED,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            tags="[]",
        )
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        logger.info(f"[AssetService] created asset | id={asset.id} | title={title}")
        return asset

    async def mark_ready(self, asset: Asset, file_path: str, file_size: int, mime_type: str) -> Asset:
        """将 PARSED 状态的资产标记为 READY（下载完成后调用）"""
        asset.file_path = file_path
        asset.file_size = file_size
        asset.mime_type = mime_type
        asset.status = AssetStatus.READY
        asset.downloaded_at = datetime.now()
        asset.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(asset)
        logger.info(f"[AssetService] marked ready | id={asset.id} | path={file_path[:60]}")
        return asset

    async def update_tags(self, asset: Asset, tag_names: list[str]) -> Asset:
        """更新资产的标签列表"""
        asset.tags = json.dumps(tag_names, ensure_ascii=False)
        asset.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(asset)
        # 更新标签计数
        for tag_name in tag_names:
            await self._inc_tag_count(tag_name)
        return asset

    async def delete(self, asset_id: str, hard: bool = False) -> bool:
        """
        删除资产。
        - hard=False：软删除（保留记录）
        - hard=True：同时删除物理文件和数据库记录
        """
        asset = await self.get_by_id(asset_id)
        if not asset:
            return False

        if hard:
            # 删除物理文件
            if asset.file_path and os.path.exists(asset.file_path):
                try:
                    os.remove(asset.file_path)
                    logger.info(f"Deleted file: {asset.file_path}")
                except OSError as e:
                    logger.warning(f"Failed to delete file {asset.file_path}: {e}")
            # 删除缩略图
            if asset.thumbnail_path and os.path.exists(asset.thumbnail_path):
                try:
                    os.remove(asset.thumbnail_path)
                except OSError:
                    pass

        await self.session.delete(asset)
        await self.session.flush()
        return True

    # -------------------------------------------------------------------------
    # 标签管理
    # -------------------------------------------------------------------------

    async def list_tags(self) -> list[AssetTag]:
        """列出所有标签"""
        result = await self.session.execute(
            select(AssetTag).order_by(AssetTag.asset_count.desc())
        )
        return list(result.scalars().all())

    async def get_or_create_tag(self, name: str, color: str = "#1890ff") -> AssetTag:
        """根据名称查找标签，不存在则创建"""
        result = await self.session.execute(
            select(AssetTag).where(AssetTag.name == name)
        )
        tag = result.scalar_one_or_none()
        if tag:
            return tag
        tag = AssetTag(name=name, color=color)
        self.session.add(tag)
        await self.session.flush()
        await self.session.refresh(tag)
        return tag

    async def _inc_tag_count(self, tag_name: str) -> None:
        """增加标签计数"""
        result = await self.session.execute(
            select(AssetTag).where(AssetTag.name == tag_name)
        )
        tag = result.scalar_one_or_none()
        if tag:
            tag.asset_count = (tag.asset_count or 0) + 1
            await self.session.flush()
