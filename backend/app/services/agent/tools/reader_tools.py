"""Agent tools for local readable document browsing and preview."""

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


def _summarize_reader_file(data: dict[str, Any], max_chars: int) -> dict[str, Any]:
    chapters = data.get("chapters") or []
    safe_max = max(200, min(int(max_chars or 3000), 20000))
    chapter_summaries = []
    total_chars = 0
    for chapter in chapters:
        content = chapter.get("content") or ""
        total_chars += len(content)
        chapter_summaries.append(
            {
                "id": chapter.get("id") or "",
                "title": chapter.get("title") or "",
                "content_type": chapter.get("content_type") or "html",
                "order": chapter.get("order") or 0,
                "content_length": len(content),
                "content_preview": content[:safe_max] + ("..." if len(content) > safe_max else ""),
            }
        )
    return {
        "success": bool(data.get("success", True)),
        "title": data.get("title") or "",
        "root_path": data.get("root_path") or "",
        "file_path": data.get("file_path") or "",
        "file_name": data.get("file_name") or "",
        "format": data.get("format") or "",
        "file_size": data.get("file_size") or 0,
        "modified_at": data.get("modified_at") or 0,
        "chapter_count": len(chapters),
        "total_content_length": total_chars,
        "chapters": chapter_summaries,
    }


@register_tool(
    name="browse_reader_documents",
    description="Browse readable local documents under the configured download/root directory.",
    category="reader",
    examples=["浏览下载目录里的文章", "列出这个文件夹下可阅读文档", "看看公众号下载目录有哪些 md/html 文件"],
    input_schema_note="directory can be relative to root_path or absolute within the allowed reader root. root_path is optional; defaults to configured download path.",
    output_schema_note="Returns success, root_path, current path, parent path, supported formats, and item summaries.",
    risk_level="read",
    output_type="reader_browse_result",
)
async def browse_reader_documents(directory: str = "", root_path: str = "") -> dict[str, Any]:
    from app.api.v1.reader import browse_local_documents

    try:
        response = await browse_local_documents(directory=directory or "", root_path=root_path or "")
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    return _to_plain(response)


@register_tool(
    name="read_reader_document",
    description="Read one local Markdown/HTML/text/EPUB-like document for preview, returning chapter previews rather than unbounded full content.",
    category="reader",
    examples=["读取这篇公众号文章", "预览这个小说章节文件", "打开本地 md/html 文档看看内容"],
    input_schema_note="file_path is required. root_path is optional. max_chars_per_chapter defaults to 3000 and is capped at 20000.",
    output_schema_note="Returns metadata plus chapter_count, total_content_length, and truncated chapter previews.",
    risk_level="read",
    output_type="reader_document_preview",
)
async def read_reader_document(file_path: str, root_path: str = "", max_chars_per_chapter: int = 3000) -> dict[str, Any]:
    if not (file_path or "").strip():
        raise ValueError("file_path cannot be empty")
    from app.api.v1.reader import read_local_document

    try:
        response = await read_local_document(file_path=file_path.strip(), root_path=root_path or "")
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    data = _to_plain(response)
    return _summarize_reader_file(data if isinstance(data, dict) else {}, max_chars_per_chapter)


@register_tool(
    name="read_reader_document_collection",
    description="Read multiple local documents as one collection preview, useful before EPUB generation or creative-project import.",
    category="reader",
    examples=["把这几篇文章合起来预览", "读取这个合集的前几章", "检查多个 md 文件能否组成电子书"],
    input_schema_note="file_paths is required. title/root_path optional. max_chars_per_chapter defaults to 2000 and is capped at 20000.",
    output_schema_note="Returns merged document metadata, chapter_count, total_content_length, and truncated chapter previews.",
    risk_level="read",
    output_type="reader_collection_preview",
)
async def read_reader_document_collection(
    file_paths: list[str],
    title: str = "",
    root_path: str = "",
    max_chars_per_chapter: int = 2000,
) -> dict[str, Any]:
    clean_paths = [str(item).strip() for item in (file_paths or []) if str(item or "").strip()]
    if not clean_paths:
        raise ValueError("file_paths cannot be empty")
    from app.api.v1.reader import ReaderBatchRequest, read_local_documents

    try:
        response = await read_local_documents(ReaderBatchRequest(file_paths=clean_paths, title=title or "", root_path=root_path or ""))
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    data = _to_plain(response)
    return _summarize_reader_file(data if isinstance(data, dict) else {}, max_chars_per_chapter)


@register_tool(
    name="delete_reader_document",
    description="Delete a local document or folder inside the reader root/download directory.",
    category="reader",
    examples=["删除这个下载的文章文件", "清理这个空目录", "确认后删除本地文档合集"],
    input_schema_note="path is required. root_path optional. recursive=true is required for non-empty directories.",
    output_schema_note="Returns success, deleted path, relative paths, deletion counts, freed size, and message.",
    risk_level="delete",
    output_type="reader_delete_result",
)
async def delete_reader_document(path: str, root_path: str = "", recursive: bool = False) -> dict[str, Any]:
    if not (path or "").strip():
        raise ValueError("path cannot be empty")
    from app.api.v1.reader import ReaderDeleteRequest, delete_local_document

    try:
        response = await delete_local_document(
            ReaderDeleteRequest(path=path.strip(), root_path=root_path or "", recursive=bool(recursive))
        )
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    return _to_plain(response)
