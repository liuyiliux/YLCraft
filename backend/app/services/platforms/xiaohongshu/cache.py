"""小红书搜索结果缓存。

## 为什么需要（用户实测反馈，2026-09-26）

"小红书应该加个缓存，这样切换分页再切回来时候不用重新打开浏览器查询"

问题比表面更严重。当前每次搜索的代价：
    开浏览器(2~3s) → 预热首页(6s) → 打开搜索页(5~10s) → 读卡片 → 关浏览器
单次 15~20 秒。翻一页、切回上一页、重复搜同一关键词，**每次都要重来一遍**，
用户看到的就是"又弹了个浏览器窗口"。

## 设计

两层缓存，都带 TTL：

1. **结果缓存**（按 平台+关键词+页码+每页数）
   同一页在 TTL 内直接返回，完全不碰浏览器。这是命中率最高的一层。

2. **浏览器会话缓存**（按 平台+连接）
   复用同一个浏览器上下文，省掉"开浏览器 + 预热首页"这 ~9 秒。
   翻页时特别有效：第 1 页预热过，第 2 页直接接着滚。

TTL 默认 10 分钟。小红书内容时效性不强，且翻页/切回都发生在几分钟内，
10 分钟足够覆盖真实使用；过期后重新抓，避免看到太旧的数据。

## 为什么不用 LRU 无过期

搜索结果会变（新笔记、热度变化），永久缓存会让用户以为"搜索坏了"。
带 TTL 是"够快"和"够新"之间的平衡点。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.cache")

# 结果缓存 TTL（秒）。10 分钟覆盖"翻页 / 切回"这类连续操作。
DEFAULT_TTL_SECONDS = 600

# 会话缓存空闲上限（秒）。超过就回收，不长期占着浏览器。
DEFAULT_SESSION_IDLE_SECONDS = 900


@dataclass
class _Entry:
    value: Any
    expires_at: float

    def alive(self) -> bool:
        return time.monotonic() < self.expires_at


class SearchResultCache:
    """按 key 缓存搜索结果，带 TTL。"""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._store: Dict[str, _Entry] = {}
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
    ) -> str:
        """缓存键：同一平台+连接+关键词+类型+页码+每页数 才算同一份数据。

        含 conn_id 是必须的——不同账号看到的结果不同，不能互相串。
        """
        return "|".join([
            platform,
            conn_id or "-",
            (keyword or "").strip(),
            search_type or "note",
            str(page),
            str(size),
        ])

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        if not entry.alive():
            del self._store[key]
            self.misses += 1
            logger.debug("[xhs-cache] 过期 key=%s", key)
            return None
        self.hits += 1
        logger.info("[xhs-cache] 命中 key=%s", key)
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """写入缓存。

        注意用 `is None` 而不是 `or`：`ttl=0` 是合法值（立即过期，
        常用于测试或强制刷新），用 `or` 会被悄悄换成默认 TTL。
        """
        lifetime = self._ttl if ttl is None else ttl
        self._store[key] = _Entry(value, time.monotonic() + lifetime)

    def invalidate(self, conn_id: str = "") -> int:
        """清缓存。传 conn_id 只清该连接的（重新登录后调用）。"""
        if not conn_id:
            n = len(self._store)
            self._store.clear()
            return n
        keys = [k for k in self._store if f"|{conn_id}|" in k]
        for k in keys:
            del self._store[k]
        return len(keys)

    def purge_expired(self) -> int:
        dead = [k for k, v in self._store.items() if not v.alive()]
        for k in dead:
            del self._store[k]
        return len(dead)

    def stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }


# 进程级单例（搜索是低频操作，不需要分布式缓存）
_result_cache = SearchResultCache()


def get_result_cache() -> SearchResultCache:
    return _result_cache
