"""
YLCraft — 资产节点服务

AssetNode 是资产中枢的根节点，每个资产（图片/视频/角色/...）对应一个 Node。
Node 支持父子层级（如角色的不同装扮），并维护与标签的多对多关联。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, func, or_, cast, String, text, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import (
    AIModel,
    AssetEmbedding,
    AssetNode,
    AssetRelation,
    AssetRepresentation,
    AssetType,
    AssetTagLink,
    AssetVersion,
    Tag,
)

logger = logging.getLogger("ylcraft.asset_hub.node")


class AssetNodeService:
    """资产节点 CRUD + 查询服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    async def create(
        self,
        name: str,
        asset_type: AssetType | str,
        parent_id: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        quality_score: Optional[float] = None,
        phash: Optional[str] = None,
    ) -> AssetNode:
        """
        创建资产节点。

        Args:
            name: 节点名称（如角色名、图片标题）
            asset_type: 资产类型
            parent_id: 父节点 ID（角色多装扮场景）
            thumbnail_url: 缩略图 URL
            metadata: 元数据（存入 metadata_json）
            tags: 标签名称列表（自动创建或关联已有标签）
            quality_score: 质量评分 0.0-1.0
            phash: 感知哈希（用于去重）

        Returns:
            AssetNode: 创建后的节点
        """
        if isinstance(asset_type, str):
            asset_type = AssetType(asset_type)

        node = AssetNode(
            id=str(uuid4()),
            name=name,
            asset_type=asset_type,
            parent_id=parent_id,
            thumbnail_url=thumbnail_url,
            metadata_json=metadata or {},
            tags_json=[],
            quality_score=quality_score,
            phash=phash,
        )
        self.session.add(node)
        await self.session.flush()
        await self.session.refresh(node)
        # asyncpg 把 PG UUID 字段返回为 UUID 对象，统一转 str 避免上游 SQLAlchemy
        # 在写 String 字段时收到 UUID 类型导致 ::VARCHAR 编码失败
        node.id = str(node.id)
        if node.parent_id is not None:
            node.parent_id = str(node.parent_id)

        # 处理标签（按名称自动创建或关联）
        if tags:
            for tag_name in tags:
                await self._ensure_tagged(node.id, tag_name)

        logger.info(
            f"[AssetNodeService] created | id={node.id} | type={asset_type.value} | name={name}"
        )
        return node

    async def get(self, node_id: str) -> Optional[AssetNode]:
        """根据 ID 获取节点"""
        return await self.session.get(AssetNode, node_id)

    async def update(
        self,
        node_id: str,
        name: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        quality_score: Optional[float] = None,
        phash: Optional[str] = None,
        increment_use_count: bool = False,
    ) -> Optional[AssetNode]:
        """
        更新节点字段。metadata 为合并式更新（不覆盖未指定的键）。

        Args:
            increment_use_count: 是否同时递增 use_count
        """
        node = await self.session.get(AssetNode, node_id)
        if not node:
            return None

        if name is not None:
            node.name = name
        if thumbnail_url is not None:
            node.thumbnail_url = thumbnail_url
        if metadata is not None:
            merged = dict(node.metadata_json or {})
            merged.update(metadata)
            node.metadata_json = merged
        if quality_score is not None:
            node.quality_score = quality_score
        if phash is not None:
            node.phash = phash
        if increment_use_count:
            node.use_count = (node.use_count or 0) + 1

        node.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(node)
        return node

    async def delete(self, node_id: str, cascade: bool = False) -> bool:
        """
        删除节点（引用行级联清理）。

        Args:
            cascade: 是否级联删除子节点

        顺序纪律：先删引用行（表示 → 版本 → 向量/关系/标签/AI 模型）并 flush，
        再删主行——这些表对 ``asset_nodes`` 的外键都是 NO ACTION，而主/子表之间
        没有 relationship()，UoW 的跨表删除顺序不可靠（PG 实测会先发主行 DELETE）。
        """
        node = await self.session.get(AssetNode, node_id)
        if not node:
            return False

        children = await self.list_children(node_id)
        if children and not cascade:
            raise ValueError("该节点存在子节点：请使用 cascade=true 级联删除")
        for child in children:
            await self.delete(child.id, cascade=True)

        # 版本与其文件表示（表示挂在版本上，必须先删）
        versions = (
            await self.session.execute(
                select(AssetVersion).where(AssetVersion.asset_node_id == node_id)
            )
        ).scalars().all()
        version_ids = [version.id for version in versions]
        if version_ids:
            representations = (
                await self.session.execute(
                    select(AssetRepresentation).where(
                        AssetRepresentation.asset_version_id.in_(version_ids)
                    )
                )
            ).scalars().all()
            for rep in representations:
                self._remove_file_quietly(rep.file_path)
                await self.session.delete(rep)

        # 节点的直接引用行：向量 / 标签 / AI 模型 / 关系（双向）
        for model, field in (
            (AssetVersion, "asset_node_id"),
            (AssetEmbedding, "asset_node_id"),
            (AssetTagLink, "asset_node_id"),
            (AIModel, "asset_node_id"),
            (AssetRelation, "source_id"),
            (AssetRelation, "target_id"),
        ):
            rows = (
                await self.session.execute(
                    select(model).where(getattr(model, field) == node_id)
                )
            ).scalars().all()
            for row in rows:
                await self.session.delete(row)

        # 引用行删除先落库，再删主行
        await self.session.flush()
        await self.session.delete(node)
        await self.session.flush()
        return True

    @staticmethod
    def _remove_file_quietly(file_path: str) -> None:
        """尽力删除磁盘文件；失败只记日志，不阻塞行删除。"""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.warning("删除资产文件失败（忽略）：%s（%s）", file_path, exc)

    # -------------------------------------------------------------------------
    # 查询
    # -------------------------------------------------------------------------

    async def list_nodes(
        self,
        asset_type: Optional[AssetType | str] = None,
        parent_id: Optional[str] = None,
        tag_ids: Optional[List[str]] = None,
        keyword: Optional[str] = None,
        include_children: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[AssetNode], int]:
        """
        分页查询资产节点。

        Args:
            asset_type: 按类型过滤
            parent_id: 按父节点过滤（None 表示不限，传 "root" 表示只看根节点）
            tag_ids: 按标签过滤（AND 关系：同时包含所有标签）
            keyword: 名称模糊搜索
            include_children: parent_id 过滤时是否包含所有后代

        Returns:
            (节点列表, 总数)
        """
        # 用原生 SQL 避免 SQLModel enum 字段与 asyncpg 的类型冲突
        # （SQLModel 把 AssetType enum 注册成 PG enum 类型，导致 ::assettype cast 报错）
        where_parts: List[str] = []
        params: Dict[str, Any] = {}

        if asset_type is not None:
            if isinstance(asset_type, AssetType):
                type_value = asset_type.value
            else:
                type_value = AssetType(asset_type).value
            # SQLAlchemy Enum 类型默认存 enum 的 name（大写），不是 value（小写）
            # 所以查询时要用 name 匹配 DB 实际存储的值
            enum_name = asset_type.name if isinstance(asset_type, AssetType) else AssetType(asset_type).name
            where_parts.append("asset_type = :asset_type")
            params["asset_type"] = enum_name

        if parent_id is not None:
            if parent_id == "root":
                where_parts.append("parent_id IS NULL")
            else:
                where_parts.append("parent_id = :parent_id")
                params["parent_id"] = parent_id

        if keyword:
            where_parts.append("name ILIKE :keyword")
            params["keyword"] = f"%{keyword}%"

        # 标签过滤（AND 关系）
        if tag_ids:
            for i, tag_id in enumerate(tag_ids):
                alias = f"atl_{i}"
                where_parts.append(
                    f"id IN (SELECT asset_node_id FROM asset_tag_links WHERE tag_id = :{alias})"
                )
                params[alias] = tag_id

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # 总数
        count_sql = text(f"SELECT count(*) FROM asset_nodes{where_clause}")
        total = (await self.session.execute(count_sql, params)).scalar_one()

        # 分页查询
        offset = (page - 1) * page_size
        list_sql = text(
            f"SELECT * FROM asset_nodes{where_clause} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        )
        params["limit"] = page_size
        params["offset"] = offset
        result = await self.session.execute(list_sql, params)

        # 原生 SQL 返回原始 DB 值，需手动转成 ORM 对象
        # - id/parent_id: asyncpg 返回 UUID 对象，需转 str
        # - asset_type: DB 存 enum name（大写），需转成 enum value（小写）
        nodes = []
        for row in result.mappings().all():
            row_dict = dict(row)
            if "id" in row_dict and row_dict["id"] is not None:
                row_dict["id"] = str(row_dict["id"])
            if "parent_id" in row_dict and row_dict["parent_id"] is not None:
                row_dict["parent_id"] = str(row_dict["parent_id"])
            if "asset_type" in row_dict and row_dict["asset_type"] is not None:
                # DB 存的是 enum name（大写），转成 value（小写）
                at = row_dict["asset_type"]
                if isinstance(at, str):
                    try:
                        row_dict["asset_type"] = AssetType[at.upper()].value
                    except KeyError:
                        row_dict["asset_type"] = at
            node = AssetNode.model_validate(row_dict)
            nodes.append(node)

        return nodes, total

    async def list_children(self, parent_id: str) -> List[AssetNode]:
        """获取直接子节点"""
        result = await self.session.execute(
            select(AssetNode)
            .where(AssetNode.parent_id == parent_id)
            .order_by(AssetNode.created_at)
        )
        return list(result.scalars().all())

    async def get_by_phash(self, phash: str) -> Optional[AssetNode]:
        """根据感知哈希去重查询"""
        result = await self.session.execute(
            select(AssetNode).where(AssetNode.phash == phash)
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # 标签关联（便捷方法，完整功能见 TagService）
    # -------------------------------------------------------------------------

    async def _ensure_tagged(self, node_id: str, tag_name: str) -> None:
        """按名称确保节点带有某个标签（不存在则创建）"""
        # 查找已有标签
        result = await self.session.execute(
            select(Tag).where(Tag.name == tag_name).limit(1)
        )
        tag = result.scalar_one_or_none()

        if not tag:
            tag = Tag(
                id=str(uuid4()),
                name=tag_name,
                parent_id=None,
                level=0,
                path=f"root/{tag_name}",
                category=None,
                asset_count=0,
            )
            self.session.add(tag)
            await self.session.flush()

        # 创建关联（去重）
        existing = await self.session.execute(
            select(AssetTagLink)
            .where(AssetTagLink.asset_node_id == node_id)
            .where(AssetTagLink.tag_id == tag.id)
        )
        if existing.scalar_one_or_none() is None:
            link = AssetTagLink(
                id=str(uuid4()),
                asset_node_id=node_id,
                tag_id=tag.id,
                source="manual",
            )
            self.session.add(link)
            tag.asset_count = (tag.asset_count or 0) + 1
            await self.session.flush()

    async def add_tags(self, node_id: str, tag_names: List[str]) -> None:
        """批量按名称添加标签"""
        for name in tag_names:
            await self._ensure_tagged(node_id, name)

    async def get_tags(self, node_id: str) -> List[Tag]:
        """获取节点的所有标签"""
        result = await self.session.execute(
            select(Tag)
            .join(AssetTagLink, Tag.id == AssetTagLink.tag_id)
            .where(AssetTagLink.asset_node_id == node_id)
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 统计
    # -------------------------------------------------------------------------

    async def count_by_type(self) -> Dict[str, int]:
        """按类型统计资产数"""
        result = await self.session.execute(
            select(AssetNode.asset_type, func.count(AssetNode.id))
            .group_by(AssetNode.asset_type)
        )
        return {
            (t.value if hasattr(t, "value") else str(t)): c
            for t, c in result.all()
        }
