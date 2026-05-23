"""
YLCraft — 导出服务

实现数据集导出、质量评分、去重检测等功能。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4
import httpx
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import (
    AssetNode,
    AssetVersion,
    AssetRepresentation,
    AssetTagLink,
    Tag,
    AssetType,
)

logger = logging.getLogger("ylcraft.export_service")


class ExportService:
    """导出服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # 数据集导出
    # -------------------------------------------------------------------------

    async def export_dataset(
        self,
        output_path: str,
        filters: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True,
        include_lineage: bool = False,
        max_size_mb: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        导出数据集

        Args:
            output_path: 输出 ZIP 文件路径
            filters: 过滤条件（tag_ids, asset_types, min_quality_score 等）
            include_metadata: 是否包含元数据
            include_lineage: 是否包含谱系信息
            max_size_mb: 单个 ZIP 文件最大大小（MB），超过则分卷

        Returns:
            {"success": True, "total_count": N, "files": [...]}
        """
        filters = filters or {}
        max_size_bytes = (max_size_mb * 1024 * 1024) if max_size_mb else None

        # 构建查询
        query = select(AssetNode)

        # 应用过滤条件
        if filters.get("asset_types"):
            query = query.where(AssetNode.asset_type.in_(filters["asset_types"]))

        if filters.get("min_quality_score"):
            query = query.where(
                AssetNode.quality_score >= filters["min_quality_score"]
            )

        if filters.get("tag_ids"):
            # 按标签过滤
            tag_asset_ids = (
                await self.session.execute(
                    select(AssetTagLink.asset_node_id)
                    .where(AssetTagLink.tag_id.in_(filters["tag_ids"]))
                )
            ).scalars().all()
            query = query.where(AssetNode.id.in_(tag_asset_ids))

        result = await self.session.execute(query)
        assets = result.scalars().all()

        if max_size_bytes:
            # 分卷导出
            return await self._export_dataset_multi_volume(
                assets=assets,
                base_output_path=output_path,
                max_size_bytes=max_size_bytes,
                include_metadata=include_metadata,
                include_lineage=include_lineage,
            )
        else:
            # 单文件导出
            return await self._export_dataset_single_volume(
                assets=assets,
                output_path=output_path,
                include_metadata=include_metadata,
                include_lineage=include_lineage,
            )

    async def _export_dataset_single_volume(
        self,
        assets: List[AssetNode],
        output_path: str,
        include_metadata: bool,
        include_lineage: bool,
    ) -> Dict[str, Any]:
        """单文件导出（内部函数）"""
        # 创建 ZIP 文件
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        metadata_list = []

        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
            metadata_list = await self._write_assets_to_zip(
                assets=assets,
                zf=zf,
                include_metadata=include_metadata,
                include_lineage=include_lineage,
            )

            # 写入 summary.json
            summary = {
                "total_count": len(assets),
                "asset_types": {},
                "volume_number": 1,
                "total_volumes": 1,
                "export_time": str(Path(output_path).stat().st_mtime),
            }

            for asset in assets:
                asset_type = asset.asset_type.value
                summary["asset_types"][asset_type] = summary["asset_types"].get(asset_type, 0) + 1

            zf.writestr("summary.json", json.dumps(summary, ensure_ascii=False, indent=2))

        logger.info(f"[ExportService] Dataset exported: {output_path} ({len(assets)} assets)")

        return {
            "success": True,
            "total_count": len(assets),
            "output_paths": [str(output_file)],
            "file_count": sum(len(a.get("files", [])) for a in metadata_list),
        }

    async def _export_dataset_multi_volume(
        self,
        assets: List[AssetNode],
        base_output_path: str,
        max_size_bytes: float,
        include_metadata: bool,
        include_lineage: bool,
    ) -> Dict[str, Any]:
        """分卷导出（内部函数）"""
        base_path = Path(base_output_path)
        output_paths = []
        current_volume = 1
        current_size = 0
        current_assets = []
        total_metadata = []

        for asset in assets:
            # 估算这个资产会增加多少大小（基于文件大小）
            estimated_size = await self._estimate_asset_size(asset)
            
            # 如果超过限制，或者是第一个，就创建新卷
            if current_assets and (current_size + estimated_size > max_size_bytes):
                # 写入当前卷
                volume_path = f"{base_path.with_suffix('')}.{current_volume}{base_path.suffix}"
                await self._write_single_volume(
                    assets=current_assets,
                    output_path=volume_path,
                    volume_number=current_volume,
                    include_metadata=include_metadata,
                    include_lineage=include_lineage,
                )
                output_paths.append(volume_path)
                current_volume += 1
                current_assets = []
                current_size = 0

            current_assets.append(asset)
            current_size += estimated_size

        # 写入最后一卷
        if current_assets:
            volume_path = f"{base_path.with_suffix('')}.{current_volume}{base_path.suffix}"
            await self._write_single_volume(
                assets=current_assets,
                output_path=volume_path,
                volume_number=current_volume,
                total_volumes=current_volume,
                include_metadata=include_metadata,
                include_lineage=include_lineage,
            )
            output_paths.append(volume_path)

        logger.info(f"[ExportService] Multi-volume export: {len(output_paths)} volumes")

        return {
            "success": True,
            "total_count": len(assets),
            "output_paths": output_paths,
            "total_volumes": len(output_paths),
        }

    async def _write_single_volume(
        self,
        assets: List[AssetNode],
        output_path: str,
        volume_number: int,
        total_volumes: Optional[int] = None,
        include_metadata: bool = True,
        include_lineage: bool = False,
    ):
        """写入单个分卷 ZIP 文件"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
            metadata_list = await self._write_assets_to_zip(
                assets=assets,
                zf=zf,
                include_metadata=include_metadata,
                include_lineage=include_lineage,
            )

            # 写入 summary.json
            summary = {
                "total_count": len(assets),
                "volume_number": volume_number,
                "total_volumes": total_volumes or volume_number,
                "export_time": str(Path(output_path).stat().st_mtime),
            }
            zf.writestr("summary.json", json.dumps(summary, ensure_ascii=False, indent=2))

    async def _write_assets_to_zip(
        self,
        assets: List[AssetNode],
        zf: zipfile.ZipFile,
        include_metadata: bool,
        include_lineage: bool,
    ) -> List[Dict[str, Any]]:
        """写入资产到 ZIP 文件（内部函数）"""
        metadata_list = []

        for asset in assets:
            # 收集元数据
            asset_data = {
                "id": str(asset.id),
                "name": asset.name,
                "asset_type": asset.asset_type.value,
                "created_at": asset.created_at.isoformat() if asset.created_at else None,
            }

            if include_metadata:
                asset_data["metadata"] = asset.metadata_json
                asset_data["quality_score"] = asset.quality_score
                asset_data["phash"] = asset.phash

            # 获取版本信息
            versions = (
                await self.session.execute(
                    select(AssetVersion)
                    .where(AssetVersion.asset_node_id == asset.id)
                )
            ).scalars().all()

            if versions and include_lineage:
                asset_data["versions"] = [
                    {
                        "version_number": v.version_number,
                        "prompt_used": v.prompt_used,
                        "model_used": v.model_used,
                        "lineage": v.lineage_json,
                    }
                    for v in versions
                ]

            # 获取标签
            tags = (
                await self.session.execute(
                    select(Tag.name)
                    .join(AssetTagLink, Tag.id == AssetTagLink.tag_id)
                    .where(AssetTagLink.asset_node_id == asset.id)
                )
            ).scalars().all()
            asset_data["tags"] = list(tags)

            # 添加文件
            file_paths = []
            for version in versions:
                reps = (
                    await self.session.execute(
                        select(AssetRepresentation)
                        .where(AssetRepresentation.asset_version_id == version.id)
                    )
                ).scalars().all()

                for rep in reps:
                    if rep.file_path and Path(rep.file_path).exists():
                        # 添加文件到 ZIP
                        arcname = f"files/{asset.id}/{Path(rep.file_path).name}"
                        zf.write(rep.file_path, arcname)
                        file_paths.append(arcname)

            asset_data["files"] = file_paths
            metadata_list.append(asset_data)

        # 写入 metadata.json
        zf.writestr(
            "metadata.json",
            json.dumps(metadata_list, ensure_ascii=False, indent=2),
        )

        return metadata_list

    async def _estimate_asset_size(self, asset: AssetNode) -> int:
        """估算资产在 ZIP 中的大小（字节）"""
        total_size = 0
        
        versions = (
            await self.session.execute(
                select(AssetVersion)
                .where(AssetVersion.asset_node_id == asset.id)
            )
        ).scalars().all()

        for version in versions:
            reps = (
                await self.session.execute(
                    select(AssetRepresentation)
                    .where(AssetRepresentation.asset_version_id == version.id)
                )
            ).scalars().all()

            for rep in reps:
                if rep.file_path and Path(rep.file_path).exists():
                    total_size += Path(rep.file_path).stat().st_size

        # 加上 metadata 的估算
        total_size += 1024  # 预留空间

        return total_size

    # -------------------------------------------------------------------------
    # 质量评分
    # -------------------------------------------------------------------------

    async def calculate_quality_score(self, asset_id: str) -> Optional[float]:
        """
        计算资产质量评分（预留接口）

        实际实现需要集成美学评分模型、模糊检测等。
        """
        asset = await self.session.get(AssetNode, asset_id)
        if not asset:
            return None

        # 获取 representations
        versions = (
            await self.session.execute(
                select(AssetVersion)
                .where(AssetVersion.asset_node_id == asset_id)
            )
        ).scalars().all()

        score = 0.5  # 基础分
        metadata = asset.metadata_json or {}

        # 根据资产类型调整
        if asset.asset_type == AssetType.IMAGE:
            score = 0.6
            # 尝试图像质量检测
            image_quality = await self._analyze_image_quality(versions)
            if image_quality:
                score += (image_quality - 0.5) * 0.3

        elif asset.asset_type == AssetType.VIDEO:
            score = 0.55
        elif asset.asset_type == AssetType.MODEL:
            score = 0.7

        # 根据 use_count 调整
        if asset.use_count > 0:
            score += min(asset.use_count * 0.01, 0.2)

        # 根据谱系完整性调整
        if versions:
            for version in versions:
                if version.prompt_used:
                    score += 0.05
                if version.lineage_json:
                    score += 0.05

        # 根据图像分辨率调整（在 metadata 中）
        if metadata.get("width") and metadata.get("height"):
            resolution = metadata["width"] * metadata["height"]
            if resolution >= 2000000:  # 2MP+
                score += 0.1
            elif resolution >= 1000000:  # 1MP+
                score += 0.05

        # 限制在 0-1 之间
        score = max(0.0, min(1.0, score))

        # 更新数据库
        asset.quality_score = score
        await self.session.commit()

        return score

    async def _analyze_image_quality(
        self,
        versions: List[AssetVersion],
    ) -> Optional[float]:
        """
        分析图像质量（模糊/噪点检测）

        预留接口，需要集成 OpenCV / PIL / ML 模型。
        
        简单实现：基于文件大小和分辨率估算
        """
        if not versions:
            return None

        try:
            for version in versions:
                reps = (
                    await self.session.execute(
                        select(AssetRepresentation)
                        .where(AssetRepresentation.asset_version_id == version.id)
                    )
                ).scalars().all()

                for rep in reps:
                    if rep.mime_type and rep.mime_type.startswith("image/"):
                        file_path = rep.file_path
                        if not file_path or not Path(file_path).exists():
                            continue

                        # 简单估算：基于文件大小 / 像素数量
                        if rep.width and rep.height and rep.file_size:
                            pixels = rep.width * rep.height
                            bytes_per_pixel = rep.file_size / pixels

                            # 经验值：正常图像在 1-30 bytes/pixel 范围
                            if 2 <= bytes_per_pixel <= 20:
                                return 0.8  # 正常
                            elif bytes_per_pixel > 20:
                                return 0.9  # 高清大图
                            elif 0.5 <= bytes_per_pixel < 2:
                                return 0.6  # 可能压缩过
                            else:
                                return 0.3  # 极小文件，可能有问题

        except Exception as e:
            logger.warning(f"[ExportService] Image quality analysis failed: {e}")

        return None

    async def batch_calculate_quality(
        self,
        asset_ids: Optional[List[str]] = None,
        asset_type: Optional[AssetType] = None,
    ) -> Dict[str, Any]:
        """批量计算质量评分"""
        query = select(AssetNode)

        if asset_ids:
            query = query.where(AssetNode.id.in_(asset_ids))
        elif asset_type:
            query = query.where(AssetNode.asset_type == asset_type)

        result = await self.session.execute(query)
        assets = result.scalars().all()

        stats = {"total": len(assets), "calculated": 0, "errors": 0}

        for asset in assets:
            try:
                score = await self.calculate_quality_score(asset.id)
                if score:
                    stats["calculated"] += 1
            except Exception as e:
                logger.error(f"[ExportService] Failed to calculate quality for {asset.id}: {e}")
                stats["errors"] += 1

        return stats

    # -------------------------------------------------------------------------
    # 去重检测
    # -------------------------------------------------------------------------

    async def find_duplicates_by_phash(
        self,
        threshold: float = 0.9,
    ) -> List[List[str]]:
        """
        使用 pHash 查找近似重复的资产

        预留接口，需要 pHash 库支持。
        """
        # TODO: 集成 imagehash 库进行 pHash 计算
        logger.info("[ExportService] pHash deduplication not implemented")
        return []

    async def find_duplicates_by_vector(
        self,
        asset_type: Optional[AssetType] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.95,
    ) -> List[Dict[str, Any]]:
        """
        使用向量相似度查找重复资产

        查找与任何资产高度相似的其他资产。
        """
        from app.db.models.asset_hub import AssetEmbedding

        # 构建查询
        query = text("""
            WITH similar_pairs AS (
                SELECT
                    a.asset_node_id as id1,
                    b.asset_node_id as id2,
                    1 - (a.embedding <=> b.embedding) as similarity
                FROM asset_embeddings a
                JOIN asset_embeddings b ON a.embedding_model = b.embedding_model
                WHERE a.id < b.id
                AND a.embedding_model = 'clip-ViT-B-32'
                AND 1 - (a.embedding <=> b.embedding) >= :threshold
            )
            SELECT DISTINCT
                LEAST(id1, id2) as asset_id_1,
                GREATEST(id1, id2) as asset_id_2,
                similarity
            FROM similar_pairs
            ORDER BY similarity DESC
            LIMIT 100
        """)

        result = await self.session.execute(
            query,
            {"threshold": similarity_threshold}
        )

        duplicates = []
        for row in result.all():
            duplicates.append({
                "asset_id_1": str(row.asset_id_1),
                "asset_id_2": str(row.asset_id_2),
                "similarity": float(row.similarity),
            })

        return duplicates

    async def merge_duplicates(
        self,
        primary_asset_id: str,
        duplicate_asset_ids: List[str],
        keep_references: bool = True,
    ) -> Dict[str, Any]:
        """
        合并重复资产

        将 duplicate_asset_ids 合并到 primary_asset_id，更新关联关系。
        """
        primary = await self.session.get(AssetNode, primary_asset_id)
        if not primary:
            return {"error": "Primary asset not found"}

        # 更新 use_count
        total_use_count = primary.use_count or 0
        for dup_id in duplicate_asset_ids:
            dup = await self.session.get(AssetNode, dup_id)
            if dup:
                total_use_count += dup.use_count or 0
                if keep_references:
                    # 创建关系
                    from app.db.models.asset_hub import AssetRelation, RelationType

                    # primary -> duplicate (VARIANT_OF)
                    relation = AssetRelation(
                        id=str(uuid4()),
                        source_id=primary_asset_id,
                        target_id=dup_id,
                        relation_type=RelationType.VARIANT_OF,
                    )
                    self.session.add(relation)

                # 软删除 duplicate
                # 可以设置 parent_id 指向 primary，或者添加 deleted_at 字段
                # 这里暂时标记为隐藏
                dup.parent_id = primary_asset_id

        primary.use_count = total_use_count
        await self.session.commit()

        return {
            "success": True,
            "merged_count": len(duplicate_asset_ids),
            "primary_asset_id": primary_asset_id,
        }

    # -------------------------------------------------------------------------
    # 统计信息
    # -------------------------------------------------------------------------

    async def get_dataset_stats(self) -> Dict[str, Any]:
        """获取数据集统计信息"""
        # 资产数量
        total_assets = (
            await self.session.execute(select(func.count(AssetNode.id)))
        ).scalar_one()

        # 按类型统计
        type_stats = (
            await self.session.execute(
                select(
                    AssetNode.asset_type,
                    func.count(AssetNode.id).label("count"),
                ).group_by(AssetNode.asset_type)
            )
        ).all()

        # 标签统计
        total_tags = (
            await self.session.execute(select(func.count(Tag.id)))
        ).scalar_one()

        # 平均质量分
        avg_quality = (
            await self.session.execute(
                select(func.avg(AssetNode.quality_score))
                .where(AssetNode.quality_score.isnot(None))
            )
        ).scalar_one()

        return {
            "total_assets": total_assets,
            "by_type": {row.asset_type.value: row.count for row in type_stats},
            "total_tags": total_tags,
            "avg_quality_score": float(avg_quality) if avg_quality else None,
        }
