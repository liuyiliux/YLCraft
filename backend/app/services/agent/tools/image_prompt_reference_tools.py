"""Agent tools for the image prompt reference library."""

from __future__ import annotations

from typing import Any

from app.db.database import SessionLocal
from app.services.agent.registry import register_tool
from app.services.image_prompt_reference import ImagePromptReferenceService


@register_tool(
    name="list_image_prompt_sources",
    description="List configured third-party image prompt reference sources.",
    category="image_prompt_reference",
    examples=["列出生图提示词参考库来源", "有哪些 GitHub 提示词集合可用"],
    input_schema_note="include_disabled defaults to false.",
    output_schema_note="Returns success, total and configured sources with sync status.",
    risk_level="read",
    output_type="image_prompt_source_list",
    description_short="List image prompt reference sources.",
)
async def list_image_prompt_sources(include_disabled: bool = False) -> dict[str, Any]:
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        sources = service.list_sources(include_disabled=include_disabled)
        return {
            "success": True,
            "total": len(sources),
            "sources": [service.source_to_dict(source) for source in sources],
        }


@register_tool(
    name="search_image_prompt_references",
    description="Search image prompt examples by keyword, tag, category or source.",
    category="image_prompt_reference",
    examples=["找一些赛博朋克生图提示词", "搜索需要参考图的人像提示词"],
    input_schema_note="keyword/tag/category/source_id are optional. page_size defaults to 10 and maxes at 50.",
    output_schema_note="Returns success, total, items, tags and categories.",
    risk_level="read",
    output_type="image_prompt_reference_search_result",
    description_short="Search image prompt examples.",
)
async def search_image_prompt_references(
    keyword: str = "",
    tag: str = "",
    category: str = "",
    source_id: str = "",
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        return service.search_references(
            keyword=keyword,
            tag=tag,
            category=category,
            source_id=source_id,
            page=page,
            page_size=min(max(int(page_size or 10), 1), 50),
        )


@register_tool(
    name="get_image_prompt_reference",
    description="Read one full image prompt reference by id.",
    category="image_prompt_reference",
    examples=["查看这个提示词参考详情", "读取某个生图 prompt 案例"],
    input_schema_note="reference_id is required.",
    output_schema_note="Returns success and the full reference detail.",
    risk_level="read",
    output_type="image_prompt_reference_detail",
    description_short="Read one image prompt reference.",
)
async def get_image_prompt_reference(reference_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        reference = service.get_reference(reference_id)
        if not reference:
            return {"success": False, "error": "image prompt reference not found", "reference_id": reference_id}
        return {"success": True, "reference": service.reference_to_dict(reference)}


@register_tool(
    name="refresh_image_prompt_sources",
    description="Refresh image prompt reference sources from configured remote repositories.",
    category="image_prompt_reference",
    examples=["刷新生图提示词参考库", "同步某个 GitHub prompt 来源"],
    input_schema_note="source_id is optional. Empty source_id refreshes all enabled sources.",
    output_schema_note="Returns per-source sync results and errors.",
    risk_level="write",
    output_type="image_prompt_source_refresh_result",
    description_short="Refresh image prompt reference sources.",
)
async def refresh_image_prompt_sources(source_id: str = "") -> dict[str, Any]:
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        return service.refresh_sources(source_id=source_id or None)


@register_tool(
    name="save_image_prompt_reference_as_asset",
    description="Save one selected image prompt reference as an explicit Asset Hub text asset.",
    category="image_prompt_reference",
    examples=["把这个提示词保存成素材", "保存这个 prompt 案例到素材库"],
    input_schema_note="reference_id is required. This is explicit; synced references are not imported automatically.",
    output_schema_note="Returns created asset_node_id and asset_version_id.",
    risk_level="write",
    output_type="image_prompt_reference_asset_result",
    description_short="Save selected prompt reference as a text asset.",
)
async def save_image_prompt_reference_as_asset(reference_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        return service.save_reference_as_asset(reference_id)
