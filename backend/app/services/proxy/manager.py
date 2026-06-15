"""
代理管理器 — 代理生命周期管理

统一管理 HTTP 代理的启动、停止、恢复，供 crawler / download 等服务模块复用。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from .config import ProxyConfig
from .pool import ProxyPool

logger = logging.getLogger("ylcraft.proxy.manager")


class ProxyManager:
    """
    代理管理器

    职责：
        1. 管理全局代理配置
        2. 代理池生命周期（由 ProxyPool 负责轮换/健康）
        3. 提供 httpx 客户端工厂方法（自动注入代理）

    使用方式：
        manager = get_proxy_manager()
        manager.configure(ProxyConfig(http_proxy="http://127.0.0.1:7890"))
        client = manager.create_client()
    """

    def __init__(self):
        self._config = ProxyConfig()
        self._pool = ProxyPool()
        self._lock = threading.RLock()

    # ── 配置管理 ──────────────────────────────────────────────

    def configure(self, config: ProxyConfig) -> None:
        """
        更新代理配置

        会自动同步代理池（如果 config.pool_proxies 不为空）。
        """
        with self._lock:
            self._config = config
            if config.pool_proxies:
                self._pool.set_proxies(config.pool_proxies)
                self._pool._strategy = config.pool_strategy
            logger.info(f"[ProxyManager] 配置已更新: enabled={config.enabled}, "
                        f"proxy={config.proxy_url}, pool_size={len(config.pool_proxies)}")

    def update_config(self, **kwargs) -> None:
        """
        部分更新配置

        示例:
            manager.update_config(http_proxy="http://127.0.0.1:8080", enabled=True)
        """
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
            # 同步代理池
            if "pool_proxies" in kwargs:
                self._pool.set_proxies(kwargs["pool_proxies"])
            if "pool_strategy" in kwargs:
                self._pool._strategy = kwargs["pool_strategy"]

    @property
    def config(self) -> ProxyConfig:
        return self._config

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled and (self._config.proxy_url is not None or not self._pool.is_empty)

    # ── 代理池代理 ──────────────────────────────────────────────

    @property
    def pool(self) -> ProxyPool:
        return self._pool

    def get_proxy_url(self) -> Optional[str]:
        """
        获取当前应使用的代理 URL

        优先级：
            1. 代理池中的代理（如果配置了代理池）
            2. 配置中的 http_proxy / https_proxy
        """
        if self._config.has_pool:
            return self._pool.get_next()
        return self._config.proxy_url

    def mark_success(self, proxy_url: Optional[str] = None) -> None:
        """标记代理请求成功"""
        if proxy_url:
            self._pool.mark_success(proxy_url)

    def mark_fail(self, proxy_url: Optional[str] = None) -> None:
        """标记代理请求失败"""
        if proxy_url:
            self._pool.mark_fail(proxy_url)

    # ── 客户端工厂 ──────────────────────────────────────────────

    async def create_async_client(self, **kwargs) -> "httpx.AsyncClient":
        """
        创建带代理配置的 httpx.AsyncClient

        自动注入代理 URL 和认证信息。
        """
        import httpx

        client_kwargs = {
            "timeout": httpx.Timeout(
                connect=self._config.connect_timeout,
                read=self._config.read_timeout,
            ),
            "follow_redirects": True,
            **kwargs,
        }

        if self.is_enabled:
            proxy_url = self.get_proxy_url()
            if proxy_url:
                client_kwargs["proxy"] = proxy_url
                logger.debug(f"[ProxyManager] 使用代理: {proxy_url}")

        return httpx.AsyncClient(**client_kwargs)

    def create_sync_client(self, **kwargs) -> "httpx.Client":
        """创建带代理配置的 httpx.Client（同步版本）"""
        import httpx

        client_kwargs = {
            "timeout": httpx.Timeout(
                connect=self._config.connect_timeout,
                read=self._config.read_timeout,
            ),
            "follow_redirects": True,
            **kwargs,
        }

        if self.is_enabled:
            proxy_url = self.get_proxy_url()
            if proxy_url:
                client_kwargs["proxy"] = proxy_url

        return httpx.Client(**client_kwargs)

    # ── 代理测试 ──────────────────────────────────────────────

    async def test_proxy(self, proxy_url: Optional[str] = None, test_url: str = "https://httpbin.org/ip") -> dict:
        """
        测试代理是否可用

        Args:
            proxy_url: 要测试的代理 URL，不传则用当前配置
            test_url: 测试目标 URL

        Returns:
            { success: bool, ip: str, latency_ms: float, error: str }
        """
        import time

        proxy = proxy_url or self.get_proxy_url()
        if not proxy:
            return {"success": False, "error": "无可用代理"}

        start = time.time()
        try:
            import httpx
            async with httpx.AsyncClient(proxy=proxy, timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(test_url)
                resp.raise_for_status()
                data = resp.json()
                latency = (time.time() - start) * 1000
                self.mark_success(proxy)
                return {
                    "success": True,
                    "ip": data.get("origin", "unknown"),
                    "latency_ms": round(latency, 1),
                }
        except Exception as e:
            self.mark_fail(proxy)
            return {
                "success": False,
                "error": str(e),
                "latency_ms": round((time.time() - start) * 1000, 1),
            }

    # ── 统计信息 ──────────────────────────────────────────────

    def get_status(self) -> dict:
        """获取代理管理器当前状态"""
        return {
            "enabled": self._config.enabled,
            "proxy_url": self._config.proxy_url,
            "has_pool": self._config.has_pool,
            "pool_stats": self._pool.get_stats(),
        }


# ── 全局单例 ──────────────────────────────────────────────────

_proxy_manager: Optional[ProxyManager] = None


def get_proxy_manager() -> ProxyManager:
    """获取 ProxyManager 全局单例"""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager
