"""Agent tools for novel sources, bookshelf records, and chapter previews."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db.database import SessionLocal
from app.services.agent.registry import register_tool
from app.services.novel.book_source_manager import BookSourceManager


def _truncate(value: str | None, limit: int = 800) -> str:
    text_value = value or ""
    if len(text_value) <= limit:
        return text_value
    return f"{text_value[:limit]}... (truncated, len={len(text_value)})"


def _book_source_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("source_id") or "",
        "name": item.get("book_source_name") or item.get("name") or "",
        "url": item.get("book_source_url") or item.get("url") or "",
        "group": item.get("book_source_group") or "",
        "enabled": bool(item.get("enabled_by_user", True)),
        "is_js_source": bool(item.get("is_js_source")),
        "has_search_rule": bool(item.get("has_search_rule") or item.get("rule_search") or item.get("ruleSearch")),
        "has_toc_rule": bool(item.get("has_toc_rule") or item.get("rule_toc") or item.get("ruleToc")),
        "has_content_rule": bool(item.get("has_content_rule") or item.get("rule_content") or item.get("ruleContent")),
    }


def _novel_asset_summary(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
    return {
        "asset_id": str(row.get("id") or ""),
        "title": row.get("name") or metadata.get("novel_title") or "",
        "author": metadata.get("author") or "",
        "status": metadata.get("status") or "",
        "source_type": metadata.get("source_type") or metadata.get("source") or "",
        "source_name": metadata.get("source_name") or metadata.get("source_site") or "",
        "book_url": metadata.get("book_url") or metadata.get("source_url") or "",
        "chapter_count": metadata.get("chapter_count") or len(metadata.get("chapters") or []),
        "downloaded_chapter_indices": metadata.get("downloaded_chapter_indices") or metadata.get("downloaded_chapters") or [],
        "content_path": metadata.get("content_path") or "",
        "updated_at": str(row.get("updated_at") or ""),
    }


@register_tool(
    name="list_novel_sources",
    description="列出小说书源配置，供智能体判断哪些书源可用于搜索、目录和章节正文抓取。",
    category="novel",
    examples=["列出可用小说书源", "看看哪些书源启用了", "检查书源有没有目录和正文规则"],
    input_schema_note="enabled_only 默认 true；limit 最大 200。只读取本地书源配置，不访问外部网站。",
    output_schema_note="返回 success、total、sources；sources 包含 id/name/url/group/enabled/is_js_source/规则能力摘要。",
    risk_level="read",
    output_type="novel_source_list",
)
async def list_novel_sources(enabled_only: bool = True, limit: int = 100) -> dict[str, Any]:
    with SessionLocal() as session:
        manager = BookSourceManager(session)
        sources = manager.list_sources(enabled_only=enabled_only)
        safe_limit = max(1, min(int(limit or 100), 200))
        summaries = [_book_source_summary(item) for item in sources[:safe_limit]]
        return {"success": True, "total": len(sources), "sources": summaries}


@register_tool(
    name="list_novel_bookshelf",
    description="列出本地 Asset Hub 中的小说书架/下载记录，供智能体选择小说素材继续拆章、改写或导入创作项目。",
    category="novel",
    examples=["列出本地小说书架", "找已经下载的小说", "看看有哪些小说可以拆成短剧脚本"],
    input_schema_note="keyword 可按标题、作者、书源模糊过滤；status 可传 all/bookshelf/partial/ready；limit 最大 100。",
    output_schema_note="返回 success、total、books；books 包含 asset_id/title/author/status/source/chapter_count/downloaded_chapter_indices/content_path。",
    risk_level="read",
    output_type="novel_bookshelf_list",
)
async def list_novel_bookshelf(keyword: str = "", status: str = "all", limit: int = 50) -> dict[str, Any]:
    with SessionLocal() as session:
        rows = (
            session.execute(
                text(
                    """
                    SELECT id, name, metadata_json, updated_at
                    FROM asset_nodes
                    WHERE asset_type = 'TEXT'
                      AND COALESCE(metadata_json ->> 'status', '') <> 'DELETED'
                      AND COALESCE(metadata_json ->> 'source_type', metadata_json ->> 'source', '') IN ('novel', 'novel_bookshelf', 'novel_download')
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 50), 100))},
            )
            .mappings()
            .all()
        )
        books = [_novel_asset_summary(dict(row)) for row in rows]
        needle = (keyword or "").strip().lower()
        if needle:
            books = [
                item
                for item in books
                if needle in item["title"].lower()
                or needle in item["author"].lower()
                or needle in item["source_name"].lower()
            ]
        if status and status not in {"all", "*"}:
            books = [item for item in books if item["status"] == status]
        return {"success": True, "total": len(books), "books": books}


