"""跨平台的浏览器会话复用。

## 为什么需要（用户实测反馈，2026-09-27）

"小红书应该加个缓存，这样切换分页再切回来时候不用重新打开浏览器查询"

小红书搜索必须走浏览器（签名限制），而每次新建会话的代价很高：

    开浏览器(2~3s) → 预热首页(6s) → 打开搜索页(5~10s) → 读 → 关

实测单次 16~19 秒。翻页、切回上一页、重复搜同一关键词时，这些代价全都白付。

## 设计

按 `平台+连接` 复用同一个 BrowserContext + Page：

    · 已预热过就不再预热（省下的最大一块，~6 秒）
    · 翻页时可以直接接着往下滚，不用重新打开搜索页
    · 空闲超过 TTL 自动回收，不长期占着浏览器和内存

## 与 platforms/base.py 的关系

base.py 每次 `create_client()` 都会建新 client，但**不该建新浏览器**。
它通过 `get_session_pool()` 拿会话：有就复用，没有才新建并登记。

## 并发安全

同一个 key 的并发请求要串行化，否则两个请求会同时操作同一页面
（互相干扰导航）。用 asyncio.Lock 按 key 保护。

## 为什么不用无头

实测无头会被甩到验证码/登录页，所以复用的会话是有头浏览器。
空闲回收很重要——不然会在用户桌面留一堆窗口。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("ylcraft.platforms.session_pool")

# 空闲多久回收（秒）。用户翻页/切回都在几分钟内，15 分钟足够。
DEFAULT_IDLE_SECONDS = 900


@dataclass
class PooledSession:
    """一个被复用的浏览器会话。"""

    ctx: Any
    page: Any
    # 是否已预热过首页（预热只需一次，这是省下的主要时间）
    warmed: bool = False
    # 上一次使用时间（monotonic）
    last_used: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_used = time.monotonic()

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_used

    def alive(self) -> bool:
        """会话是否还活着（浏览器/页面没被关掉）。

        ## ⚠️ 为什么必须检查（2026-09-29 实测）

        用户关掉浏览器窗口（或进程被杀）后，会话池里**还留着那个会话**，
        下次请求仍会"复用它" → `Page.evaluate: Target page, context
        or browser has been closed` → 功能直接失败。

        实测：杀掉 chrome 后连搜两次都报这个错，而**重建会话就能恢复**。

        这里用各对象自己的 `is_closed()`（Playwright / Patchright 都有）。
        任何一项已关 → 整个会话不可用。
        检查本身不抛异常（对象可能已被 GC）。
        """
        try:
            for obj in (self.page, self.ctx):
                checker = getattr(obj, "is_closed", None)
                if callable(checker) and checker():
                    return False
            return True
        except Exception:
            # 检查过程本身报错（对象已失效）→ 当作不可用，重建更安全
            return False


class SessionPool:
    """按 key 复用浏览器会话。"""

    def __init__(self, idle_seconds: int = DEFAULT_IDLE_SECONDS):
        self._idle = idle_seconds
        self._sessions: Dict[str, PooledSession] = {}
        # 每个 key 一把锁，避免同 key 并发操作同一页面
        self._locks: Dict[str, asyncio.Lock] = {}
        self.reused = 0
        self.created = 0

    def lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def get(self, key: str) -> Optional[PooledSession]:
        """取会话。过期/**已失效**/不存在返回 None（调用方负责新建）。

        ## ⚠️ 必须检查"还活着"（2026-09-29 实测）

        用户关掉浏览器（或进程被杀）后，池里还留着那个会话，
        下次仍会复用它 → `Page.evaluate: Target page, context or
        browser has been closed` → 功能直接失败。

        实测：杀掉 chrome 后连搜两次都报这个错，**重建会话就恢复**。
        所以这里除了"空闲超时"，还要查会话是否已关闭。

        注意：只摘除，不在锁外关闭 —— 关闭由调用方在锁内做，
        避免并发重复关同一个 context。
        """
        session = self._sessions.get(key)
        if session is None:
            return None
        if session.idle_seconds() > self._idle:
            logger.info(
                "[session-pool] 空闲 %.0fs 超限，回收 key=%s",
                session.idle_seconds(), key,
            )
            del self._sessions[key]
            return None
        if not session.alive():
            # 浏览器已被关闭/进程被杀 —— 摘掉它，让调用方重建。
            # 不重建的话，用户重开浏览器后第一次操作必然失败。
            logger.info(
                "[session-pool] 会话已失效（浏览器被关闭），回收 key=%s", key
            )
            del self._sessions[key]
            return None
        session.touch()
        self.reused += 1
        return session

    def put(self, key: str, session: PooledSession) -> None:
        self._sessions[key] = session
        self.created += 1

    async def close(self, key: str) -> None:
        session = self._sessions.pop(key, None)
        if session is None:
            return
        try:
            await session.ctx.close()
        except Exception as exc:
            logger.debug("[session-pool] 关闭会话失败：%s", exc)

    async def close_all(self) -> None:
        for key in list(self._sessions):
            await self.close(key)

    def stats(self) -> Dict[str, Any]:
        return {
            "sessions": len(self._sessions),
            "keys": list(self._sessions),
            "created": self.created,
            "reused": self.reused,
            "idle_seconds": {
                k: round(v.idle_seconds(), 1) for k, v in self._sessions.items()
            },
        }


_pool = SessionPool()


def get_session_pool() -> SessionPool:
    return _pool
