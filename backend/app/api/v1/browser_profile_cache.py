"""
采集浏览器 profile 的缓存占用与清理接口（2026-10-03）

## 背景

`backend/data/browser_profiles/<平台>/` 是**持久化 profile**，每次采集都复用
同一份磁盘目录，只增不减。实测 9 个平台合计 **1.2 GB**，其中约 98% 是
可丢弃的加速副本（HTTP 响应缓存 241MB WebP 封面 / 4.5MB gzip 的 JS bundle /
V8 Code Cache 等），真正不能碰的是 Cookies / Local Storage / IndexedDB /
Service Worker（微博采集依赖 SW 上下文）。

实现见 `app/services/browser/profile_cache.py`（含目录分类与实测数据）。

## 为什么不给「一键删光」

`Service Worker` 目录一旦删掉，**微博采集会直接失效**（实测 httpx 直连
一律 `ok=-100`，SW 负责注入复现不了的上下文）。所以本接口只删
`CACHE_DIRS` 白名单里的目录，并在响应里回传 `preserved` 说明没动什么。

## 删不掉时如实报错

profile 被浏览器占用时 Windows 会锁文件。接口**不静默吞掉**，
把失败的目录连同原因放进 `skipped` 返回 —— 假装清完了比没清更糟。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.browser.profile_cache import (
    CACHE_DIR_LABELS,
    PRESERVED_NOTE,
    ClearResult,
    clear_all_caches,
    clear_platform_cache,
    list_platform_caches,
    total_cache_bytes,
)

logger = logging.getLogger("ylcraft.api.profile_cache")

router = APIRouter()


def _mb(n: int) -> float:
    return round(n / 1048576, 1)


class PlatformCacheItem(BaseModel):
    platform: str
    cache_mb: float
    total_mb: float
    cookie_bytes: int
    cache_ratio: float = Field(description="可清理占总量的比例 0~1")
    #: 各缓存目录占用（**单位 MB，可有小数** —— 小目录只有零点几 MB，
    #: 若声明成 int 会被 pydantic 拒绝并返回 500）
    by_dir_mb: Dict[str, float] = Field(default_factory=dict)
    dir_labels: Dict[str, str] = Field(default_factory=dict)


class CacheListResponse(BaseModel):
    platforms: List[PlatformCacheItem]
    total_cache_mb: float
    total_disk_mb: float
    preserved: str = PRESERVED_NOTE
    dir_labels: Dict[str, str]


class ClearItem(BaseModel):
    platform: str
    freed_mb: float
    removed: List[str]
    skipped: Dict[str, str] = Field(default_factory=dict)
    ok: bool


class ClearResponse(BaseModel):
    results: List[ClearItem]
    total_freed_mb: float
    remaining_cache_mb: float
    preserved: str = PRESERVED_NOTE


@router.get("/caches", summary="列出各平台采集 profile 的缓存占用")
async def list_caches() -> CacheListResponse:
    """返回每个平台的缓存 / 总量 / cookie 大小。

    `cookie_bytes` 单列出来，是为了让用户看到"我们要清的是 1.2GB，
    而登录态只有几十 KB"，避免误以为要重新登录。
    """
    items = list_platform_caches()
    return CacheListResponse(
        platforms=[
            PlatformCacheItem(
                platform=i.platform,
                cache_mb=_mb(i.cache_bytes),
                total_mb=_mb(i.total_bytes),
                cookie_bytes=i.cookie_bytes,
                cache_ratio=round(i.preservable_ratio, 3),
                by_dir_mb={k: _mb(v) for k, v in i.by_dir.items() if v > 0},
                dir_labels=CACHE_DIR_LABELS,
            )
            for i in items
        ],
        total_cache_mb=_mb(total_cache_bytes()),
        total_disk_mb=_mb(sum(i.total_bytes for i in items)),
        dir_labels=CACHE_DIR_LABELS,
    )


@router.delete("/caches/{platform}", summary="清理指定平台的采集缓存")
async def clear_cache(platform: str) -> ClearResponse:
    """只删白名单里的缓存目录，**保留登录态与 Service Worker**。

    被浏览器占用导致删不掉的目录会出现在 `results[].skipped` 里，
    并附带可操作提示（先关闭采集/账号相关操作）。
    """
    try:
        r = clear_platform_cache(platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        # 磁盘/权限类问题属于服务端状况，但**必须说清楚**，不能返回空成功
        raise HTTPException(status_code=500, detail=f"清理失败：{type(e).__name__}") from e

    logger.info(
        "[api] 清理 %s 缓存：释放 %.1fMB，跳过 %s",
        r.platform, r.freed_bytes / 1048576, list(r.skipped),
    )
    return ClearResponse(
        results=[_to_item(r)],
        total_freed_mb=_mb(r.freed_bytes),
        remaining_cache_mb=_mb(r.freed_bytes_after),
    )


@router.post("/caches/clear-all", summary="清理所有平台的采集缓存")
async def clear_all() -> ClearResponse:
    """逐平台清理。**部分失败不影响其他平台**，每平台单独报告。"""
    results = clear_all_caches()
    return ClearResponse(
        results=[_to_item(r) for r in results],
        total_freed_mb=_mb(sum(r.freed_bytes for r in results)),
        remaining_cache_mb=_mb(total_cache_bytes()),
    )


def _to_item(r: ClearResult) -> ClearItem:
    return ClearItem(
        platform=r.platform,
        freed_mb=_mb(r.freed_bytes),
        removed=r.removed,
        skipped=r.skipped,
        ok=r.ok,
    )