@register_tool(
    name="search_novel_sources",
    description="跨已启用小说书源搜索书籍。该工具会访问外部书源站点，适合用户确认后查找小说素材。",
    category="novel",
    examples=["搜索这本小说有哪些书源", "帮我找短剧改编小说素材", "跨书源搜索 MIRD"],
    input_schema_note="必须提供 keyword；max_concurrent 建议 3-10；limit 最大 50。会访问外部网站，可能受书源质量、Cookie 和反爬影响。",
    output_schema_note="返回 success、total、results；results 包含 title/author/url/cover/source_site/source_id。",
    risk_level="external",
    output_type="novel_search_results",
)
async def search_novel_sources(keyword: str, max_concurrent: int = 5, limit: int = 20) -> dict[str, Any]:
    if not (keyword or "").strip():
        raise ValueError("keyword 不能为空")
    with SessionLocal() as session:
        manager = BookSourceManager(session)
        results = await manager.search_all_sources(keyword.strip(), max_concurrent=max(1, min(int(max_concurrent or 5), 10)))
        safe_limit = max(1, min(int(limit or 20), 50))
        return {"success": True, "total": len(results), "results": results[:safe_limit]}


@register_tool(
    name="get_novel_catalog",
    description="读取一本小说在指定书源下的目录章节列表。该工具会访问外部书源站点。",
    category="novel",
    examples=["读取这本小说目录", "查看这个书源下有多少章", "拿到前 20 章标题"],
    input_schema_note="必须提供 book_url；source_id 可选但建议提供；limit 最大 500；offset 从 0 开始。",
    output_schema_note="返回 success、total、chapters；chapters 包含 index/title/url，默认只返回分页片段。",
    risk_level="external",
    output_type="novel_catalog",
)
async def get_novel_catalog(
    book_url: str,
    source_id: str = "",
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    if not (book_url or "").strip():
        raise ValueError("book_url 不能为空")
    with SessionLocal() as session:
        manager = BookSourceManager(session)
        source = manager.get_source(source_id) if source_id else None
        if not source:
            for item in manager.sources:
                if item.bookSourceUrl and book_url.startswith(item.bookSourceUrl.rstrip("/")):
                    source = item
                    break
        if not source:
            source = next((item for item in manager.sources if item.enabled_by_user), None)
        if not source:
            return {"success": False, "message": "没有可用书源", "chapters": [], "total": 0}
        chapters = await manager.get_chapter_list(source, book_url.strip())
        normalized = [
            {"index": idx, "title": chapter.get("title") or chapter.get("name", ""), "url": chapter.get("url", "")}
            for idx, chapter in enumerate(chapters, 1)
        ]
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 100), 500))
        return {
            "success": True,
            "source_id": getattr(source, "source_id", ""),
            "source_name": getattr(source, "bookSourceName", ""),
            "total": len(normalized),
            "chapters": normalized[safe_offset : safe_offset + safe_limit],
        }


@register_tool(
    name="preview_novel_chapter",
    description="读取指定小说章节正文并返回截断预览，适合智能体判断小说语气、剧情和可改编价值。该工具会访问外部书源站点。",
    category="novel",
    examples=["预览第一章正文", "读取这个章节看看能不能改短剧", "给我看章节前 2000 字"],
    input_schema_note="必须提供 chapter_url；source_id 或 book_url 至少建议提供一个用于匹配书源；max_chars 最大 8000。",
    output_schema_note="返回 success、source_name、content_preview、content_length；默认只返回预览，避免把整章塞进上下文。",
    risk_level="external",
    output_type="novel_chapter_preview",
)
async def preview_novel_chapter(
    chapter_url: str,
    source_id: str = "",
    book_url: str = "",
    max_chars: int = 2000,
) -> dict[str, Any]:
    if not (chapter_url or "").strip():
        raise ValueError("chapter_url 不能为空")
    with SessionLocal() as session:
        manager = BookSourceManager(session)
        source = manager.get_source(source_id) if source_id else None
        if not source and book_url:
            for item in manager.sources:
                if item.bookSourceUrl and book_url.startswith(item.bookSourceUrl.rstrip("/")):
                    source = item
                    break
        if not source:
            source = next((item for item in manager.sources if item.enabled_by_user), None)
        if not source:
            return {"success": False, "message": "没有可用书源", "content_preview": "", "content_length": 0}
        content = await manager.get_chapter_content(source, chapter_url.strip())
        if content is None:
            return {
                "success": False,
                "message": "无法获取章节内容，请检查书源规则、Cookie 或章节 URL",
                "source_name": getattr(source, "bookSourceName", ""),
                "content_preview": "",
                "content_length": 0,
            }
        safe_limit = max(200, min(int(max_chars or 2000), 8000))
        return {
            "success": True,
            "source_id": getattr(source, "source_id", ""),
            "source_name": getattr(source, "bookSourceName", ""),
            "content_preview": _truncate(content, safe_limit),
            "content_length": len(content),
        }
