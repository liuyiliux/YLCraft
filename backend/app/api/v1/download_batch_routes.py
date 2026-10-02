"""YLCraft — 批量下载 HTTP 接口（可恢复的队列）。

## 三个端点

    POST /download/batches                 提交一批下载
    GET  /download/batches                 列出所有批次与进度
    POST /download/batches/{id}/resume     续跑（只跑没成功的）

## ⚠️ 为什么要有"续跑"而不是"重新提交"

用户提交 50 个视频，跑到第 30 个时程序崩了。重新提交会：
  · 把**已下好的 29 个再下一遍**（浪费流量和时间）
  · 覆盖已有文件（如果文件名一样）

`resume` 只跑 `pending` + `failed` 的条目 —— 这正是"批量任务
队列落盘"的意义。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.api.v1 import download_batch as store

logger = logging.getLogger("ylcraft.api.download_batch_routes")

router = APIRouter()

# ⚠️ 保留后台任务的**强引用**（2026-10-01）
#
# asyncio 的经典坑：`create_task()` 返回的 Task 如果没有强引用，
# 可能被 GC 回收，表现为"任务莫名消失、什么都没做"。
# 用一个模块级 set 持有引用，完成时自动移除。
_RUNNING_BATCHES: set = set()


class BatchItemIn(BaseModel):
    url: str
    title: str = ""


class CreateBatchRequest(BaseModel):
    items: List[BatchItemIn] = Field(default_factory=list)
    title: str = ""
    quality: str = "best"


class BatchItemOut(BaseModel):
    index: int = 0
    url: str = ""
    title: str = ""
    task_id: str = ""
    status: str = ""
    error: str = ""
    file_path: str = ""


class BatchOut(BaseModel):
    batch_id: str = ""
    title: str = ""
    quality: str = "best"
    total: int = 0
    done: int = 0
    counts: Dict[str, int] = Field(default_factory=dict)
    progress: float = 0.0
    finished: bool = False
    resumable: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
    items: List[BatchItemOut] = Field(default_factory=list)


@router.post("/batches", summary="提交批量下载")
async def create_batch(req: CreateBatchRequest):
    """提交一批下载（**立即返回**，实际下载在后台跑）。

    ## ⚠️ 不在这里等下载完成

    50 个视频可能要跑几小时 —— 同步等会超时。
    返回 `batch_id`，前端轮询 `GET /download/batches` 看进度。

    ## 条目状态会**落盘**

    所以中途重启程序，进度**不丢**；用 `POST /download/batches/{id}/resume`
    可以只跑没成功的那部分。
    """
    items = [{"url": it.url, "title": it.title} for it in req.items if it.url]
    if not items:
        raise HTTPException(
            status_code=400,
            detail="没有有效的下载项（每项都需要 url）。",
        )
    if len(items) > 500:
        raise HTTPException(
            status_code=400,
            detail=f"一次最多 500 项（收到 {len(items)} 项）—— 请分批提交。",
        )

    batch_id = store.create_batch(items, title=req.title, quality=req.quality)

    # ⚠️ 立刻**开始跑**（用独立后台协程，不等响应返回）
    #
    # 原来只创建批次、不启动 —— 用户提交后进度永远 0%，
    # 必须再手动调一次 resume 才开始（实测踩到）。
    import asyncio

    task = asyncio.create_task(_run_batch(batch_id))
    _RUNNING_BATCHES.add(task)
    task.add_done_callback(_RUNNING_BATCHES.discard)

    return {
        "success": True,
        "batch_id": batch_id,
        "total": len(items),
        "message": (
            f"已创建批次（{len(items)} 项）并**开始下载**。"
            "用 GET /download/batches 看进度。"
        ),
    }


@router.get("/batches", summary="列出批量下载批次")
async def list_batches():
    """列出所有批次与进度（**含续跑标记**）。

    ⚠️ 这个接口会**顺手修复**重启残留的 `running` 状态
    （进程已死，那个状态是假的）—— 所以调一次就能让
    `resumable` 标记变准。
    """
    batches = store.list_batches()
    return {
        "success": True,
        "data": batches,
        "message": (
            f"共 {len(batches)} 个批次"
            if batches else "还没有批量下载记录"
        ),
    }


@router.get("/batches/{batch_id}", summary="查看单个批次详情")
async def get_batch(batch_id: str):
    b = store.get_batch(batch_id)
    if not b:
        raise HTTPException(
            status_code=404,
            detail=f"找不到批次 {batch_id}（可能已被删除）。",
        )
    # 复用 list 里的"状态修复"逻辑
    for row in store.list_batches():
        if row["batch_id"] == batch_id:
            return {"success": True, "data": {**b, **row}}
    return {"success": True, "data": b}


@router.post("/batches/{batch_id}/resume", summary="续跑未完成的批量下载")
async def resume_batch(batch_id: str, background: BackgroundTasks):
    """只跑**没成功**的条目（`pending` + `failed`）。

    ## 与"重新提交"的区别

      · 重新提交 → 已下好的**再下一遍**（浪费）
      · 续跑     → 跳过 `done` / `skipped`，**只补没完成的**

    ⚠️ 没有任何待跑条目时**如实说明**，不假装"已开始"。
    """
    b = store.get_batch(batch_id)
    if not b:
        raise HTTPException(status_code=404, detail=f"找不到批次 {batch_id}。")

    pend = store.pending_items(batch_id)
    if not pend:
        return {
            "success": True,
            "batch_id": batch_id,
            "resumed": 0,
            "message": (
                "该批次**没有待跑或失败的条目**（全部已完成）。\n"
                "如需重新下载，请重新提交一个新批次。"
            ),
        }

    # ⚠️ 用 `asyncio.create_task` 而不是 `BackgroundTasks`（2026-10-01 修）
    #
    # `BackgroundTasks` 是在**响应返回之后**才执行的，而且它的生命周期
    # 绑在**那一个请求**上 —— 对于"跑几小时"的批次不合适
    # （实测：任务没有被调度，状态一直是 pending）。
    #
    # `asyncio.create_task` 让它成为**独立的后台协程**，
    # 不依赖请求生命周期，也不阻塞响应。
    #
    # ⚠️ 记得保留引用（放模块级 set），否则可能被 GC 回收 ——
    # 这是 asyncio 的经典坑（"任务莫名消失"）。
    import asyncio

    task = asyncio.create_task(_run_batch(batch_id))
    _RUNNING_BATCHES.add(task)
    task.add_done_callback(_RUNNING_BATCHES.discard)

    return {
        "success": True,
        "batch_id": batch_id,
        "resumed": len(pend),
        "message": f"已续跑 {len(pend)} 个未完成条目（已完成的会跳过）",
    }


@router.delete("/batches/{batch_id}", summary="删除批次记录")
async def delete_batch(batch_id: str, delete_files: bool = False):
    """删除批次记录。

    ⚠️ 默认**只删记录，不删文件** —— 已下好的文件是用户的成果，
    不该因为清理记录而丢失。要一并删文件需显式传 `delete_files=true`。
    """
    b = store.get_batch(batch_id)
    if not b:
        raise HTTPException(status_code=404, detail=f"找不到批次 {batch_id}。")

    deleted_files = 0
    if delete_files:
        import os

        for it in b.get("items") or []:
            fp = it.get("file_path") or ""
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                    deleted_files += 1
                except Exception as exc:
                    logger.warning("[batch] 删文件失败 %s: %s", fp, exc)

    store.delete_batch(batch_id)
    return {
        "success": True,
        "message": (
            f"已删除批次记录"
            + (f"，并删除 {deleted_files} 个文件" if delete_files else
               "（文件保留 —— 如需删文件请传 delete_files=true）")
        ),
    }


async def _run_batch(batch_id: str) -> None:
    """后台跑一个批次（**逐条**下，已完成的跳过）。

    ## ⚠️ 为什么不直接调 `create_download_task`（2026-10-01 修）

    `create_download_task` 是 **FastAPI 路由函数** —— 它的参数是
    `TaskCreateRequest` + `principal`（依赖注入的当前用户），
    直接 `await` 调用会**签名不匹配**，异常被后台任务吞掉，
    表现为"批次一直是 0% 进度"（实测踩到）。

    所以这里**直接构造 `DownloadTask` 对象**并调 `_run_download_task`
    （那才是真正的执行逻辑）—— 绕开路由层的参数校验与鉴权。

    ⚠️ 逐条串行而不是并发：
      · 各平台都有频率限制，并发容易被风控
      · 顺序执行便于"崩了之后知道跑到哪"
    """
    import asyncio

    from app.api.v1.download import DownloadTask, _run_download_task

    b = store.get_batch(batch_id) or {}
    quality = b.get("quality") or "best"
    pend = store.pending_items(batch_id)
    logger.info("[batch] %s 开始跑 %d 条", batch_id, len(pend))

    for it in pend:
        idx = it.get("index", 0)
        store.update_item(batch_id, idx, status=store.ITEM_RUNNING, error="")
        try:
            import uuid as _uuid

            tid = str(_uuid.uuid4())[:12]
            task = DownloadTask(
                task_id=tid,
                url=it.get("url") or "",
                quality=quality,
                title=it.get("title") or "",
                page_url="",
                is_audio=False,
            )
            store.update_item(batch_id, idx, task_id=tid)

            # 直接跑（不经过 HTTP 路由层）
            await _run_download_task(task)

            # 根据任务最终状态回写条目
            result = getattr(task, "status", "") or ""
            if result == "DONE":
                store.update_item(
                    batch_id, idx,
                    status=store.ITEM_DONE,
                    file_path=getattr(task, "file_path", "") or "",
                )
            else:
                store.update_item(
                    batch_id, idx,
                    status=store.ITEM_FAILED,
                    error=str(getattr(task, "error", "") or "未知错误")[:200],
                )
        except Exception as exc:
            logger.warning("[batch] %s 条目 %d 失败：%s", batch_id, idx, exc)
            store.update_item(
                batch_id, idx, status=store.ITEM_FAILED, error=str(exc)[:200],
            )
        # 条目间隔（避免风控）
        await asyncio.sleep(1)

    logger.info("[batch] %s 跑完", batch_id)
