"""Agent tools for platform connections and crawler source acquisition."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.services.agent.registry import register_tool


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value


def _compact_result(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("raw_data") or {}
    return {
        "id": item.get("id") or "",
        "platform": item.get("platform") or "",
        "title": item.get("title") or "",
        "desc": item.get("desc") or "",
        "cover": item.get("cover") or "",
        "url": item.get("url") or "",
        "video_url_available": bool(item.get("video_url")),
        "image_count": len(item.get("images") or []),
        "author": item.get("author") or "",
        "author_id": item.get("author_id") or "",
        "likes": item.get("likes") or 0,
        "comments": item.get("comments") or 0,
        "shares": item.get("shares") or 0,
        "create_time": item.get("create_time") or "",
        "raw_keys": sorted(raw.keys())[:30] if isinstance(raw, dict) else [],
    }


@register_tool(
    name="list_platform_source_options",
    description="List supported crawler/source platforms and search modes.",
    category="platform_source",
    examples=["列出可搜索的平台", "看看采集支持哪些平台", "获取平台搜索选项"],
    input_schema_note="No parameters. Reads local crawler configuration only.",
    output_schema_note="Returns supported platforms and crawler/search types.",
    risk_level="read",
    output_type="platform_source_options",
)
async def list_platform_source_options() -> dict[str, Any]:
    from app.api.v1.crawler import get_options

    data = await get_options()
    return _to_plain(data)


@register_tool(
    name="list_platform_connections",
    description="List configured platform connections without exposing cookies, tokens, or credentials.",
    category="platform_source",
    examples=["列出平台账号连接", "查看 B站/小红书 Cookie 配置状态", "哪些平台连接可用"],
    input_schema_note="platform optional, e.g. xhs/douyin/bilibili/wechat_mp. include_inactive controls expired/failed connections.",
    output_schema_note="Returns success, total, and connection summaries with credential booleans only.",
    risk_level="read",
    output_type="platform_connection_list",
)
async def list_platform_connections(platform: str = "", include_inactive: bool = True, limit: int = 100) -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db.models.platform_connection import PlatformConnection
    from sqlalchemy import select

    with SessionLocal() as session:
        query = select(PlatformConnection).order_by(PlatformConnection.updated_at.desc())
        rows = session.execute(query).scalars().all()
    connections = []
    for conn in rows:
        platform_value = conn.platform.value if hasattr(conn.platform, "value") else str(conn.platform)
        status_value = conn.status.value if hasattr(conn.status, "value") else str(conn.status)
        if platform and platform_value != platform:
            continue
        if not include_inactive and status_value != "active":
            continue
        connections.append(
            {
                "id": conn.id,
                "platform": platform_value,
                "name": conn.name,
                "status": status_value,
                "auth_type": conn.auth_type.value if hasattr(conn.auth_type, "value") else str(conn.auth_type),
                "account_id": conn.account_id or "",
                "account_name": conn.account_name or "",
                "has_credentials": bool(conn.credentials),
                "has_cookie_content": bool(conn.cookie_content),
                "last_used": conn.last_used.isoformat() if conn.last_used else "",
                "last_tested": conn.last_tested.isoformat() if conn.last_tested else "",
                "error_message": conn.error_message or "",
            }
        )
    safe_limit = max(1, min(int(limit or 100), 200))
    return {"success": True, "total": len(connections), "connections": connections[:safe_limit]}


@register_tool(
    name="search_platform_sources",
    description="Search external content platforms for video/image/article/user material.",
    category="platform_source",
    examples=["搜索小红书 AI短剧 分镜", "搜索 B站 角色设定 教程", "找抖音爆款短剧素材"],
    input_schema_note="platform and keyword are required. platform examples: xhs/dy/ks/bili/wb/zhihu/wechat_mp. max_results max 100.",
    output_schema_note="Returns success, total, using, message, and compact result summaries. Direct media URLs are summarized as availability flags.",
    risk_level="external",
    output_type="platform_source_search_results",
)
async def search_platform_sources(
    platform: str,
    keyword: str,
    max_results: int = 20,
) -> dict[str, Any]:
    if not (platform or "").strip():
        raise ValueError("platform cannot be empty")
    if not (keyword or "").strip():
        raise ValueError("keyword cannot be empty")
    from app.api.v1.crawler import search_materials
    from app.services.crawler import SearchRequest

    try:
        response = await search_materials(
            SearchRequest(platform=platform.strip(), keyword=keyword.strip(), max_results=max(1, min(int(max_results or 20), 100)))
        )
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail), "results": []}
    data = _to_plain(response)
    results = [_compact_result(item) for item in data.get("results", []) if isinstance(item, dict)]
    return {
        "success": bool(data.get("success", True)),
        "total": data.get("total", len(results)),
        "using": data.get("using", ""),
        "message": data.get("message", ""),
        "results": results,
    }


@register_tool(
    name="search_platform_sources_enhanced",
    description="Run enhanced platform search with search type, sort, page, and filter options.",
    category="platform_source",
    examples=["搜索 B站 user 类型", "搜索公众号全网文章", "按分页搜索小红书笔记"],
    input_schema_note="platform/keyword required. search_type defaults note. filters_json optional JSON object, e.g. {\"conn_id\":\"...\",\"fake_id\":\"...\"}. max_results max 100.",
    output_schema_note="Returns success, total, using, message, and compact result summaries.",
    risk_level="external",
    output_type="platform_source_enhanced_results",
)
async def search_platform_sources_enhanced(
    platform: str,
    keyword: str,
    search_type: str = "note",
    max_results: int = 20,
    sort_by: str = "",
    page: int = 1,
    filters_json: str = "",
) -> dict[str, Any]:
    if not (platform or "").strip():
        raise ValueError("platform cannot be empty")
    if not (keyword or "").strip():
        raise ValueError("keyword cannot be empty")
    import json
    from app.api.v1.crawler import SearchEnhancedRequest, search_enhanced

    filters = {}
    if filters_json:
        try:
            filters = json.loads(filters_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"filters_json must be valid JSON: {exc}") from exc
        if not isinstance(filters, dict):
            raise ValueError("filters_json must decode to a JSON object")
    try:
        response = await search_enhanced(
            SearchEnhancedRequest(
                platform=platform.strip(),
                keyword=keyword.strip(),
                search_type=search_type or "note",
                max_results=max(1, min(int(max_results or 20), 100)),
                sort_by=sort_by or "",
                page=max(1, int(page or 1)),
                filters=filters,
            )
        )
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail), "results": []}
    data = _to_plain(response)
    results = [_compact_result(item) for item in data.get("results", []) if isinstance(item, dict)]
    return {
        "success": bool(data.get("success", True)),
        "total": data.get("total", len(results)),
        "using": data.get("using", ""),
        "message": data.get("message", ""),
        "results": results,
    }


@register_tool(
    name="get_platform_note_detail",
    description="Fetch detailed no-watermark metadata/media for one platform note/content id when supported.",
    category="platform_source",
    examples=["获取这个小红书笔记详情", "读取抖音 note_id 的无水印资源", "查 B站内容详情"],
    input_schema_note="platform and note_id are required. conn_id optional for authenticated platforms.",
    output_schema_note="Returns success, data with title/desc/images/video/author/stats/tags/raw_data, or error.",
    risk_level="external",
    output_type="platform_source_note_detail",
)
async def get_platform_note_detail(platform: str, note_id: str, conn_id: str = "") -> dict[str, Any]:
    if not (platform or "").strip():
        raise ValueError("platform cannot be empty")
    if not (note_id or "").strip():
        raise ValueError("note_id cannot be empty")
    from app.api.v1.crawler import get_note_detail

    try:
        response = await get_note_detail(platform=platform.strip(), note_id=note_id.strip(), conn_id=conn_id or "")
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    return _to_plain(response)


@register_tool(
    name="fetch_platform_no_watermark",
    description="Batch-fetch no-watermark media resources for platform note ids.",
    category="platform_source",
    examples=["批量获取这些小红书笔记的无水印图片", "获取抖音无水印视频资源", "拉取多个 note_id 的媒体资源"],
    input_schema_note="platform and note_ids are required. note_ids max 20 per call.",
    output_schema_note="Returns success, total, message, and results with note_id/images/video/title.",
    risk_level="external",
    output_type="platform_source_no_watermark_results",
)
async def fetch_platform_no_watermark(platform: str, note_ids: list[str]) -> dict[str, Any]:
    if not (platform or "").strip():
        raise ValueError("platform cannot be empty")
    clean_ids = [str(item).strip() for item in (note_ids or []) if str(item or "").strip()][:20]
    if not clean_ids:
        raise ValueError("note_ids cannot be empty")
    from app.api.v1.crawler import FetchNoWatermarkRequest, fetch_no_watermark

    try:
        response = await fetch_no_watermark(FetchNoWatermarkRequest(platform=platform.strip(), note_ids=clean_ids))
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail), "results": []}
    return _to_plain(response)


@register_tool(
    name="import_platform_results_to_assets",
    description="Import platform crawler result objects into Asset Hub.",
    category="platform_source",
    examples=["把搜索结果导入素材库", "确认后保存这些平台素材线索", "把无水印资源入库"],
    input_schema_note="results are required and should be raw result objects from crawler/search detail, not compact summaries when possible.",
    output_schema_note="Returns success, imported_count, asset_ids, and message.",
    risk_level="write",
    output_type="platform_source_import_result",
)
async def import_platform_results_to_assets(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("results cannot be empty")
    from app.api.v1.crawler import ImportRequest, import_to_assets

    try:
        response = await import_to_assets(ImportRequest(results=results))
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail), "asset_ids": []}
    return _to_plain(response)
