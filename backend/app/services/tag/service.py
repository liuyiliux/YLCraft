"""
YLCraft — 标签服务

实现树形标签系统的完整 CRUD、递归查询、路径查询等功能。
"""

from __future__ import annotations

import logging
from uuid import uuid4
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import Tag, AssetTagLink, AssetNode, AssetType

logger = logging.getLogger("ylcraft.tag_service")


class TagService:
    """树形标签服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # 标签 CRUD
    # -------------------------------------------------------------------------

    async def create_tag(
        self,
        name: str,
        parent_id: Optional[str] = None,
        color: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Tag:
        """创建标签"""
        # 获取父标签信息
        level = 0
        path = f"root/{name}"

        if parent_id:
            parent = await self.session.get(Tag, parent_id)
            if parent:
                level = parent.level + 1
                path = f"{parent.path}/{name}"

        tag = Tag(
            id=str(uuid4()),
            name=name,
            parent_id=parent_id,
            level=level,
            path=path,
            color=color,
            category=category,
            asset_count=0,
        )

        self.session.add(tag)
        await self.session.flush()
        await self.session.refresh(tag)

        logger.info(f"[TagService] created tag | id={tag.id} | path={tag.path}")
        return tag

    async def get_tag(self, tag_id: str) -> Optional[Tag]:
        """根据 ID 获取标签"""
        return await self.session.get(Tag, tag_id)

    async def get_tag_by_path(self, path: str) -> Optional[Tag]:
        """根据路径获取标签"""
        result = await self.session.execute(
            select(Tag).where(Tag.path == path)
        )
        return result.scalar_one_or_none()

    async def update_tag(
        self,
        tag_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[Tag]:
        """更新标签信息"""
        tag = await self.session.get(Tag, tag_id)
        if not tag:
            return None

        if name is not None and name != tag.name:
            old_path = tag.path
            tag.name = name

            # 更新自身路径
            if tag.parent_id:
                parent = await self.session.get(Tag, tag.parent_id)
                if parent:
                    tag.path = f"{parent.path}/{name}"
            else:
                tag.path = f"root/{name}"

            # 更新所有子标签路径
            await self._update_child_paths(old_path, tag.path)

        if color is not None:
            tag.color = color
        if category is not None:
            tag.category = category

        await self.session.flush()
        await self.session.refresh(tag)
        return tag

    async def _update_child_paths(self, old_prefix: str, new_prefix: str) -> None:
        """更新子标签的路径前缀"""
        result = await self.session.execute(
            select(Tag).where(Tag.path.like(f"{old_prefix}/%"))
        )
        children = result.scalars().all()

        for child in children:
            child.path = child.path.replace(old_prefix, new_prefix, 1)

        await self.session.flush()

    async def delete_tag(self, tag_id: str, cascade: bool = True) -> bool:
        """
        删除标签
        - cascade=True：同时删除所有子标签
        - cascade=False：只删除自身，子标签变为根标签
        """
        tag = await self.session.get(Tag, tag_id)
        if not tag:
            return False

        if cascade:
            # 删除所有子标签
            children = await self.get_descendants(tag_id)
            for child in children:
                await self.session.delete(child)

            # 删除所有关联的 AssetTagLink
            links = await self.session.execute(
                select(AssetTagLink).where(AssetTagLink.tag_id == tag_id)
            )
            for link in links.scalars().all():
                await self.session.delete(link)

        else:
            # 子标签变为根标签
            children = await self.get_descendants(tag_id)
            for child in children:
                child.parent_id = None
                child.level = 0
                child.path = f"root/{child.name}"

        await self.session.delete(tag)
        await self.session.flush()
        return True

    # -------------------------------------------------------------------------
    # 标签树查询
    # -------------------------------------------------------------------------

    async def get_root_tags(self) -> List[Tag]:
        """获取所有根标签（level=0）"""
        result = await self.session.execute(
            select(Tag).where(Tag.level == 0).order_by(Tag.name)
        )
        return list(result.scalars().all())

    async def get_children(self, parent_id: str) -> List[Tag]:
        """获取直接子标签"""
        result = await self.session.execute(
            select(Tag)
            .where(Tag.parent_id == parent_id)
            .order_by(Tag.name)
        )
        return list(result.scalars().all())

    async def get_descendants(self, parent_id: str) -> List[Tag]:
        """获取所有后代标签（递归查询）"""
        parent = await self.session.get(Tag, parent_id)
        if not parent:
            return []

        result = await self.session.execute(
            select(Tag).where(Tag.path.like(f"{parent.path}/%"))
        )
        return list(result.scalars().all())

    async def get_ancestors(self, tag_id: str) -> List[Tag]:
        """获取所有祖先标签（从子到父）"""
        tag = await self.session.get(Tag, tag_id)
        if not tag:
            return []

        ancestors = []
        current = tag

        while current.parent_id:
            parent = await self.session.get(Tag, current.parent_id)
            if parent:
                ancestors.insert(0, parent)
                current = parent
            else:
                break

        return ancestors

    async def get_tag_tree(self, root_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取标签树结构（嵌套格式）
        返回格式：[{id, name, children: [...], ...}]
        """
        if root_id:
            root = await self.session.get(Tag, root_id)
            if not root:
                return []
            base_path = root.path
            tags = await self.session.execute(
                select(Tag).where(Tag.path.like(f"{base_path}%"))
            )
        else:
            tags = await self.session.execute(select(Tag))

        tag_list = list(tags.scalars().all())
        return self._build_tree(tag_list, root_id)

    def _build_tree(
        self, tags: List[Tag], root_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """将标签列表构建为树形结构"""
        tag_map = {tag.id: tag for tag in tags}
        tree = []

        for tag in tags:
            node = {
                "id": tag.id,
                "name": tag.name,
                "path": tag.path,
                "level": tag.level,
                "color": tag.color,
                "category": tag.category,
                "asset_count": tag.asset_count,
                "children": [],
            }

            if tag.parent_id and tag.parent_id in tag_map:
                tag_map[tag.parent_id].children.append(node)
            elif root_id is None:
                tree.append(node)

        return tree

    # -------------------------------------------------------------------------
    # 标签-资产关联
    # -------------------------------------------------------------------------

    async def tag_asset(
        self,
        asset_id: str,
        tag_id: str,
        confidence: Optional[float] = None,
        source: str = "manual",
    ) -> Optional[AssetTagLink]:
        """给资产添加标签"""
        # 检查是否已存在关联
        result = await self.session.execute(
            select(AssetTagLink)
            .where(AssetTagLink.asset_node_id == asset_id)
            .where(AssetTagLink.tag_id == tag_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            if confidence is not None:
                existing.confidence = confidence
            existing.source = source
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        link = AssetTagLink(
            id=str(uuid4()),
            asset_node_id=asset_id,
            tag_id=tag_id,
            confidence=confidence,
            source=source,
        )

        self.session.add(link)

        # 更新标签计数
        tag = await self.session.get(Tag, tag_id)
        if tag:
            tag.asset_count += 1

        await self.session.flush()
        await self.session.refresh(link)
        return link

    async def untag_asset(self, asset_id: str, tag_id: str) -> bool:
        """移除资产的标签"""
        result = await self.session.execute(
            select(AssetTagLink)
            .where(AssetTagLink.asset_node_id == asset_id)
            .where(AssetTagLink.tag_id == tag_id)
        )
        link = result.scalar_one_or_none()

        if not link:
            return False

        await self.session.delete(link)

        # 更新标签计数
        tag = await self.session.get(Tag, tag_id)
        if tag and tag.asset_count > 0:
            tag.asset_count -= 1

        await self.session.flush()
        return True

    async def batch_tag_assets(
        self,
        asset_ids: List[str],
        tag_id: str,
        confidence: Optional[float] = None,
        source: str = "manual",
    ) -> int:
        """批量给多个资产添加标签"""
        count = 0
        for asset_id in asset_ids:
            await self.tag_asset(asset_id, tag_id, confidence, source)
            count += 1
        return count

    async def get_asset_tags(self, asset_id: str) -> List[Tag]:
        """获取资产的所有标签"""
        result = await self.session.execute(
            select(Tag)
            .join(AssetTagLink, Tag.id == AssetTagLink.tag_id)
            .where(AssetTagLink.asset_node_id == asset_id)
        )
        return list(result.scalars().all())

    async def get_tagged_assets(self, tag_id: str) -> List[AssetNode]:
        """获取某个标签下的所有资产"""
        result = await self.session.execute(
            select(AssetNode)
            .join(AssetTagLink, AssetNode.id == AssetTagLink.asset_node_id)
            .where(AssetTagLink.tag_id == tag_id)
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 搜索和统计
    # -------------------------------------------------------------------------

    async def search_tags(
        self,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        min_asset_count: int = 0,
    ) -> List[Tag]:
        """搜索标签"""
        query = select(Tag)

        if keyword:
            query = query.where(Tag.name.ilike(f"%{keyword}%"))

        if category:
            query = query.where(Tag.category == category)

        if min_asset_count > 0:
            query = query.where(Tag.asset_count >= min_asset_count)

        query = query.order_by(Tag.asset_count.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_tags_by_category(self, category: str) -> List[Tag]:
        """按分类获取标签"""
        result = await self.session.execute(
            select(Tag)
            .where(Tag.category == category)
            .order_by(Tag.name)
        )
        return list(result.scalars().all())

    async def get_category_stats(self) -> List[Dict[str, Any]]:
        """获取各分类的标签统计"""
        result = await self.session.execute(
            select(
                Tag.category,
                func.count(Tag.id).label("tag_count"),
                func.sum(Tag.asset_count).label("total_assets"),
            )
            .group_by(Tag.category)
            .order_by(func.count(Tag.id).desc())
        )

        stats = []
        for row in result.all():
            stats.append({
                "category": row.category or "未分类",
                "tag_count": row.tag_count,
                "total_assets": row.total_assets or 0,
            })

        return stats

    async def sync_asset_counts(self, tag_id: Optional[str] = None) -> None:
        """
        同步标签的 asset_count（全量或单个标签）
        """
        if tag_id:
            # 单个标签
            tag = await self.session.get(Tag, tag_id)
            if not tag:
                return
            count_result = await self.session.execute(
                select(func.count(AssetTagLink.id)).where(AssetTagLink.tag_id == tag_id)
            )
            tag.asset_count = count_result.scalar() or 0
        else:
            # 全量同步
            result = await self.session.execute(
                select(
                    AssetTagLink.tag_id,
                    func.count(AssetTagLink.id).label("count")
                ).group_by(AssetTagLink.tag_id)
            )
            counts = {row.tag_id: row.count for row in result.all()}
            tags_result = await self.session.execute(select(Tag))
            for tag in tags_result.scalars().all():
                tag.asset_count = counts.get(tag.id, 0)
        await self.session.flush()

    async def suggest_tags(self, asset_id: str) -> List[Dict[str, Any]]:
        """
        根据资产内容建议标签（预留接口）
        
        实际实现时会调用 AI 模型分析资产内容，返回建议标签列表。
        """
        asset = await self.session.get(AssetNode, asset_id)
        if not asset:
            return []

        # TODO: 集成 AI 自动标签功能
        # 分析资产的 metadata_json 和其他信息，生成建议标签
        suggestions = []

        # 基于资产类型建议标签
        if asset.asset_type == AssetType.IMAGE:
            suggestions.append(
                {"name": "图片", "category": "type", "confidence": 1.0}
            )
        elif asset.asset_type == AssetType.VIDEO:
            suggestions.append(
                {"name": "视频", "category": "type", "confidence": 1.0}
            )
        elif asset.asset_type == AssetType.CHARACTER:
            suggestions.append(
                {"name": "角色", "category": "type", "confidence": 1.0}
            )

        return suggestions
