"""Agent tools for Asset Hub lineage inspection and relation creation."""

from __future__ import annotations

import json
from typing import Any

from app.db.database import get_async_session
from app.db.models.asset_hub import RelationType
from app.services.agent.registry import register_tool
from app.services.lineage.service import LineageService


def _parse_context(context_json: str | dict[str, Any] | None) -> dict[str, Any]:
    if context_json is None or context_json == "":
        return {}
    if isinstance(context_json, dict):
        return context_json
    try:
        parsed = json.loads(context_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"context_json must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("context_json must decode to a JSON object")
    return parsed


async def _lineage_service():
    async with get_async_session() as session:
        yield LineageService(session)


@register_tool(
    name="get_asset_lineage_graph",
    description="Read the full upstream/downstream lineage graph for an Asset Hub node.",
    category="lineage",
    examples=["查看这张分镜图从哪些参考图生成", "查这个素材的完整血缘图", "看角色立绘有哪些派生图"],
    input_schema_note="asset_id is required. max_depth defaults to 10 and is capped at 20.",
    output_schema_note="Returns success and graph data with nodes/edges when available, or error.",
    risk_level="read",
    output_type="lineage_graph",
)
async def get_asset_lineage_graph(asset_id: str, max_depth: int = 10) -> dict[str, Any]:
    if not (asset_id or "").strip():
        raise ValueError("asset_id cannot be empty")
    async for service in _lineage_service():
        data = await service.get_full_lineage(asset_id.strip(), max(1, min(int(max_depth or 10), 20)))
        return {"success": "error" not in data, "data": data, "error": data.get("error", "") if isinstance(data, dict) else ""}
    return {"success": False, "data": {}, "error": "lineage service unavailable"}


@register_tool(
    name="get_asset_upstream_lineage",
    description="Read upstream sources for an Asset Hub node, such as prompt, model, reference image, or source material.",
    category="lineage",
    examples=["查这张图用了哪些参考素材", "向上追溯素材来源", "看这个生成结果的上游 prompt 和模型"],
    input_schema_note="asset_id is required. max_depth defaults to 10 and is capped at 20.",
    output_schema_note="Returns success, total, upstream list with id/name/type/relation_type/depth.",
    risk_level="read",
    output_type="lineage_upstream",
)
async def get_asset_upstream_lineage(asset_id: str, max_depth: int = 10) -> dict[str, Any]:
    if not (asset_id or "").strip():
        raise ValueError("asset_id cannot be empty")
    async for service in _lineage_service():
        upstream = await service.get_upstream(asset_id.strip(), max(1, min(int(max_depth or 10), 20)))
        return {"success": True, "total": len(upstream), "upstream": upstream}
    return {"success": False, "total": 0, "upstream": [], "error": "lineage service unavailable"}


@register_tool(
    name="get_asset_downstream_lineage",
    description="Read downstream derived assets for an Asset Hub node, such as variants, edits, generated panels, or exported files.",
    category="lineage",
    examples=["查这个角色参考图生成过哪些图", "向下追溯素材派生物", "看这个 prompt 产出了哪些结果"],
    input_schema_note="asset_id is required. max_depth defaults to 10 and is capped at 20.",
    output_schema_note="Returns success, total, downstream list with id/name/type/relation_type/depth.",
    risk_level="read",
    output_type="lineage_downstream",
)
async def get_asset_downstream_lineage(asset_id: str, max_depth: int = 10) -> dict[str, Any]:
    if not (asset_id or "").strip():
        raise ValueError("asset_id cannot be empty")
    async for service in _lineage_service():
        downstream = await service.get_downstream(asset_id.strip(), max(1, min(int(max_depth or 10), 20)))
        return {"success": True, "total": len(downstream), "downstream": downstream}
    return {"success": False, "total": 0, "downstream": [], "error": "lineage service unavailable"}


@register_tool(
    name="get_asset_lineage_stats",
    description="Read lineage statistics for an Asset Hub node.",
    category="lineage",
    examples=["统计这个素材有多少上游和下游", "看这个角色参考图使用频率", "检查素材血缘复杂度"],
    input_schema_note="asset_id is required.",
    output_schema_note="Returns success and stats such as upstream/downstream counts, relation type distribution, and depth when available.",
    risk_level="read",
    output_type="lineage_stats",
)
async def get_asset_lineage_stats(asset_id: str) -> dict[str, Any]:
    if not (asset_id or "").strip():
        raise ValueError("asset_id cannot be empty")
    async for service in _lineage_service():
        stats = await service.get_lineage_stats(asset_id.strip())
        return {"success": True, "stats": stats}
    return {"success": False, "stats": {}, "error": "lineage service unavailable"}


@register_tool(
    name="link_asset_lineage",
    description="Create a lineage relation between two Asset Hub nodes.",
    category="lineage",
    examples=["把参考图关联到生成图", "记录这个分镜图 DERIVED_FROM 角色立绘", "给输出素材添加 REFERENCES 关系"],
    input_schema_note="source_id, target_id, and relation_type are required. relation_type must be one of DERIVED_FROM/USES/REFERENCES/CONTAINS/VARIANT_OF. context_json is optional JSON object string.",
    output_schema_note="Returns success and relation id/source_id/target_id/relation_type, or error if duplicate or invalid.",
    risk_level="write",
    output_type="lineage_relation_result",
)
async def link_asset_lineage(
    source_id: str,
    target_id: str,
    relation_type: str,
    context_json: str = "",
) -> dict[str, Any]:
    if not (source_id or "").strip():
        raise ValueError("source_id cannot be empty")
    if not (target_id or "").strip():
        raise ValueError("target_id cannot be empty")
    try:
        relation = RelationType(relation_type)
    except ValueError as exc:
        allowed = [item.value for item in RelationType]
        raise ValueError(f"relation_type must be one of {allowed}") from exc
    async for service in _lineage_service():
        item = await service.link_assets(
            source_id=source_id.strip(),
            target_id=target_id.strip(),
            relation_type=relation,
            context=_parse_context(context_json),
        )
        if not item:
            return {"success": False, "error": "relation already exists or could not be created"}
        await service.session.commit()
        return {
            "success": True,
            "relation": {
                "id": str(item.id),
                "source_id": str(item.source_id),
                "target_id": str(item.target_id),
                "relation_type": item.relation_type.value,
            },
        }
    return {"success": False, "error": "lineage service unavailable"}


@register_tool(
    name="find_asset_common_ancestor",
    description="Find a common upstream ancestor shared by two Asset Hub nodes.",
    category="lineage",
    examples=["这两张图是不是来自同一个参考图", "找两个输出的共同 prompt 或模型", "检查两个素材是否同源"],
    input_schema_note="asset_id_1 and asset_id_2 are required.",
    output_schema_note="Returns success, found, and ancestor when available.",
    risk_level="read",
    output_type="lineage_common_ancestor",
)
async def find_asset_common_ancestor(asset_id_1: str, asset_id_2: str) -> dict[str, Any]:
    if not (asset_id_1 or "").strip() or not (asset_id_2 or "").strip():
        raise ValueError("asset_id_1 and asset_id_2 cannot be empty")
    async for service in _lineage_service():
        ancestor = await service.find_common_ancestor(asset_id_1.strip(), asset_id_2.strip())
        return {"success": True, "found": bool(ancestor), "ancestor": ancestor}
    return {"success": False, "found": False, "ancestor": None, "error": "lineage service unavailable"}
