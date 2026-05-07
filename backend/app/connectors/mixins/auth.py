"""
YLCraft — 认证 Mixin

参考 MediaCrawler 的 ProxyRefreshMixin 设计模式，
提供跨平台复用的认证功能。
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Callable
from abc import ABC, abstractmethod

logger = logging.getLogger("ylcraft.connectors.mixins")


class AuthMixin(ABC):
    """
    认证 Mixin

    提供通用的认证功能，所有连接器可继承此 Mixin：
    - Cookie 管理
    - OAuth2 流程（参考 Mixpost/Postiz 实现）
    - Token 刷新
    - 会话保持
    """

    def __init__(self):
        self._credentials: dict = {}
        self._auth_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None
        self._session_id: Optional[str] = None
        self._oauth_tokens: dict = {}  # 存储完整的 OAuth token 信息

    # -------------------------------------------------------------------------
    # 凭证管理
    # -------------------------------------------------------------------------

    def set_credentials(self, credentials: dict):
        """设置凭证数据"""
        self._credentials = credentials
        self._extract_auth_info()

    def get_credentials(self) -> dict:
        """获取凭证数据"""
        return self._credentials

    def _extract_auth_info(self):
        """从凭证中提取认证信息（子类可覆盖）"""
        self._auth_token = self._credentials.get("access_token") or self._credentials.get("token")
        self._token_expires_at = self._credentials.get("expires_at")
        # 提取完整的 OAuth token 信息
        self._oauth_tokens = {
            "access_token": self._credentials.get("access_token"),
            "refresh_token": self._credentials.get("refresh_token"),
            "expires_at": self._credentials.get("expires_at"),
            "token_type": self._credentials.get("token_type", "Bearer"),
        }

    def has_valid_credentials(self) -> bool:
        """检查是否有有效凭证"""
        if not self._credentials:
            return False

        # 检查是否有过期时间
        if self._token_expires_at:
            import time
            if time.time() > self._token_expires_at:
                return False

        return True

    # -------------------------------------------------------------------------
    # OAuth 2.0 辅助方法（参考 Postiz/Mixpost 实现）
    # -------------------------------------------------------------------------

    def get_oauth_tokens(self) -> dict:
        """获取 OAuth token 信息"""
        return self._oauth_tokens

    def update_oauth_tokens(self, token_info: dict):
        """
        更新 OAuth token 信息

        Args:
            token_info: 包含 token 信息的字典
                        {
                            "access_token": "...",
                            "refresh_token": "...",
                            "expires_in": 3600,
                            "token_type": "Bearer"
                        }
        """
        import time

        self._oauth_tokens.update(token_info)

        # 更新内部状态
        self._auth_token = token_info.get("access_token", self._auth_token)
        self._token_expires_at = token_info.get("expires_at", time.time() + token_info.get("expires_in", 3600))

        # 同步到凭证
        if "access_token" in token_info:
            self._credentials["access_token"] = token_info["access_token"]
        if "refresh_token" in token_info:
            self._credentials["refresh_token"] = token_info["refresh_token"]
        if "expires_at" in token_info:
            self._credentials["expires_at"] = token_info["expires_at"]

    def is_oauth_token_expired(self) -> bool:
        """检查 OAuth token 是否过期"""
        if not self._auth_token:
            return True

        if self._token_expires_at:
            import time
            return time.time() >= self._token_expires_at

        return False

    def get_auth_headers(self) -> dict:
        """
        获取认证请求头
        参考 Postiz 的认证头生成
        """
        if self._auth_token:
            token_type = self._oauth_tokens.get("token_type", "Bearer")
            return {
                "Authorization": f"{token_type} {self._auth_token}",
                "Accept": "application/json",
            }
        return {}

    @staticmethod
    def parse_oauth_callback(url: str) -> dict:
        """
        解析 OAuth 回调 URL

        Args:
            url: 回调 URL（包含 code、state 等参数）

        Returns:
            解析后的参数字典
        """
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return {k: v[0] if len(v) == 1 else v for k, v in params.items()}

    # -------------------------------------------------------------------------
    # 会话管理
    # -------------------------------------------------------------------------

    def set_session_id(self, session_id: str):
        """设置会话 ID"""
        self._session_id = session_id

    def get_session_id(self) -> Optional[str]:
        """获取会话 ID"""
        return self._session_id

    async def refresh_session(self) -> bool:
        """
        刷新会话
        子类可覆盖以实现特定刷新逻辑
        """
        return True


class CookieManagerMixin:
    """
    Cookie 管理 Mixin

    提供 Cookie 的加载、保存、刷新功能。
    类似于 MediaCrawler 的登录模块。
    """

    def __init__(self):
        self._cookie_jar = None
        self._cookie_path: Optional[str] = None
        self._cookies: list[dict] = []

    def load_cookies(self, cookie_content: str) -> bool:
        """
        加载 Cookie

        Args:
            cookie_content: Cookie 内容（JSON 字符串或 Mozilla 格式）

        Returns:
            是否加载成功
        """
        try:
            # 尝试解析为 JSON
            if cookie_content.strip().startswith("["):
                self._cookies = json.loads(cookie_content)
            elif cookie_content.strip().startswith("{"):
                self._cookies = json.loads(cookie_content).get("cookies", [])
            else:
                # 尝试作为 Mozilla Cookie 格式解析
                return self._load_mozilla_cookies(cookie_content)

            return len(self._cookies) > 0
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            return False

    def _load_mozilla_cookies(self, content: str) -> bool:
        """加载 Mozilla 格式的 Cookie 文件"""
        from http.cookiejar import MozillaCookieJar
        import tempfile
        import os

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(content)
                tmp_path = f.name

            jar = MozillaCookieJar(tmp_path)
            jar.load(ignore_discard=True, ignore_expires=True)

            self._cookies = [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path} for c in jar]
            self._cookie_path = tmp_path

            os.unlink(tmp_path)
            return len(self._cookies) > 0
        except Exception as e:
            logger.error(f"Failed to load Mozilla cookies: {e}")
            return False

    def get_cookies(self) -> list[dict]:
        """获取 Cookie 列表"""
        return self._cookies

    def get_cookie_header(self) -> str:
        """
        获取 Cookie 请求头

        Returns:
            Cookie 请求头字符串
        """
        return "; ".join([f"{c['name']}={c['value']}" for c in self._cookies])

    def get_cookie_dict(self) -> dict:
        """获取 Cookie 字典（用于 requests 库）"""
        return {c["name"]: c["value"] for c in self._cookies}

    def save_cookies(self, path: str) -> bool:
        """保存 Cookie 到文件"""
        try:
            with open(path, 'w') as f:
                json.dump({"cookies": self._cookies}, f, ensure_ascii=False, indent=2)
            self._cookie_path = path
            return True
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False


class ProxyMixin:
    """
    代理 Mixin

    参考 MediaCrawler 的 ProxyRefreshMixin，
    提供代理轮换和健康检查功能。
    """

    def __init__(self):
        self._proxy_pool: list[str] = []
        self._current_proxy_index: int = 0
        self._proxy_enabled: bool = False
        self._proxy_stats: dict = {}  # {proxy: {success, fail, last_used}}

    def set_proxy_pool(self, proxies: list[str]):
        """设置代理池"""
        self._proxy_pool = proxies
        self._proxy_enabled = len(proxies) > 0

    def add_proxy(self, proxy: str):
        """添加代理到池"""
        if proxy not in self._proxy_pool:
            self._proxy_pool.append(proxy)
            self._proxy_enabled = True

    def remove_proxy(self, proxy: str):
        """从池中移除代理"""
        if proxy in self._proxy_pool:
            self._proxy_pool.remove(proxy)
        self._proxy_enabled = len(self._proxy_pool) > 0

    def get_next_proxy(self) -> Optional[str]:
        """
        获取下一个代理（轮换）

        Returns:
            代理 URL 或 None
        """
        if not self._proxy_pool:
            return None

        proxy = self._proxy_pool[self._current_proxy_index]
        self._current_proxy_index = (self._current_proxy_index + 1) % len(self._proxy_pool)
        return proxy

    def get_current_proxy(self) -> Optional[str]:
        """获取当前代理"""
        if not self._proxy_pool:
            return None
        return self._proxy_pool[self._current_proxy_index % len(self._proxy_pool)]

    def mark_proxy_success(self, proxy: str):
        """标记代理成功"""
        if proxy not in self._proxy_stats:
            self._proxy_stats[proxy] = {"success": 0, "fail": 0}
        self._proxy_stats[proxy]["success"] += 1

    def mark_proxy_fail(self, proxy: str):
        """标记代理失败"""
        if proxy not in self._proxy_stats:
            self._proxy_stats[proxy] = {"success": 0, "fail": 0}
        self._proxy_stats[proxy]["fail"] += 1

    def get_proxy_stats(self) -> dict:
        """获取代理统计"""
        return self._proxy_stats

    def is_proxy_enabled(self) -> bool:
        """检查是否启用代理"""
        return self._proxy_enabled


class RateLimitMixin:
    """
    限流 Mixin

    参考 MediaCrawler 的限流设计，
    提供请求速率控制功能。
    支持：
    - 最小间隔限流
    - 窗口请求数限流（参考 MediaCrawler）
    - 指数退避重试
    """

    def __init__(self):
        # 最小间隔模式
        self._min_interval: float = 1.0  # 最小请求间隔（秒）
        self._last_request_time: float = 0
        self._rate_limit_enabled: bool = True

        # 窗口限流模式（参考 MediaCrawler）
        self._max_requests: int = 30      # 窗口内最大请求数
        self._window_seconds: float = 60.0  # 时间窗口（秒）
        self._request_count: int = 0
        self._window_start: float = 0
        self._window_limit_enabled: bool = False  # 窗口限流默认关闭

        # 重试配置
        self._max_retries: int = 3
        self._retry_delay: float = 1.0  # 初始重试延迟（秒）
        self._exponential_backoff: bool = True  # 是否使用指数退避

    def set_rate_limit(self, min_interval: float):
        """设置最小请求间隔"""
        self._min_interval = min_interval
        self._rate_limit_enabled = min_interval > 0

    def set_window_limit(self, max_requests: int, window_seconds: float):
        """
        设置窗口限流

        Args:
            max_requests: 窗口内最大请求数
            window_seconds: 时间窗口（秒）
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._window_limit_enabled = max_requests > 0 and window_seconds > 0

    def set_retry_config(self, max_retries: int = 3, retry_delay: float = 1.0, exponential_backoff: bool = True):
        """
        设置重试配置

        Args:
            max_retries: 最大重试次数
            retry_delay: 初始重试延迟（秒）
            exponential_backoff: 是否使用指数退避
        """
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._exponential_backoff = exponential_backoff

    async def wait_if_needed(self):
        """
        如果需要，等待以满足限流要求
        支持两种限流模式：
        1. 最小间隔模式
        2. 窗口限流模式（如果启用）
        """
        import time
        import asyncio

        # 最小间隔模式
        if self._rate_limit_enabled:
            now = time.time()
            elapsed = now - self._last_request_time

            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)

            self._last_request_time = time.time()

        # 窗口限流模式（参考 MediaCrawler）
        if self._window_limit_enabled:
            now = time.time()

            # 检查窗口是否过期
            if now - self._window_start >= self._window_seconds:
                self._request_count = 0
                self._window_start = now

            # 检查是否触发限流
            if self._request_count >= self._max_requests:
                wait_time = self._window_seconds - (now - self._window_start)
                if wait_time > 0:
                    logger.warning(f"[RateLimit] Window limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    # 重置窗口
                    self._request_count = 0
                    self._window_start = time.time()

            self._request_count += 1

    async def retry_with_backoff(self, func, *args, **kwargs):
        """
        使用指数退避重试函数
        参考 Postiz 的重试机制

        Args:
            func: 要重试的异步函数
            *args, **kwargs: 函数参数

        Returns:
            函数的返回值

        Raises:
            Exception: 如果所有重试都失败
        """
        import asyncio

        last_exception = None

        for attempt in range(self._max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt < self._max_retries:
                    # 计算延迟时间
                    if self._exponential_backoff:
                        delay = self._retry_delay * (2 ** attempt)
                    else:
                        delay = self._retry_delay

                    logger.warning(f"[Retry] Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[Retry] All {self._max_retries + 1} attempts failed")

        # 所有重试都失败，抛出最后一个异常
        if last_exception:
            raise last_exception
        return None
