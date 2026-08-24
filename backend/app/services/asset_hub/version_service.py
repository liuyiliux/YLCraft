"""
YLCraft — 资产版本服务

AssetVersion 是 AssetNode 的版本快照，记录每次生成的提示词、模型、参数、谱系。
每次重新生成（如角色立绘换装）就创建一个新版本，可回看历史。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import AssetNode, AssetVersion, AssetRelation, RelationType

logger = logging.getLogger("ylcraft.asset_hub.version")


class AssetVersionService:
    """资产版本管理服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # 版本 CRUD
    # -------------------------------------------------------------------------

    async def create(
        self,
        asset_node_id: str,
        prompt_used: Optional[str] = None,
        model_used: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        lineage: Optional[Dict[str, Any]] = None,
        parent_version_id: Optional[str] = None,
        auto_increment: bool = True,
    ) -> AssetVersion:
        """
        创建资产版本快照。

        Args:
            asset_node_id: 所属资产节点 ID
            prompt_used: 本次生成使用的提示词
            model_used: 使用的模型名
            params: 生成参数（steps/cfg_scale/seed 等）
            lineage: 谱系信息（源素材 ID 列表、参考图路径等）
            parent_version_id: 上一版本 ID（用于版本链）
            auto_increment: 自动递增版本号（基于该节点已有版本数）

        Returns:
            AssetVersion: 创建后的版本
        """
        # 验证节点存在
        node = await self.session.get(AssetNode, asset_node_id)
        if not node:
            raise ValueError(f"AssetNode {asset_node_id} 不存在")

        version_number = 1
        if auto_increment:
            latest = await self.get_latest_version(asset_node_id)
            if latest:
                version_number = latest.version_number + 1

        version = AssetVersion(
            id=str(uuid4()),
            asset_node_id=asset_node_id,
            version_number=version_number,
            prompt_used=prompt_used,
            model_used=model_used,
            params_json=params or {},
            lineage_json=lineage or {},
        )
        self.session.add(version)
        await self.session.flush()
        await self.session.refresh(version)
        # asyncpg 把 PG UUID 字段返回为 UUID 对象，统一转 str 避免上游 SQLAlchemy
        # 在写 String 字段时收到 UUID 类型导致 ::VARCHAR 编码失败
        version.id = str(version.id)
        version.asset_node_id = str(version.asset_node_id)

        # 如果指定了父版本，建立版本链谱系
        if parent_version_id:
            await self.link_versions(
                source_id=parent_version_id,
                target_id=version.id,
                relation_type=RelationType.DERIVED_FROM,
            )

        logger.info(
            f"[AssetVersionService] created | id={version.id} | "
            f"node={asset_node_id} | v{version_number}"
        )
        return version

    async def get(self, version_id: str) -> Optional[AssetVersion]:
        """根据 ID 获取版本"""
        return await self.session.get(AssetVersion, version_id)

    async def delete(self, version_id: str) -> bool:
        """删除版本（不允许删除唯一版本）"""
        version = await self.session.get(AssetVersion, version_id)
        if not version:
            return False

        # 检查是否为唯一版本
        count_result = await self.session.execute(
            select(func.count(AssetVersion.id)).where(
                AssetVersion.asset_node_id == version.asset_node_id
            )
        )
        if count_result.scalar_one() <= 1:
            raise ValueError("不允许删除资产的唯一版本")

        await self.session.delete(version)
        await self.session.flush()
        return True

    # -------------------------------------------------------------------------
    # 查询
    # -------------------------------------------------------------------------

    async def list_versions(
        self,
        asset_node_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[AssetVersion], int]:
        """
        分页获取某资产节点的所有版本（按版本号倒序）。
        """
        count_query = (
            select(func.count(AssetVersion.id))
            .where(AssetVersion.asset_node_id == asset_node_id)
        )
        total = (await self.session.execute(count_query)).scalar_one()

        query = (
            select(AssetVersion)
            .where(AssetVersion.asset_node_id == asset_node_id)
            .order_by(desc(AssetVersion.version_number))
        )
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.session.execute(query)
        versions = list(result.scalars().all())
        return versions, total

    async def get_latest_version(
        self, asset_node_id: str
    ) -> Optional[AssetVersion]:
        """获取最新版本"""
        result = await self.session.execute(
            select(AssetVersion)
            .where(AssetVersion.asset_node_id == asset_node_id)
            .order_by(desc(AssetVersion.version_number))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_versions(self, asset_node_ids: list[str]) -> dict[str, AssetVersion]:
        """批量获取多个资产节点的最新版本（一次 IN 查询，消除 N+1）。"""
        if not asset_node_ids:
            return {}
        result = await self.session.execute(
            select(AssetVersion).where(AssetVersion.asset_node_id.in_(asset_node_ids))
        )
        versions = result.scalars().all()
        latest: dict[str, AssetVersion] = {}
        for v in versions:
            nid = str(v.asset_node_id)
            if nid not in latest or v.version_number > latest[nid].version_number:
                latest[nid] = v
        return latest

    async def get_version_by_number(
        self, asset_node_id: str, version_number: int
    ) -> Optional[AssetVersion]:
        """按版本号获取"""
        result = await self.session.execute(
            select(AssetVersion).where(
                AssetVersion.asset_node_id == asset_node_id,
                AssetVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # 谱系（AssetRelation 便捷方法）
    # -------------------------------------------------------------------------

    async def link_versions(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType = RelationType.DERIVED_FROM,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssetRelation:
        """
        建立两个资产（版本或节点）之间的关系。

        Args:
            source_id: 源资产 ID（被引用/被派生）
            target_id: 目标资产 ID（派生/引用方）
            relation_type: 关系类型
            context: 关系上下文（如"作为参考图使用"）
        """
        relation = AssetRelation(
            id=str(uuid4()),
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            context_json=context or {},
        )
        self.session.add(relation)
        await self.session.flush()
        await self.session.refresh(relation)
        return relation

    async def get_relations(
        self,
        asset_id: str,
        direction: str = "both",
        relation_type: Optional[RelationType] = None,
    ) -> List[AssetRelation]:
        """
        查询资产的关系。

        Args:
            asset_id: 资产 ID（节点或版本）
            direction: "upstream"（作为 target）/ "downstream"（作为 source）/ "both"
            relation_type: 关系类型过滤
        """
        conditions = []
        if direction in ("upstream", "both"):
            conditions.append(AssetRelation.target_id == asset_id)
        if direction in ("downstream", "both"):
            conditions.append(AssetRelation.source_id == asset_id)

        query = select(AssetRelation).where(
            (AssetRelation.target_id == asset_id)
            | (AssetRelation.source_id == asset_id)
        )
        if relation_type is not None:
            query = query.where(AssetRelation.relation_type == relation_type)

        result = await self.session.execute(query)
        return list(result.scalars().all())
