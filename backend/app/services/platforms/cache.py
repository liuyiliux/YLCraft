"""YLCraft — 搜索结果通用缓存（跨平台）

## 为什么需要

用户反馈："切换分页再切回来时候不用重新查询"。

实测各平台单次搜索耗时：

    B站      ~2s
    小红书   ~2s（纯 HTTP）
    抖音     ~4s
    X        ~15s   ← 最痛
    微博     ~21s   ← 最痛（要开浏览器）

**翻页 / 切回上一页 / 重复搜同一关键词**每次都重跑一遍。
微博和 X 尤其明显 —— 用户"只是想回去看看上一页"，要等 20 秒。

## 与 `xiaohongshu/cache.py` 的关系

那个是小红书专用（历史遗留，只在旧的 patchright 路径用）。
**本模块是通用版**，被所有平台的 api 路径使用。
小红书那个保留不删（避免破坏既有调用面），但新代码用这个。

## 设计

  · **带 TTL**（默认 5 分钟）—— 搜索结果会变，永久缓存会让用户
    以为"搜索坏了"（看到几天前的结果）。
  · **key 含 conn_id** —— 不同账号看到的结果不同，绝不能互相串。
  · **只缓存非空结果** —— 空结果可能是限流/风控导致的，
    缓存它会让"稍后重试"也拿不到数据。
  · **进程内单例** —— 搜索是低频操作，不需要 Redis。

TTL 选 5 分钟（比小红书原来的 10 分钟短）：覆盖"翻页/切回"这类
连续操作足够，又能更快反映内容变化。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("ylcraft.platforms.cache")

# 结果缓存 TTL（秒）。5 分钟覆盖"翻页 / 切回"这类连续操作。
DEFAULT_TTL_SECONDS = 300

# 最多缓存多少条 —— 防止长时间运行后无限增长
MAX_ENTRIES = 500


@dataclass
class _Entry:
    value: Any
    expires_at: float

    def alive(self) -> bool:
        return time.monotonic() < self.expires_at


class SearchCache:
    """按 key 缓存搜索结果（带 TTL + 容量上限）。"""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS,
                 max_entries: int = MAX_ENTRIES):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: Dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(
        platform: str,
        keyword: str,
        page: int,
        size: int,
        search_type: str = "",
        conn_id: str = "",
        sort_by: str = "",
        extra: str = "",
    ) -> str:
        """缓存键。

        ⚠️ **必须含 `conn_id`** —— 不同账号的搜索结果不同，
        串了会把 A 账号的结果给 B 账号看。

        ⚠️ 也要含 `sort_by` —— 综合排序和最新排序是不同的结果集。

        ⚠️ `extra` 用于**游标翻页**（2026-10-03 加）——
        `dialogs`（我的频道）/ `saved`（我的收藏）不用页码翻页，
        而是用 MTProto 游标 `offset_id`（语义："取比它更旧的"）。
        游标不同 = 不同的结果集，**必须**进键 ——
        否则"首次"和"带游标的下一页"算出同一个键，
        实测两页返回**完全一样的 10 条**（假翻页）。
        """
        return "|".join([
            platform,
            conn_id or "-",
            (keyword or "").strip(),
            search_type or "note",
            (sort_by or "").strip(),
            str(page),
            str(size),
            (extra or "").strip(),
        ])

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            if not entry.alive():
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
        logger.info("[cache] 命中 key=%s", key)
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """写入缓存。

        ⚠️ **不要缓存空结果** —— 空可能是限流/风控导致的，
        缓存它会让"稍后重试"也拿不到数据（调用方负责判断）。

        注意用 `is None` 而不是 `or`：`ttl=0` 是合法值
        （立即过期，常用于测试或强制刷新）。
        """
        lifetime = self._ttl if ttl is None else ttl
        with self._lock:
            # 容量满了先清过期的，再不行就清最早的
            if len(self._store) >= self._max:
                dead = [k for k, v in self._store.items() if not v.alive()]
                for k in dead:
                    del self._store[k]
                if len(self._store) >= self._max:
                    # 仍满：丢掉最早过期的一批
                    oldest = sorted(
                        self._store.items(), key=lambda kv: kv[1].expires_at
                    )[: max(1, self._max // 10)]
                    for k, _ in oldest:
                        del self._store[k]
            self._store[key] = _Entry(value, time.monotonic() + lifetime)

    def invalidate(self, conn_id: str = "", platform: str = "") -> int:
        """清缓存。传 conn_id / platform 只清匹配的（重新登录后调用）。

        重新登录后登录态变了，旧结果可能已经不对（比如私密内容可见性变化），
        所以要能定向清理。
        """
        with self._lock:
            if not conn_id and not platform:
                n = len(self._store)
                self._store.clear()
                return n
            keys = []
            for k in self._store:
                parts = k.split("|")
                if conn_id and parts[1] != conn_id:
                    continue
                if platform and parts[0] != platform:
                    continue
                keys.append(k)
            for k in keys:
                del self._store[k]
            return len(keys)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
                "ttl_seconds": self._ttl,
            }


# 进程级单例（搜索是低频操作，不需要分布式缓存）
_cache = SearchCache()


def get_search_cache() -> SearchCache:
    return _cache
