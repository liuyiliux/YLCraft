"""Agent tools for the unified YLCraft task center."""

from __future__ import annotations

from typing import Any

from app.services.agent.registry import register_tool


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value


def _task_matches(task: dict[str, Any], *, status: str, task_type: str, keyword: str) -> bool:
    if status and status not in {"all", "*"} and task.get("status") != status:
        return False
    if task_type and task_type not in {"all", "*"} and task.get("task_type") != task_type:
        return False
    if keyword:
        haystack = " ".join(
            str(task.get(key) or "")
            for key in ("task_id", "task_type", "status", "progress_message", "error")
        ).lower()
        if keyword.lower() not in haystack:
            return False
    return True


@register_tool(
    name="list_project_tasks",
    description="列出 YLCraft 统一任务中心里的任务，帮助智能体查看下载、生图、视频、创作、字幕、剪辑等异步任务进度。",
    category="task",
    examples=["查看最近失败的任务", "列出正在运行的任务", "看看刚才生图任务有没有完成"],
    input_schema_note="status 可选 all/pending/running/done/failed/cancelled；task_type 可选 all/image/video/download/creative_project 等；keyword 可按任务 ID、进度消息、错误模糊过滤；limit 最大 100。",
    output_schema_note="返回 success、total、tasks；tasks 为摘要，包含 task_id/task_type/status/progress/progress_message/timing/error，不包含大体积 payload/result。",
    risk_level="read",
    output_type="task_list",
)
async def list_project_tasks(
    status: str = "all",
    task_type: str = "all",
    keyword: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    from app.api.v1.tasks import list_tasks

    response = await list_tasks()
    data = _to_plain(response)
    tasks = data.get("tasks") or []
    filtered = [
        task
        for task in tasks
        if _task_matches(task, status=status or "all", task_type=task_type or "all", keyword=keyword or "")
    ]
    safe_limit = max(1, min(int(limit or 50), 100))
    return {"success": True, "total": len(filtered), "tasks": filtered[:safe_limit]}


@register_tool(
    name="get_project_task",
    description="读取单个任务详情，包含 payload、result、diagnostics、events 和错误信息，适合排查异步生成或下载失败原因。",
    category="task",
    examples=["查看这个任务的完整错误", "读取刚才任务的事件日志", "检查任务 result 里有没有素材 ID"],
    input_schema_note="必须提供 task_id，可来自 list_project_tasks 或其他生成/下载工具返回值。",
    output_schema_note="返回 success、task；task 详情包含 payload/result/diagnostics/events/error，可能较大但不会修改任务状态。",
    risk_level="read",
    output_type="task_detail",
)
async def get_project_task(task_id: str) -> dict[str, Any]:
    if not (task_id or "").strip():
        raise ValueError("task_id 不能为空")
    from app.api.v1.tasks import get_task_detail

    response = await get_task_detail(task_id.strip())
    return _to_plain(response)


@register_tool(
    name="cancel_project_task",
    description="取消一个尚未完成的任务。该操作只表达取消意图；部分底层任务如果已经在执行，可能仍会自然完成。",
    category="task",
    examples=["取消这个还在运行的生图任务", "停止刚才的视频生成任务"],
    input_schema_note="必须提供 task_id；建议先调用 get_project_task 确认任务仍是 pending/running。",
    output_schema_note="返回 success、message、task；成功时任务中心会立即显示 cancelled 或取消意图。",
    risk_level="write",
    output_type="task_cancel_result",
)
async def cancel_project_task(task_id: str) -> dict[str, Any]:
    if not (task_id or "").strip():
        raise ValueError("task_id 不能为空")
    from app.api.v1.tasks import cancel_task

    response = await cancel_task(task_id.strip())
    return _to_plain(response)


@register_tool(
    name="delete_project_task",
    description="从当前任务中心视图删除任务记录。通常只用于清理已完成、失败或取消的临时任务记录。",
    category="task",
    examples=["删除这个失败任务记录", "清理已经取消的任务"],
    input_schema_note="必须提供 task_id；删除任务记录不等于删除素材或业务产物，删除前应先读取详情确认影响。",
    output_schema_note="返回 success、message、task；只移除任务中心记录，不删除素材库资产文件。",
    risk_level="delete",
    output_type="task_delete_result",
)
async def delete_project_task(task_id: str) -> dict[str, Any]:
    if not (task_id or "").strip():
        raise ValueError("task_id 不能为空")
    from app.api.v1.tasks import delete_task

    response = await delete_task(task_id.strip())
    return _to_plain(response)
