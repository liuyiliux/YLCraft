"""Agent tools for Asset Hub export, quality, and duplicate workflows."""

from __future__ import annotations

from typing import Any

from app.db.database import get_async_session
from app.db.models.asset_hub import AssetType
from app.services.agent.registry import register_tool
from app.services.export.service import ExportService


def _asset_type(value: str | None) -> AssetType | None:
    if not value:
        return None
    normalized = value.lower().strip()
    aliases = {"img": "image", "photo": "image", "picture": "image", "doc": "text", "document": "text"}
    normalized = aliases.get(normalized, normalized)
    try:
        return AssetType(normalized)
    except ValueError as exc:
        allowed = [item.value for item in AssetType]
        raise ValueError(f"asset_type must be one of {allowed}") from exc


async def _export_service():
    async with get_async_session() as session:
        yield ExportService(session)


@register_tool(
    name="get_export_dataset_stats",
    description="Read Asset Hub dataset statistics for export and curation decisions.",
    category="export",
    examples=["统计素材库数量", "查看各类型素材占比", "导出前检查数据集概况"],
    input_schema_note="No parameters. Reads current Asset Hub dataset statistics.",
    output_schema_note="Returns success and stats such as asset counts, type distribution, tag counts, and quality summary when available.",
    risk_level="read",
    output_type="export_dataset_stats",
)
async def get_export_dataset_stats() -> dict[str, Any]:
    async for service in _export_service():
        stats = await service.get_dataset_stats()
        return {"success": True, "stats": stats}
    return {"success": False, "stats": {}, "error": "export service unavailable"}


@register_tool(
    name="export_asset_dataset",
    description="Export matching Asset Hub files and metadata to a ZIP dataset.",
    category="export",
    examples=["把角色参考图导出成数据集", "导出素材库并包含血缘信息", "按类型导出图片素材"],
    input_schema_note="output_path is required. filters_json is optional JSON object string or empty. include_metadata defaults true; include_lineage defaults false.",
    output_schema_note="Returns success and export result including output path, summary, counts, or error.",
    risk_level="write",
    output_type="export_dataset_result",
)
async def export_asset_dataset(
    output_path: str,
    filters_json: str = "",
    include_metadata: bool = True,
    include_lineage: bool = False,
) -> dict[str, Any]:
    if not (output_path or "").strip():
        raise ValueError("output_path cannot be empty")
    import json

    filters = None
    if filters_json:
        try:
            filters = json.loads(filters_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"filters_json must be valid JSON: {exc}") from exc
        if not isinstance(filters, dict):
            raise ValueError("filters_json must decode to a JSON object")
    async for service in _export_service():
        result = await service.export_dataset(
            output_path=output_path.strip(),
            filters=filters,
            include_metadata=bool(include_metadata),
            include_lineage=bool(include_lineage),
        )
        return {"success": bool(result.get("success")), "data": result, "error": result.get("error", "")}
    return {"success": False, "data": {}, "error": "export service unavailable"}


@register_tool(
    name="calculate_asset_quality",
    description="Calculate a quality score for one Asset Hub node.",
    category="export",
    examples=["计算这张图的质量分", "检查视频素材质量评分", "给这个素材做质检"],
    input_schema_note="asset_id is required.",
    output_schema_note="Returns success, asset_id, quality_score, or error if asset is missing.",
    risk_level="costly",
    output_type="export_quality_score",
    cost_hint="May inspect media files and run image/video quality analysis.",
)
async def calculate_asset_quality(asset_id: str) -> dict[str, Any]:
    if not (asset_id or "").strip():
        raise ValueError("asset_id cannot be empty")
    async for service in _export_service():
        score = await service.calculate_quality_score(asset_id.strip())
        if score is None:
            return {"success": False, "asset_id": asset_id.strip(), "error": "asset not found"}
        return {"success": True, "asset_id": asset_id.strip(), "quality_score": score}
    return {"success": False, "asset_id": asset_id, "error": "export service unavailable"}


@register_tool(
    name="batch_calculate_asset_quality",
    description="Batch-calculate quality scores for selected assets or one asset type.",
    category="export",
    examples=["批量计算图片质量分", "给这些素材做质量评分", "统计视频素材质量"],
    input_schema_note="asset_ids optional list. asset_type optional image/video/audio/text/model/character. Empty inputs mean all assets.",
    output_schema_note="Returns success and batch quality stats/results from ExportService.",
    risk_level="costly",
    output_type="export_quality_batch_result",
    cost_hint="May process many files and be slow for large datasets.",
)
async def batch_calculate_asset_quality(asset_ids: list[str] | None = None, asset_type: str = "") -> dict[str, Any]:
    clean_ids = [str(item).strip() for item in (asset_ids or []) if str(item or "").strip()] or None
    async for service in _export_service():
        data = await service.batch_calculate_quality(asset_ids=clean_ids, asset_type=_asset_type(asset_type))
        return {"success": True, "data": data}
    return {"success": False, "data": {}, "error": "export service unavailable"}


@register_tool(
    name="find_duplicate_assets",
    description="Find likely duplicate assets using vector similarity.",
    category="export",
    examples=["查找重复图片", "找相似度超过 0.97 的素材对", "清理重复素材前先检测"],
    input_schema_note="asset_type optional. similarity_threshold defaults 0.95 and is clamped between 0.5 and 1.0.",
    output_schema_note="Returns success, duplicate_count, duplicates list with pair details and similarity.",
    risk_level="costly",
    output_type="export_duplicate_assets",
    cost_hint="Runs vector duplicate detection and can be expensive on large libraries.",
)
async def find_duplicate_assets(asset_type: str = "", similarity_threshold: float = 0.95) -> dict[str, Any]:
    threshold = max(0.5, min(float(similarity_threshold or 0.95), 1.0))
    async for service in _export_service():
        duplicates = await service.find_duplicates_by_vector(
            asset_type=_asset_type(asset_type),
            similarity_threshold=threshold,
        )
        return {"success": True, "duplicate_count": len(duplicates), "duplicates": duplicates}
    return {"success": False, "duplicate_count": 0, "duplicates": [], "error": "export service unavailable"}


@register_tool(
    name="merge_duplicate_assets",
    description="Merge duplicate Asset Hub nodes into a primary asset while optionally preserving references.",
    category="export",
    examples=["把这些重复素材合并到主素材", "确认后清理重复图片", "合并重复素材并保留引用"],
    input_schema_note="primary_asset_id and duplicate_asset_ids are required. keep_references defaults true.",
    output_schema_note="Returns success and merge result or error.",
    risk_level="write",
    output_type="export_duplicate_merge_result",
)
async def merge_duplicate_assets(
    primary_asset_id: str,
    duplicate_asset_ids: list[str],
    keep_references: bool = True,
) -> dict[str, Any]:
    if not (primary_asset_id or "").strip():
        raise ValueError("primary_asset_id cannot be empty")
    clean_ids = [str(item).strip() for item in (duplicate_asset_ids or []) if str(item or "").strip()]
    if not clean_ids:
        raise ValueError("duplicate_asset_ids cannot be empty")
    async for service in _export_service():
        result = await service.merge_duplicates(
            primary_asset_id=primary_asset_id.strip(),
            duplicate_asset_ids=clean_ids,
            keep_references=bool(keep_references),
        )
        if "error" in result:
            return {"success": False, "error": result["error"], "data": result}
        await service.session.commit()
        return {"success": True, "data": result}
    return {"success": False, "error": "export service unavailable", "data": {}}
