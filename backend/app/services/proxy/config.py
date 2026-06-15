"""
代理配置模型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProxyConfig:
    """代理配置"""

    # 是否启用代理
    enabled: bool = False

    # HTTP 代理地址 (e.g. "http://127.0.0.1:8080")
    http_proxy: Optional[str] = None

    # HTTPS 代理地址
    https_proxy: Optional[str] = None

    # 代理绕过域名列表（不走代理的域名）
    bypass_domains: list[str] = field(default_factory=list)

    # 代理认证
    username: Optional[str] = None
    password: Optional[str] = None

    # 代理池配置
    pool_proxies: list[str] = field(default_factory=list)
    pool_strategy: str = "round_robin"  # round_robin | random | failover

    # 重试配置
    max_retries: int = 3
    retry_delay: float = 1.0

    # 超时
    connect_timeout: float = 10.0
    read_timeout: float = 30.0

    @property
    def proxy_url(self) -> Optional[str]:
        """优先返回 HTTPS 代理，其次 HTTP 代理"""
        return self.https_proxy or self.http_proxy

    @property
    def has_pool(self) -> bool:
        """是否配置了代理池"""
        return len(self.pool_proxies) > 0

    @property
    def auth_tuple(self) -> Optional[tuple[str, str]]:
        """认证信息 (username, password)"""
        if self.username and self.password:
            return (self.username, self.password)
        return None
