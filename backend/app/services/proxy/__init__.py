"""
YLCraft — 代理公共服务层

提供统一的代理管理、代理池和抓包能力，供 crawler / download 等服务模块复用。

导出：
    get_proxy_manager()  — ProxyManager 全局单例
    get_sniffer()        — ProxySniffer 全局单例（阶段五实现）
    ProxyPool            — 代理池配置与轮换
    ProxyConfig          — 代理配置模型
"""

from __future__ import annotations

from .manager import ProxyManager, get_proxy_manager
from .pool import ProxyPool
from .config import ProxyConfig

__all__ = [
    "ProxyManager",
    "get_proxy_manager",
    "ProxyPool",
    "ProxyConfig",
]
