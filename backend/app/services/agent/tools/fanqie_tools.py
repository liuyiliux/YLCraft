"""Fanqie author-platform tools exposed to the Agent Center.

The tools deliberately reuse the platform connection and publishing services.
Credentials remain in ``PlatformConnection.cookie_content`` and are never
returned to the model.  A read-only preview is separate from the remote draft
write so the runtime can apply its normal confirmation policy to publishing.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.db.database import AsyncSessionLocal
from app.services.agent.registry import register_tool
from app.services.platforms.fanqie import routes as fanqie_routes
from app.services.platforms.fanqie.publish_service import FanqiePublishService


def _plain_response(value: Any) -> dict[str, Any]:
    """Normalize route responses without leaking framework-specific objects."""
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {"success": True, "data": value}


async def _read_route(call, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        async with AsyncSessionLocal() as session:
            return _plain_response(await call(*args, session=session, **kwargs))
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    except Exception as exc:  # noqa: BLE001 - convert provider failures to tool output
        return {"success": False, "error": str(exc)}


@register_tool(
    name="list_fanqie_my_books",
    description="List books available in one configured Fanqie writer connection.",
    category="fanqie",
    examples=["查看我的番茄书架", "列出这个番茄账号的作品"],
    input_schema_note="conn_id is a configured Fanqie platform connection. page starts at 1; size is 1-100.",
    output_schema_note="Returns success and the upstream Fanqie book-list data, or a normalized credential/provider error. Cookie values are never returned.",
    risk_level="read",
    output_type="fanqie_book_list",
    description_short="List books from a configured Fanqie writer connection.",
)
async def list_fanqie_my_books(conn_id: str, page: int = 1, size: int = 20) -> dict[str, Any]:
    return await _read_route(
        fanqie_routes.my_books,
        conn_id=conn_id,
        page=max(1, int(page or 1)),
        size=max(1, min(int(size or 20), 100)),
    )


@register_tool(
    name="get_fanqie_book_stats",
    description="Read available statistics for one Fanqie book through a configured connection.",
    category="fanqie",
    examples=["查看这本番茄小说的数据", "读取番茄书籍阅读统计"],
    input_schema_note="conn_id and book_id are required. stats_type defaults to 1 and is passed through to Fanqie.",
    output_schema_note="Returns success and structured upstream book statistics, or a normalized credential/provider error.",
    risk_level="read",
    output_type="fanqie_book_stats",
    description_short="Read statistics for one Fanqie book.",
)
async def get_fanqie_book_stats(conn_id: str, book_id: str, stats_type: int = 1) -> dict[str, Any]:
    return await _read_route(
        fanqie_routes.book_stats,
        book_id=book_id,
        conn_id=conn_id,
        stats_type=int(stats_type or 1),
    )


@register_tool(
    name="get_fanqie_hot_list",
    description="Read Fanqie hot-list items for writing inspiration through a configured connection.",
    category="fanqie",
    examples=["看看番茄热榜", "获取番茄热门题材作为灵感"],
    input_schema_note="conn_id is required. hot_type defaults to 0.",
    output_schema_note="Returns success and raw structured Fanqie hot-list data, or a normalized credential/provider error.",
    risk_level="read",
    output_type="fanqie_hot_list",
    description_short="Read Fanqie hot-list inspiration data.",
)
async def get_fanqie_hot_list(conn_id: str, hot_type: int = 0) -> dict[str, Any]:
    return await _read_route(
        fanqie_routes.hot_list,
        conn_id=conn_id,
        hot_type=int(hot_type or 0),
    )


@register_tool(
    name="preview_fanqie_project_publish",
    description="Validate a Creative Project chapter and Fanqie binding before publishing. This never calls Fanqie or writes a draft.",
    category="fanqie",
    examples=["预检第 3 章能否保存到番茄草稿", "检查项目番茄绑定和正文是否完整"],
    input_schema_note="project_id and content_id are required. Optional conn_id/book_id/volume_id/item_id override the saved project binding for this preview only.",
    output_schema_note="Returns ready, resolved_target, chapter metadata and explicit missing fields. It never exposes a cookie or calls the remote platform.",
    risk_level="read",
    output_type="fanqie_publish_preview",
    description_short="Validate one project chapter and its Fanqie target without publishing.",
)
async def preview_fanqie_project_publish(
    project_id: str,
    content_id: str,
    item_id: str = "",
    conn_id: str = "",
    book_id: str = "",
    volume_id: str = "",
    volume_name: str = "",
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        publisher = FanqiePublishService(session)
        preview = await publisher.preview_chapter(
            project_id=project_id,
            content_id=content_id,
            item_id=item_id,
            conn_id=conn_id,
            book_id=book_id,
            volume_id=volume_id,
            volume_name=volume_name,
        )
        return {
            "success": True,
            **preview,
            "next_action": "Call publish_fanqie_project_chapter only after the user confirms the exact target chapter.",
        }


@register_tool(
    name="get_fanqie_project_publish_status",
    description="List recorded Fanqie publishing attempts for a Creative Project without contacting Fanqie.",
    category="fanqie",
    examples=["查看这个项目保存到番茄的记录", "第 3 章番茄草稿保存成功了吗"],
    input_schema_note="project_id is required. chapter_number=0 returns all recorded chapters.",
    output_schema_note="Returns local ProjectPublishRecord entries including target ids, status, remote version and error message. No cookie is returned.",
    risk_level="read",
    output_type="fanqie_publish_status",
    description_short="Read local Fanqie publish records for a Creative Project.",
)
async def get_fanqie_project_publish_status(project_id: str, chapter_number: int = 0) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        publisher = FanqiePublishService(session)
        records = await publisher.get_publish_status(
            project_id,
            chapter_number=int(chapter_number) if chapter_number else None,
        )
        return {"success": True, "records": records, "total": len(records)}


@register_tool(
    name="publish_fanqie_project_chapter",
    description="Save one Creative Project novel_body chapter as a Fanqie draft. This writes to the remote author platform and requires user confirmation.",
    category="fanqie",
    examples=["确认后把第 3 章存为番茄草稿", "发布当前正文到指定的番茄测试章节"],
    input_schema_note="project_id, content_id and item_id are required. conn_id/book_id/volume_id may use saved project binding when omitted. Only a user-created isolated [TEST] chapter should be used during validation.",
    output_schema_note="Returns one local ProjectPublishRecord with success/failed status, remote_version and error_message. It never returns credentials and never silently retries.",
    risk_level="write",
    output_type="fanqie_publish_result",
    cost_hint="Writes the selected text to the exact Fanqie item_id as a remote draft. Verify the target with preview_fanqie_project_publish first.",
    description_short="Save one selected project chapter as a confirmed Fanqie draft.",
)
async def publish_fanqie_project_chapter(
    project_id: str,
    content_id: str,
    item_id: str,
    conn_id: str = "",
    book_id: str = "",
    volume_id: str = "",
    volume_name: str = "",
    chapter_number: int = 0,
    title: str = "",
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        publisher = FanqiePublishService(session)
        binding = await publisher.get_binding(project_id)
        target = {
            "conn_id": conn_id or binding.get("conn_id", ""),
            "book_id": book_id or binding.get("book_id", ""),
            "volume_id": volume_id or binding.get("volume_id", ""),
            "volume_name": volume_name or binding.get("volume_name", ""),
        }
        missing = [field for field, value in (("conn_id", target["conn_id"]), ("book_id", target["book_id"]), ("volume_id", target["volume_id"]), ("item_id", item_id)) if not str(value or "").strip()]
        if missing:
            return {
                "success": False,
                "error": f"Missing Fanqie target fields: {', '.join(missing)}. Configure the project binding or pass explicit values.",
            }
        try:
            record = await publisher.publish_chapter(
                project_id=project_id,
                content_id=content_id,
                item_id=item_id,
                chapter_number=int(chapter_number) if chapter_number else None,
                title=title or None,
                **target,
            )
            return {"success": True, "record": record}
        except Exception as exc:  # noqa: BLE001 - publish service persists a failed record where possible
            return {"success": False, "error": str(exc)}
