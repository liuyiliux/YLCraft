"""
代理池 — 代理轮换与健康检查

借鉴 connectors/mixins/auth.py 的 ProxyMixin 设计模式。
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

logger = logging.getLogger("ylcraft.proxy.pool")


class ProxyPool:
    """
    代理池

    支持多种轮换策略：
        - round_robin: 顺序轮换
        - random: 随机选择
        - failover: 使用第一个可用代理，失败后切换

    内置健康追踪（成功/失败计数）和自动剔除机制。
    """

    def __init__(self, strategy: str = "round_robin"):
        self._proxies: list[str] = []
        self._current_index: int = 0
        self._strategy = strategy
        # 健康追踪: {proxy_url: {success, fail, last_used, last_fail}}
        self._stats: dict[str, dict] = {}
        # 最大连续失败次数（超过则临时剔除）
        self._max_consecutive_fails: int = 5
        # 临时剔除冷却时间（秒）
        self._cooldown_seconds: int = 300

    # ── 池管理 ──────────────────────────────────────────────

    def set_proxies(self, proxies: list[str]) -> None:
        """替换整个代理池"""
        self._proxies = list(proxies)
        self._current_index = 0
        # 清理不在新池中的 stats
        for p in list(self._stats.keys()):
            if p not in self._proxies:
                del self._stats[p]

    def add_proxy(self, proxy: str) -> None:
        """添加代理到池"""
        if proxy and proxy not in self._proxies:
            self._proxies.append(proxy)

    def remove_proxy(self, proxy: str) -> None:
        """从池中移除代理"""
        if proxy in self._proxies:
            self._proxies.remove(proxy)
        self._stats.pop(proxy, None)

    def clear(self) -> None:
        """清空代理池"""
        self._proxies.clear()
        self._stats.clear()
        self._current_index = 0

    # ── 代理获取 ──────────────────────────────────────────────

    def get_next(self) -> Optional[str]:
        """
        获取下一个可用代理

        Returns:
            代理 URL 或 None（池为空时）
        """
        available = self._get_available_proxies()
        if not available:
            return None

        if self._strategy == "random":
            return random.choice(available)
        elif self._strategy == "failover":
            return available[0]
        else:
            # round_robin
            if self._current_index >= len(available):
                self._current_index = 0
            proxy = available[self._current_index]
            self._current_index = (self._current_index + 1) % len(available)
            return proxy

    def get_current(self) -> Optional[str]:
        """获取当前代理（不切换）"""
        available = self._get_available_proxies()
        if not available:
            return None
        idx = min(self._current_index, len(available) - 1)
        return available[idx]

    def _get_available_proxies(self) -> list[str]:
        """获取当前可用的代理（排除冷却中的）"""
        now = time.time()
        available = []
        for p in self._proxies:
            stats = self._stats.get(p, {})
            last_fail = stats.get("last_fail", 0)
            consec_fails = stats.get("consecutive_fails", 0)
            # 连续失败过多且在冷却期内 → 跳过
            if consec_fails >= self._max_consecutive_fails:
                if now - last_fail < self._cooldown_seconds:
                    continue
                else:
                    # 冷却期过，重置
                    stats["consecutive_fails"] = 0
            available.append(p)
        return available

    # ── 健康追踪 ──────────────────────────────────────────────

    def mark_success(self, proxy: str) -> None:
        """标记代理成功"""
        stats = self._ensure_stats(proxy)
        stats["success"] += 1
        stats["last_used"] = time.time()
        stats["consecutive_fails"] = 0

    def mark_fail(self, proxy: str) -> None:
        """标记代理失败"""
        stats = self._ensure_stats(proxy)
        stats["fail"] += 1
        stats["last_fail"] = time.time()
        stats["consecutive_fails"] = stats.get("consecutive_fails", 0) + 1

    def _ensure_stats(self, proxy: str) -> dict:
        if proxy not in self._stats:
            self._stats[proxy] = {
                "success": 0,
                "fail": 0,
                "consecutive_fails": 0,
                "last_used": 0.0,
                "last_fail": 0.0,
            }
        return self._stats[proxy]

    # ── 统计信息 ──────────────────────────────────────────────

    def get_stats(self) -> dict:
        """获取代理池统计"""
        total_success = sum(s.get("success", 0) for s in self._stats.values())
        total_fail = sum(s.get("fail", 0) for s in self._stats.values())
        return {
            "total": len(self._proxies),
            "available": len(self._get_available_proxies()),
            "total_success": total_success,
            "total_fail": total_fail,
            "strategy": self._strategy,
            "proxies": {
                p: {
                    **self._stats.get(p, {}),
                    "cooldown": (
                        self._stats.get(p, {}).get("consecutive_fails", 0) >= self._max_consecutive_fails
                        and time.time() - self._stats.get(p, {}).get("last_fail", 0) < self._cooldown_seconds
                    ),
                }
                for p in self._proxies
            },
        }

    @property
    def size(self) -> int:
        return len(self._proxies)

    @property
    def is_empty(self) -> bool:
        return len(self._proxies) == 0
