"""Agent tools for EPUB generation workflows."""

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


@register_tool(
    name="create_ebook_from_folder",
    description="Generate an EPUB from a local folder containing Markdown/HTML files.",
    category="ebook",
    examples=["把下载的公众号文章目录生成 EPUB", "把小说章节文件夹打包成电子书", "根据这个文件夹创建电子书任务"],
    input_schema_note="title and folder_path are required. author/cover_path/output_dir are optional. folder_path must be an existing local directory.",
    output_schema_note="Returns task_id, status, title, chapter_count, file_path, file_size, and error. Use get_ebook_task or list_ebook_tasks for status.",
    risk_level="write",
    output_type="ebook_generation_result",
)
async def create_ebook_from_folder(
    title: str,
    folder_path: str,
    author: str = "YLCraft",
    cover_path: str = "",
    output_dir: str = "",
) -> dict[str, Any]:
    if not (title or "").strip():
        raise ValueError("title cannot be empty")
    if not (folder_path or "").strip():
        raise ValueError("folder_path cannot be empty")
    from app.api.v1.ebook import EbookGenerateRequest, generate_ebook

    try:
        response = await generate_ebook(
            EbookGenerateRequest(
                title=title.strip(),
                folder_path=folder_path.strip(),
                author=(author or "YLCraft").strip(),
                cover_path=(cover_path or "").strip(),
                output_dir=(output_dir or "").strip(),
            )
        )
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    data = _to_plain(response)
    if isinstance(data, dict):
        data.setdefault("success", not bool(data.get("error")))
    return data


@register_tool(
    name="get_ebook_task",
    description="Read one EPUB generation task status and output path.",
    category="ebook",
    examples=["查看这个 EPUB 任务是否完成", "读取电子书生成错误", "拿到 EPUB 文件路径"],
    input_schema_note="task_id is required and should come from create_ebook_from_folder or list_ebook_tasks.",
    output_schema_note="Returns success, task_id, status, title, chapter_count, file_path, file_size, and error.",
    risk_level="read",
    output_type="ebook_task_status",
)
async def get_ebook_task(task_id: str) -> dict[str, Any]:
    if not (task_id or "").strip():
        raise ValueError("task_id cannot be empty")
    from app.api.v1.ebook import get_ebook_task as api_get_ebook_task

    try:
        response = await api_get_ebook_task(task_id.strip())
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    data = _to_plain(response)
    if isinstance(data, dict):
        data.setdefault("success", not bool(data.get("error")))
    return data


@register_tool(
    name="list_ebook_tasks",
    description="List recent EPUB generation tasks maintained by the local ebook service.",
    category="ebook",
    examples=["列出电子书生成任务", "看看最近 EPUB 输出", "找失败的电子书任务"],
    input_schema_note="limit defaults to 50 and is capped at 100. Optional status filters exact task status.",
    output_schema_note="Returns success, total, tasks with task_id/status/title/chapter_count/file_path/file_size/error.",
    risk_level="read",
    output_type="ebook_task_list",
)
async def list_ebook_tasks(status: str = "all", limit: int = 50) -> dict[str, Any]:
    from app.api.v1.ebook import list_ebook_tasks as api_list_ebook_tasks

    response = await api_list_ebook_tasks()
    data = _to_plain(response)
    tasks = data.get("tasks", []) if isinstance(data, dict) else []
    if status and status not in {"all", "*"}:
        tasks = [task for task in tasks if isinstance(task, dict) and task.get("status") == status]
    safe_limit = max(1, min(int(limit or 50), 100))
    return {"success": True, "total": len(tasks), "tasks": tasks[:safe_limit]}
