"""YLCraft — 批量下载**任务队列**（可恢复）。

## 为什么需要这个（2026-10-01 加）

原来的批量下载是**前端循环调单个接口**，且任务状态在**内存字典**里 ——
进程一重启，50 个任务下到第 30 个，**前 29 个的记录全没了**，
用户不知道哪些完成了、哪些没有。

这个模块提供：
  · **批次（batch）概念** —— 一次提交多个 URL 作为一批
  · **落盘** —— 每个条目（item）的状态写 JSON，重启可读
  · **续跑** —— `resume_batch` 只跑**未完成**的条目
  · **可查** —— `GET /download/batches` 列出所有批次与进度

## ⚠️ 设计取舍

### 为什么用 JSON 文件而不是数据库表

  · 这是**临时状态**（下载完就没用了），不值得为它加表 + 迁移
  · 下载本身是本地 IO 操作，JSON 足够（批次通常几十条）
  · 与已有的 `resume_state.json`（单文件续传）保持**同一种存储**，
    运维时只需理解一套机制

### 与 `resume_state.json` 的关系

    resume_state.json   → **单文件续传**（某个 .part 下到哪了）
    batches.json        → **批次进度**（这批里哪些条目完了）

两者互补：批次负责"还有哪些没下"，单文件负责"这个文件续到哪"。

### 条目状态

    pending   排队中
    running   正在下
    done      成功
    failed    失败（可重试）
    skipped   跳过（如重复的 URL）

⚠️ 重启后 `running` 的条目会被**重置为 pending** —— 因为进程死了，
那个"正在下"的状态是假的（实际已经中断）。
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ylcraft.api.download_batch")

_BATCHES_FILE = "batches.json"

# 本进程的启动时间（用于区分"上次进程残留的 running"和"当前真在跑的"）
#
# ## ⚠️ 为什么需要这个（2026-10-01 踩坑）
#
# 原来 `list_batches()` **每次调用**都把 `running` 重置为 `pending` ——
# 本意是修复"重启后残留的假 running"，但**无法区分两种情况**：
#
#     · 上次进程崩了留下的 running  → 该重置 ✅
#     · **当前进程正在下载**的 running → **不该重置** ❌
#
# 而前端要**轮询** `list_batches()` 看进度 —— 于是真实的"正在下载"
# 被每次轮询打回 `pending`，**进度永远显示 0%**（实测踩到，
# 查了很久才发现是"修复逻辑"自己把状态改坏了）。
#
# 修法：记下进程启动时间。只有 `started_at < 本进程启动时间` 的
# running 才是**上个进程残留**的，才重置。
_PROCESS_START = time.time()

# ⚠️ 条目状态。重启时 `running` 要重置 —— 进程死了那个状态是假的
ITEM_PENDING = "pending"
ITEM_RUNNING = "running"
ITEM_DONE = "done"
ITEM_FAILED = "failed"
ITEM_SKIPPED = "skipped"

_TERMINAL = {ITEM_DONE, ITEM_SKIPPED}


def _batches_path() -> Path:
    """批次状态文件位置（放下载目录，与 resume_state.json 同处）。"""
    from app.api.v1.download import ensure_download_path

    try:
        savedir = ensure_download_path("")
    except Exception:
        savedir = Path(__file__).resolve().parents[2] / "downloads"
    savedir.mkdir(parents=True, exist_ok=True)
    return savedir / _BATCHES_FILE


def _load() -> Dict[str, Any]:
    p = _batches_path()
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("[batch] 状态文件损坏，忽略：%s", exc)
        return {}


def _save(data: Dict[str, Any]) -> None:
    p = _batches_path()
    try:
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)      # 原子替换
    except Exception as exc:
        logger.warning("[batch] 状态写回失败：%s", exc)


def create_batch(
    items: List[Dict[str, Any]],
    *,
    title: str = "",
    quality: str = "best",
) -> str:
    """建一个批次，返回 `batch_id`。

    Args:
        items: `[{"url": ..., "title": ...}, ...]`
        title: 批次名称（便于用户识别）
        quality: 统一清晰度
    """
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    now = time.time()
    data = _load()
    data[batch_id] = {
        "batch_id": batch_id,
        "title": title or f"批量下载 {time.strftime('%m-%d %H:%M')}",
        "quality": quality,
        "created_at": now,
        "updated_at": now,
        "items": [
            {
                "index": i,
                "url": it.get("url") or "",
                "title": it.get("title") or "",
                "task_id": "",            # 跑起来后填
                "status": ITEM_PENDING,
                # ⚠️ running 的起始时刻（见 `list_batches` 的说明）
                "running_since": 0,
                "error": "",
                "file_path": "",
            }
            for i, it in enumerate(items or [])
            if (it or {}).get("url")
        ],
    }
    _save(data)
    logger.info("[batch] 创建 %s（%d 条）", batch_id, len(data[batch_id]["items"]))
    return batch_id


def get_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    return _load().get(batch_id)


def list_batches() -> List[Dict[str, Any]]:
    """列出所有批次（含进度统计）。

    ## ⚠️ 只重置**上个进程**残留的 `running`（2026-10-01 修）

    本意是修复"进程崩了但状态还写着 running" ——
    但**不能无条件重置**，否则会把**当前正在跑的**也打回 pending，
    导致进度永远 0%（实测踩过）。

    判据：`running_since < 本进程启动时间` → 是上个进程残留的，重置。
    """
    data = _load()
    changed = False
    out: List[Dict[str, Any]] = []

    for bid, b in data.items():
        items = b.get("items") or []
        for it in items:
            if it.get("status") != ITEM_RUNNING:
                continue
            # ⚠️ 只看**当前进程启动之前**就开始 run 的（那才是残留）
            since = float(it.get("running_since") or 0)
            if since and since >= _PROCESS_START:
                continue        # 本进程正在跑，别动它
            it["status"] = ITEM_PENDING
            it["error"] = "进程重启，已重置为待下载"
            it["running_since"] = 0
            changed = True

        counts: Dict[str, int] = {}
        for it in items:
            st = it.get("status") or ITEM_PENDING
            counts[st] = counts.get(st, 0) + 1

        total = len(items)
        done = counts.get(ITEM_DONE, 0) + counts.get(ITEM_SKIPPED, 0)
        out.append({
            "batch_id": bid,
            "title": b.get("title") or "",
            "quality": b.get("quality") or "best",
            "created_at": b.get("created_at") or 0,
            "updated_at": b.get("updated_at") or 0,
            "total": total,
            "done": done,
            "counts": counts,
            "progress": round(done / total * 100, 1) if total else 0.0,
            "finished": done >= total,
            # ⚠️ 有失败或待跑的就能续
            "resumable": any(
                it.get("status") in (ITEM_PENDING, ITEM_FAILED) for it in items
            ),
        })

    if changed:
        _save(data)

    out.sort(key=lambda x: -(x.get("updated_at") or 0))
    return out


def update_item(
    batch_id: str,
    index: int,
    *,
    status: Optional[str] = None,
    task_id: Optional[str] = None,
    error: Optional[str] = None,
    file_path: Optional[str] = None,
) -> None:
    """更新某个条目的状态（下载过程中调用）。"""
    data = _load()
    b = data.get(batch_id)
    if not b:
        return
    for it in b.get("items") or []:
        if it.get("index") == index:
            if status is not None:
                it["status"] = status
                # ⚠️ 记下"从什么时候开始 running"——
                # `list_batches` 靠它区分"本进程在跑"还是"上个进程残留"
                it["running_since"] = time.time() if status == ITEM_RUNNING else 0
            if task_id is not None:
                it["task_id"] = task_id
            if error is not None:
                it["error"] = error
            if file_path is not None:
                it["file_path"] = file_path
            break
    b["updated_at"] = time.time()
    _save(data)


def pending_items(batch_id: str) -> List[Dict[str, Any]]:
    """该批次里**还没成功**的条目（`resume_batch` 用）。

    ⚠️ 包含 `failed`（失败的要重试）和 `pending`（没跑的），
    **不包含** `done` / `skipped` —— 那些不该重下。
    """
    b = _load().get(batch_id)
    if not b:
        return []
    return [
        it for it in (b.get("items") or [])
        if it.get("status") in (ITEM_PENDING, ITEM_FAILED)
    ]


def delete_batch(batch_id: str) -> bool:
    data = _load()
    if batch_id in data:
        del data[batch_id]
        _save(data)
        return True
    return False
