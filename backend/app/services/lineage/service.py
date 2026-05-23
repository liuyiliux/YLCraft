"""
YLCraft — 谱系追踪服务

实现资产的血统追溯：
- 上游查询：查找资产的所有祖先（Prompt → Model → Output）
- 下游查询：查找资产的所有后代（Output → Variants）
- DAG 可视化数据生成
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any, Set
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import (
    AssetNode,
    AssetRelation,
    AssetVersion,
    RelationType,
)

logger = logging.getLogger("ylcraft.lineage_service")


class LineageService:
    """谱系追踪服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # 基础查询
    # -------------------------------------------------------------------------

    async def get_upstream(self, asset_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """
        获取上游谱系（递归向上追溯）

        返回格式：
        [
            {"id": "...", "name": "...", "asset_type": "...", "relation_type": "USES", "depth": 1},
            {"id": "...", "name": "...", "asset_type": "...", "relation_type": "USES", "depth": 2},
        ]
        """
        visited: Set[str] = set()
        upstream: List[Dict[str, Any]] = []

        await self._fetch_upstream_recursive(
            asset_id=asset_id,
            current_depth=1,
            max_depth=max_depth,
            visited=visited,
            results=upstream,
        )

        return upstream

    async def _fetch_upstream_recursive(
        self,
        asset_id: str,
        current_depth: int,
        max_depth: int,
        visited: Set[str],
        results: List[Dict[str, Any]],
    ) -> None:
        """递归获取上游（内部方法）"""
        if current_depth > max_depth or asset_id in visited:
            return

        visited.add(asset_id)

        # 查询所有指向当前资产的关系（当前资产是 target）
        query = text("""
            SELECT
                ar.id as relation_id,
                ar.source_id,
                ar.relation_type,
                ar.context_json,
                an.id as asset_id,
                an.name,
                an.asset_type,
                an.thumbnail_url,
                an.metadata_json
            FROM asset_relations ar
            JOIN asset_nodes an ON ar.source_id = an.id
            WHERE ar.target_id = :asset_id
        """)

        result = await self.session.execute(query, {"asset_id": asset_id})
        rows = result.all()

        for row in rows:
            source_id = str(row.source_id)

            if source_id not in visited:
                results.append({
                    "id": source_id,
                    "name": row.name,
                    "asset_type": row.asset_type,
                    "thumbnail_url": row.thumbnail_url,
                    "relation_type": row.relation_type,
                    "context": row.context_json,
                    "depth": current_depth,
                })

                # 递归向上
                await self._fetch_upstream_recursive(
                    asset_id=source_id,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                    visited=visited,
                    results=results,
                )

    async def get_downstream(self, asset_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """
        获取下游谱系（递归向下追溯）

        返回格式：
        [
            {"id": "...", "name": "...", "asset_type": "...", "relation_type": "VARIANT_OF", "depth": 1},
            {"id": "...", "name": "...", "asset_type": "...", "relation_type": "VARIANT_OF", "depth": 2},
        ]
        """
        visited: Set[str] = set()
        downstream: List[Dict[str, Any]] = []

        await self._fetch_downstream_recursive(
            asset_id=asset_id,
            current_depth=1,
            max_depth=max_depth,
            visited=visited,
            results=downstream,
        )

        return downstream

    async def _fetch_downstream_recursive(
        self,
        asset_id: str,
        current_depth: int,
        max_depth: int,
        visited: Set[str],
        results: List[Dict[str, Any]],
    ) -> None:
        """递归获取下游（内部方法）"""
        if current_depth > max_depth or asset_id in visited:
            return

        visited.add(asset_id)

        # 查询所有从当前资产出发的关系（当前资产是 source）
        query = text("""
            SELECT
                ar.id as relation_id,
                ar.target_id,
                ar.relation_type,
                ar.context_json,
                an.id as asset_id,
                an.name,
                an.asset_type,
                an.thumbnail_url,
                an.metadata_json
            FROM asset_relations ar
            JOIN asset_nodes an ON ar.target_id = an.id
            WHERE ar.source_id = :asset_id
        """)

        result = await self.session.execute(query, {"asset_id": asset_id})
        rows = result.all()

        for row in rows:
            target_id = str(row.target_id)

            if target_id not in visited:
                results.append({
                    "id": target_id,
                    "name": row.name,
                    "asset_type": row.asset_type,
                    "thumbnail_url": row.thumbnail_url,
                    "relation_type": row.relation_type,
                    "context": row.context_json,
                    "depth": current_depth,
                })

                # 递归向下
                await self._fetch_downstream_recursive(
                    asset_id=target_id,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                    visited=visited,
                    results=results,
                )

    async def get_full_lineage(self, asset_id: str, max_depth: int = 10) -> Dict[str, Any]:
        """
        获取完整谱系（上游 + 下游 + 当前节点）

        返回格式：
        {
            "center": {...},
            "upstream": [...],
            "downstream": [...],
            "graph": {
                "nodes": [...],
                "edges": [...]
            }
        }
        """
        # 获取当前节点
        center = await self.session.get(AssetNode, asset_id)
        if not center:
            return {"error": "Asset not found"}

        # 获取上游和下游
        upstream = await self.get_upstream(asset_id, max_depth)
        downstream = await self.get_downstream(asset_id, max_depth)

        # 构建图数据（D3.js / cytoscape.js 兼容格式）
        nodes = []
        edges = []

        # 中心节点
        nodes.append({
            "id": str(center.id),
            "name": center.name,
            "asset_type": center.asset_type.value,
            "thumbnail_url": center.thumbnail_url,
            "isCenter": True,
        })

        # 上游节点
        for item in upstream:
            if not any(n["id"] == item["id"] for n in nodes):
                nodes.append({
                    "id": item["id"],
                    "name": item["name"],
                    "asset_type": item["asset_type"],
                    "thumbnail_url": item.get("thumbnail_url"),
                    "isCenter": False,
                })
            edges.append({
                "source": item["id"],
                "target": asset_id if item["depth"] == 1 else upstream[upstream.index(item) - 1]["id"] if upstream.index(item) > 0 else asset_id,
                "relation_type": item["relation_type"],
                "direction": "upstream",
            })

        # 下游节点
        for item in downstream:
            if not any(n["id"] == item["id"] for n in nodes):
                nodes.append({
                    "id": item["id"],
                    "name": item["name"],
                    "asset_type": item["asset_type"],
                    "thumbnail_url": item.get("thumbnail_url"),
                    "isCenter": False,
                })
            edges.append({
                "source": asset_id if item["depth"] == 1 else downstream[downstream.index(item) - 1]["id"] if downstream.index(item) > 0 else asset_id,
                "target": item["id"],
                "relation_type": item["relation_type"],
                "direction": "downstream",
            })

        return {
            "center": {
                "id": str(center.id),
                "name": center.name,
                "asset_type": center.asset_type.value,
                "thumbnail_url": center.thumbnail_url,
                "metadata": center.metadata_json,
            },
            "upstream": upstream,
            "downstream": downstream,
            "graph": {
                "nodes": nodes,
                "edges": edges,
            },
        }

    # -------------------------------------------------------------------------
    # 谱系创建
    # -------------------------------------------------------------------------

    async def link_assets(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[AssetRelation]:
        """创建资产间的谱系关系"""
        # 检查是否已存在
        query = text("""
            SELECT id FROM asset_relations
            WHERE source_id = :source_id AND target_id = :target_id
        """)
        result = await self.session.execute(query, {
            "source_id": source_id,
            "target_id": target_id,
        })
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"[LineageService] Relation already exists: {source_id} -> {target_id}")
            return None

        relation = AssetRelation(
            id=str(uuid4()),
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            context_json=context or {},
        )

        self.session.add(relation)
        await self.session.commit()
        await self.session.refresh(relation)

        logger.info(f"[LineageService] Created relation: {source_id} -> {target_id} ({relation_type})")
        return relation

    async def create_prompt_to_output_chain(
        self,
        prompt_asset_id: str,
        model_asset_id: str,
        output_asset_id: str,
        output_version_id: Optional[str] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        创建完整的 Prompt → Model → Output 谱系链

        自动创建以下关系：
        - model -> output (USES)
        - prompt -> output (DERIVED_FROM)
        """
        context = {
            "chain_type": "text_to_image",
            **(extra_context or {}),
        }

        # Model → Output
        rel1 = await self.link_assets(
            source_id=model_asset_id,
            target_id=output_asset_id,
            relation_type=RelationType.USES,
            context={"role": "checkpoint", "chain_type": "text_to_image", **context},
        )

        # Prompt → Output
        rel2 = await self.link_assets(
            source_id=prompt_asset_id,
            target_id=output_asset_id,
            relation_type=RelationType.DERIVED_FROM,
            context={"role": "prompt", **context},
        )

        return {
            "model_to_output": str(rel1.id) if rel1 else None,
            "prompt_to_output": str(rel2.id) if rel2 else None,
        }

    async def create_comfyui_lineage(
        self,
        workflow_id: str,
        node_outputs: Dict[str, str],  # node_id -> asset_id
        final_output_id: str,
    ) -> List[AssetRelation]:
        """
        从 ComfyUI 工作流创建谱系

        Args:
            workflow_id: 工作流 ID
            node_outputs: 节点 ID 到资产 ID 的映射
            final_output_id: 最终输出资产 ID
        """
        relations = []

        for node_id, asset_id in node_outputs.items():
            if asset_id == final_output_id:
                continue

            relation = await self.link_assets(
                source_id=asset_id,
                target_id=final_output_id,
                relation_type=RelationType.USES,
                context={
                    "workflow_id": workflow_id,
                    "node_id": node_id,
                    "engine": "ComfyUI",
                },
            )

            if relation:
                relations.append(relation)

        return relations

    # -------------------------------------------------------------------------
    # 谱系分析
    # -------------------------------------------------------------------------

    async def get_lineage_stats(self, asset_id: str) -> Dict[str, Any]:
        """获取谱系统计信息"""
        upstream = await self.get_upstream(asset_id)
        downstream = await self.get_downstream(asset_id)

        # 按关系类型统计
        upstream_types: Dict[str, int] = {}
        downstream_types: Dict[str, int] = {}

        for item in upstream:
            rel_type = item["relation_type"]
            upstream_types[rel_type] = upstream_types.get(rel_type, 0) + 1

        for item in downstream:
            rel_type = item["relation_type"]
            downstream_types[rel_type] = downstream_types.get(rel_type, 0) + 1

        return {
            "asset_id": asset_id,
            "upstream_count": len(upstream),
            "downstream_count": len(downstream),
            "upstream_types": upstream_types,
            "downstream_types": downstream_types,
            "max_upstream_depth": max([u["depth"] for u in upstream], default=0),
            "max_downstream_depth": max([d["depth"] for d in downstream], default=0),
        }

    async def find_common_ancestor(self, asset_id_1: str, asset_id_2: str) -> Optional[Dict[str, Any]]:
        """查找两个资产的公共祖先"""
        # 获取两个资产的上游
        upstream_1 = await self.get_upstream(asset_id_1)
        upstream_2 = await self.get_upstream(asset_id_2)

        # 构建 ID 集合
        ancestors_1 = {item["id"] for item in upstream_1}
        ancestors_2 = {item["id"] for item in upstream_2}

        # 找交集
        common = ancestors_1 & ancestors_2

        if not common:
            return None

        # 返回最近的公共祖先（深度最大的）
        common_ancestors = [u for u in upstream_1 if u["id"] in common]
        common_ancestors.sort(key=lambda x: x["depth"], reverse=True)

        return common_ancestors[0] if common_ancestors else None

    async def find_common_descendant(self, asset_id_1: str, asset_id_2: str) -> Optional[Dict[str, Any]]:
        """查找两个资产的公共后代"""
        downstream_1 = await self.get_downstream(asset_id_1)
        downstream_2 = await self.get_downstream(asset_id_2)

        descendants_1 = {item["id"] for item in downstream_1}
        descendants_2 = {item["id"] for item in downstream_2}

        common = descendants_1 & descendants_2

        if not common:
            return None

        common_descendants = [d for d in downstream_1 if d["id"] in common]
        common_descendants.sort(key=lambda x: x["depth"])

        return common_descendants[0] if common_descendants else None

    # -------------------------------------------------------------------------
    # 批量操作
    # -------------------------------------------------------------------------

    async def delete_relation(self, relation_id: str) -> bool:
        """删除谱系关系"""
        result = await self.session.execute(
            select(AssetRelation).where(AssetRelation.id == relation_id)
        )
        relation = result.scalar_one_or_none()

        if not relation:
            return False

        await self.session.delete(relation)
        await self.session.commit()
        return True

    async def delete_all_relations(self, asset_id: str) -> int:
        """删除资产的所有谱系关系"""
        query = text("""
            DELETE FROM asset_relations
            WHERE source_id = :asset_id OR target_id = :asset_id
        """)
        result = await self.session.execute(query, {"asset_id": asset_id})
        await self.session.commit()
        return result.rowcount
