"""AI 操作的任务记录封装（任务中心可见性）。

事件日志已经由 ``AIService`` 三个入口统一收口（见 ``services/ai/service.py``）；
**任务记录不能同样自动收口**——chat 之类高频调用若自动建任务会把任务中心冲垮，
且任务需要业务粒度（一个"地图成图"算一条，而不是每次模型调用一条）。

所以这里提供显式但省事的封装：一个 async 上下文把
「建任务 → 记开始 → 完成或失败 → 进度与诊断」一次做完，
避免各端点自己拼这套流程时漏写（此前地图生图就是整段漏掉）。

用法：

    async with ai_task("world_map_visual", project_id=pid, title="地图视觉成图") as task:
        result = await generate_map_visual(...)
        task["result"] = {"url": result["url"]}
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

logger = logging.getLogger("ylcraft.ai.tracking")


@asynccontextmanager
async def ai_task(
    task_type: str,
    *,
    project_id: str | None = None,
    title: str = "",
    payload: dict[str, Any] | None = None,
    queue: Any | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """把一段 AI 操作包成任务中心里可见的一条任务。

    Args:
        task_type: 任务类型。需命中 ``task_persistence.PERSISTED_TASK_TYPES``
            且 payload 带 ``project_id`` 才会落库，否则只存内存（重启即失）。
        project_id: 关联项目，决定任务能否持久化与出现在项目视图。
        title: 任务中心展示的标题。
        payload: 额外负载，与 ``project_id`` / ``title`` 合并。
        queue: 任务队列，缺省取全局单例（测试可注入）。

    Yields:
        任务句柄字典：``{"task_id", "queue", "result"}``。
        往 ``result`` 里塞的内容会写进任务的 result 字段。

    Raises:
        原样抛出被包裹代码的异常（先落失败状态再抛）。
    """
    from app.core.task_queue import TaskStatus, get_task_queue

    real_queue = queue or get_task_queue()
    merged: dict[str, Any] = dict(payload or {})
    if project_id:
        merged.setdefault("project_id", project_id)
    if title:
        merged.setdefault("title", title)

    task = await real_queue.create_task(task_type=task_type, payload=merged)
    handle: dict[str, Any] = {"task_id": task.task_id, "queue": real_queue, "result": {}}
    started = time.perf_counter()

    async def _safe(coro) -> None:
        """任务记账失败不能影响业务本身。"""
        try:
            await coro
        except Exception:  # pragma: no cover - best-effort
            logger.debug("[ai_task] 任务记账失败（已忽略）", exc_info=True)

    await _safe(real_queue.append_event(task.task_id, "start", title or f"{task_type} 开始"))
    await _safe(real_queue.update_progress(task.task_id, 5, title or "开始"))

    failed: BaseException | None = None
    try:
        yield handle
    except BaseException as exc:  # noqa: BLE001 - 记完失败再原样抛出
        failed = exc
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        task.progress = 100
        task.completed_at = time.time()
        task.result = dict(handle.get("result") or {})
        if failed is not None:
            task.status = TaskStatus.FAILED
            task.error = str(failed)
            await _safe(
                real_queue.append_event(
                    task.task_id, "error", str(failed), level="error"
                )
            )
        else:
            task.status = TaskStatus.DONE
            task.error = None
            await _safe(real_queue.append_event(task.task_id, "done", title or "完成"))
        # 诊断信息：任务详情里能看到耗时与结果摘要，便于定位慢调用。
        try:
            real_queue_update = getattr(real_queue, "update_diagnostics", None)
            if callable(real_queue_update):
                await _safe(
                    real_queue_update(
                        task.task_id,
                        {
                            "duration_ms": duration_ms,
                            "failed": failed is not None,
                            "result_keys": sorted((handle.get("result") or {}).keys()),
                        },
                    )
                )
        except Exception:  # pragma: no cover
            pass
        await _safe(real_queue.update_task(task))
