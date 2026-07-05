"""Agent tools for parsing media links and creating download tasks."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import HTTPException
from starlette.responses import JSONResponse

from app.services.agent.registry import register_tool


def _to_plain(value: Any) -> Any:
    if isinstance(value, JSONResponse):
        try:
            import json

            return json.loads(value.body.decode("utf-8"))
        except Exception:
            return {"raw": value.body.decode("utf-8", errors="ignore")}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value


def _summarize_parse(data: dict[str, Any]) -> dict[str, Any]:
    qualities = data.get("qualities") or []
    return {
        "success": bool(data.get("success")),
        "asset_id": data.get("asset_id") or "",
        "title": data.get("title") or "",
        "author": data.get("author") or "",
        "platform": data.get("platform") or "",
        "cover_url": data.get("cover_url") or "",
        "duration": data.get("duration") or 0,
        "duration_str": data.get("duration_str") or "",
        "resolution": data.get("resolution") or "",
        "page_url": data.get("page_url") or "",
        "audio_url_available": bool(data.get("audio_url")),
        "video_url_available": bool(data.get("video_url")),
        "quality_count": len(qualities),
        "qualities": [
            {
                "quality": item.get("quality") or "",
                "resolution": item.get("resolution") or "",
                "filesize": item.get("filesize") or "",
                "url_available": bool(item.get("url")),
            }
            for item in qualities[:20]
            if isinstance(item, dict)
        ],
        "error": data.get("error") or "",
    }


@register_tool(
    name="parse_download_link",
    description="Parse a video/article/media URL through YLCraft's download parser and return metadata, available qualities, and an optional parsed asset id without downloading the file.",
    category="download",
    examples=["解析这个抖音/B站/小红书链接", "看看这个链接能不能下载", "先解析微信公众号文章但不要下载"],
    input_schema_note="url is required. The tool visits the external URL, may use configured cookies, and returns only summarized direct URL availability rather than long signed media URLs.",
    output_schema_note="Returns success, title, author, platform, cover_url, duration, page_url, asset_id, quality_count, qualities summaries, and error.",
    risk_level="external",
    output_type="download_parse_result",
)
async def parse_download_link(url: str) -> dict[str, Any]:
    if not (url or "").strip():
        raise ValueError("url cannot be empty")
    from app.api.v1.download import ParseRequest, parse_download_url

    try:
        response = await parse_download_url(ParseRequest(url=url.strip()))
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    data = _to_plain(response)
    return _summarize_parse(data if isinstance(data, dict) else {"success": False, "error": str(data)})


@register_tool(
    name="create_download_task",
    description="Create a background download task for a parsed media link. The task writes files and can later be inspected through task/download polling tools.",
    category="download",
    examples=["确认后下载这个视频", "用 1080P 创建下载任务", "把刚解析出的 asset_id 关联到下载任务"],
    requires_progress=True,
    input_schema_note="url is required. quality/title/page_url/asset_id are optional values usually copied from parse_download_link. is_audio=true downloads audio only when supported.",
    output_schema_note="Returns success, task_id, status, message, and poll_tool. Use poll_download_task or get_project_task to inspect progress.",
    risk_level="external",
    output_type="download_task_started",
    cost_hint="This may access external sites, consume bandwidth, and write downloaded media into local storage/Asset Hub.",
)
async def create_download_task(
    url: str,
    quality: str = "best",
    title: str = "",
    page_url: str = "",
    is_audio: bool = False,
    asset_id: str = "",
) -> dict[str, Any]:
    if not (url or "").strip():
        raise ValueError("url cannot be empty")
    from app.api.v1.download import DownloadTask, _download_tasks, _run_download_task

    task_id = str(uuid.uuid4())[:12]
    task = DownloadTask(
        task_id=task_id,
        url=url.strip(),
        quality=(quality or "best").strip(),
        title=(title or "").strip() or None,
        page_url=(page_url or "").strip() or None,
        is_audio=bool(is_audio),
        asset_id=(asset_id or "").strip() or None,
    )
    _download_tasks[task_id] = task.__dict__
    asyncio.create_task(_run_download_task(task))
    return {
        "success": True,
        "task_id": task_id,
        "status": "PENDING",
        "message": "Download task created. Poll it with poll_download_task or task center tools.",
        "poll_tool": "poll_download_task",
    }


@register_tool(
    name="poll_download_task",
    description="Read the current status of a background download task created by YLCraft download tools.",
    category="download",
    examples=["查看刚才下载任务进度", "轮询这个下载 task_id", "下载失败的话读错误原因"],
    input_schema_note="task_id is required and should come from create_download_task or the download page.",
    output_schema_note="Returns success, task_id, status, progress, progress_message, result file_path/asset_id when done, error, and timestamps.",
    risk_level="read",
    output_type="download_task_status",
)
async def poll_download_task(task_id: str) -> dict[str, Any]:
    if not (task_id or "").strip():
        raise ValueError("task_id cannot be empty")
    from app.api.v1.download import get_download_task

    try:
        response = await get_download_task(task_id.strip())
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    data = _to_plain(response)
    return data if isinstance(data, dict) else {"success": False, "error": str(data)}
