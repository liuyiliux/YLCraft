"""
YLCraft — 平台爬虫基础抽象类
支持 API 模式和 Patchright 模式切换
"""
from __future__ import annotations

import abc
import asyncio
import json
import logging
from typing import Optional, List, Dict, Any, Type
from abc import abstractmethod

import httpx

from .types import (
    ClientMode,
    SearchResult,
    NoteDetail,
    UserProfile,
    SeriesInfo,
    SearchParams,
    ClientConfig,
)

logger = logging.getLogger("ylcraft.platforms.base")


# =============================================================================
# 基础客户端类（支持模式切换）
# =============================================================================

class BasePlatformClient(abc.ABC):
    """
    平台客户端基类
    支持两种模式：
    1. API 模式：直接 HTTP 请求（快速，但可能被反爬）
    2. Patchright 模式：使用浏览器自动化（慢，但能绕过反爬）
    """
    
    def __init__(self, config: ClientConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None
        self._patchright_page = None
        self._patchright_context = None
        
    # =========================================================================
    # 上下文管理
    # =========================================================================
    
    async def __aenter__(self):
        """进入上下文，初始化客户端"""
        if self.config.mode == ClientMode.API:
            await self._init_http_client()
        elif self.config.mode == ClientMode.PATCHRIGHT:
            await self._init_patchright()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，清理资源"""
        if self._http_client:
            await self._http_client.aclose()
        if self._patchright_page:
            await self._patchright_page.close()
        if self._patchright_context:
            await self._patchright_context.close()
    
    # =========================================================================
    # 初始化方法
    # =========================================================================
    
    async def _init_http_client(self):
        """初始化 HTTP 客户端（API 模式）"""
        headers = self._build_headers()
        self._http_client = httpx.AsyncClient(
            headers=headers,
            timeout=self.config.timeout,
            proxy=self.config.proxy,
            follow_redirects=True,
        )
        logger.info(f"[{self.config.platform}] HTTP client initialized (API mode)")
    
    async def _init_patchright(self):
        """初始化 Patchright 浏览器（Patchright 模式）"""
        try:
            import patchright
            
            playwright = await patchright.async_playwright().start()
            
            # 启动浏览器
            browser = await playwright.chromium.launch(
                headless=self.config.patchright_headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
            
            # 创建上下文（使用 Cookie）
            self._patchright_context = await browser.new_context(
                user_agent=self.config.user_agent or self._get_default_user_agent(),
                viewport={'width': 1920, 'height': 1080},
            )
            
            # 设置 Cookie
            if self.config.cookie:
                await self._set_cookies_to_browser()
            
            # 创建页面
            self._patchright_page = await self._patchright_context.new_page()
            
            logger.info(f"[{self.config.platform}] Patchright initialized (browser mode)")
            
        except ImportError:
            logger.error(f"[{self.config.platform}] patchright not installed. Run: pip install patchright")
            raise
        except Exception as e:
            logger.error(f"[{self.config.platform}] Failed to initialize Patchright: {e}")
            raise
    
    async def _set_cookies_to_browser(self):
        """将 Cookie 字符串设置到浏览器"""
        if not self._patchright_context or not self.config.cookie:
            return
        
        # 解析 Cookie 字符串
        cookies = self._parse_cookie_string(self.config.cookie)
        
        # 获取平台域名
        domain = self._get_platform_domain()
        
        # 设置 Cookie
        for cookie in cookies:
            try:
                await self._patchright_context.add_cookies([{
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': domain,
                    'path': '/',
                }])
            except Exception as e:
                logger.warning(f"[{self.config.platform}] Failed to set cookie {cookie['name']}: {e}")
        
        logger.info(f"[{self.config.platform}] Cookies set to browser")
    
    # =========================================================================
    # 请求方法（自动选择模式）
    # =========================================================================
    
    async def request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Any:
        """
        统一请求方法
        根据 config.mode 自动选择 API 或 Patchright
        """
        import logging
        logger = logging.getLogger("ylcraft.platforms.base")
        logger.debug(f"request() {method} {url} (mode={self.config.mode})")
        
        if self.config.mode == ClientMode.API:
            return await self._request_api(method, url, **kwargs)
        elif self.config.mode == ClientMode.PATCHRIGHT:
            return await self._request_patchright(method, url, **kwargs)
        else:
            raise ValueError(f"Unknown mode: {self.config.mode}")
    
    async def _request_api(self, method: str, url: str, **kwargs) -> Any:
        """API 模式请求（带重试和频率控制）"""
        if not self._http_client:
            await self._init_http_client()

        import logging
        logger = logging.getLogger("ylcraft.platforms.base")

        max_retries = self.config.max_retries
        retry_delay = self.config.retry_delay

        for attempt in range(max_retries):
            logger.debug(f"[request_api] {method} {url} (attempt {attempt + 1}/{max_retries})")

            try:
                response = await self._http_client.request(method, url, **kwargs)
                response.raise_for_status()

                # httpx 会自动处理 Brotli (br) 解压（需要 brotli 包）
                try:
                    return response.json()
                except (ValueError, UnicodeDecodeError) as e:
                    logger.warning(f"[request_api] JSON parse failed for {url}: {e}")
                    content = response.text
                    try:
                        import json
                        return json.loads(content)
                    except ValueError as e2:
                        logger.error(f"[request_api] JSON parse failed (fallback): {e2}")
                        logger.error(f"[request_api] Response preview: {content[:500]}")
                        return {'text': content, 'status': response.status_code}

            except Exception as e:
                status = getattr(getattr(e, 'response', None), 'status_code', 0)
                is_412 = status == 412 or '412' in str(e)

                if is_412 and attempt < max_retries - 1:
                    wait = retry_delay * (2 ** attempt) + (attempt * 0.5)
                    logger.warning(f"[request_api] 412 banned, retrying in {wait:.1f}s...")
                    await asyncio.sleep(wait)
                    continue

                if attempt < max_retries - 1:
                    wait = retry_delay * (2 ** attempt)
                    logger.warning(f"[request_api] Error: {e}, retrying in {wait:.1f}s...")
                    await asyncio.sleep(wait)
                    continue

                logger.error(f"[request_api] Failed after {max_retries} attempts: {e}")
                raise
    
    async def _request_patchright(self, method: str, url: str, **kwargs) -> Any:
        """Patchright 模式请求（通过浏览器）"""
        if not self._patchright_page:
            await self._init_patchright()
        
        # 简单实现：直接用页面请求
        # 复杂场景可以拦截请求、使用 CDP 等
        if method.upper() == 'GET':
            response = await self._patchright_page.goto(url, wait_until='networkidle')
            content = await self._patchright_page.content()
            
            # 尝试提取 JSON（如果是 API 请求）
            try:
                # 从页面中提取 JSON 数据
                json_text = await self._patchright_page.evaluate("""
                    () => {
                        const pre = document.querySelector('pre');
                        if (pre) return pre.innerText;
                        return document.body.innerText;
                    }
                """)
                return json.loads(json_text)
            except Exception:
                return {'text': content, 'status': response.status if response else 200}
        else:
            raise NotImplementedError(f"Patchright mode only supports GET requests for now")
    
    # =========================================================================
    # 抽象方法（子类必须实现）
    # =========================================================================
    
    @abstractmethod
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头（API 模式用）"""
        pass
    
    @abstractmethod
    def _get_default_user_agent(self) -> str:
        """获取默认 User-Agent"""
        pass
    
    @abstractmethod
    def _get_platform_domain(self) -> str:
        """获取平台域名（用于设置 Cookie）"""
        pass
    
    @abstractmethod
    async def search(self, params: SearchParams) -> List[SearchResult]:
        """
        搜索
        子类实现具体的搜索逻辑
        """
        pass
    
    @abstractmethod
    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        """
        获取详情
        子类实现具体的详情获取逻辑
        """
        pass
    
    # =========================================================================
    # 可选方法（子类可选实现）
    # =========================================================================
    
    async def get_user_profile(self, user_id: str) -> UserProfile:
        """获取用户主页（可选）"""
        raise NotImplementedError(f"[{self.config.platform}] get_user_profile not implemented")
    
    async def get_user_notes(self, user_id: str, max_results: int = 20) -> List[SearchResult]:
        """获取用户发布的笔记（可选）"""
        raise NotImplementedError(f"[{self.config.platform}] get_user_notes not implemented")
    
    async def get_series(self, series_id: str) -> SeriesInfo:
        """获取合集信息（可选，B站等）"""
        raise NotImplementedError(f"[{self.config.platform}] get_series not implemented")
    
    async def get_comments(self, item_id: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """获取评论（可选）"""
        raise NotImplementedError(f"[{self.config.platform}] get_comments not implemented")
    
    # =========================================================================
    # 工具方法
    # =========================================================================
    
    @staticmethod
    def _parse_cookie_string(cookie_str: str) -> List[Dict[str, str]]:
        """解析 Cookie 字符串（key=value; key2=value2 格式）"""
        cookies = []
        for item in cookie_str.split(';'):
            item = item.strip()
            if '=' in item:
                name, value = item.split('=', 1)
                cookies.append({'name': name.strip(), 'value': value.strip()})
        return cookies    
    @staticmethod
    def _build_cookie_string(cookies: List[Dict]) -> str:
        """构建 Cookie 字符串"""
        return '; '.join([f"{c['name']}={c['value']}" for c in cookies])
    
    def _log(self, message: str, level: str = 'info'):
        """日志"""
        log_func = getattr(logger, level, logger.info)
        log_func(f"[{self.config.platform}] {message}")


# =============================================================================
# 平台客户端工厂
# =============================================================================

class PlatformClientFactory:
    """平台客户端工厂"""
    
    _registry: Dict[str, Type[BasePlatformClient]] = {}
    
    @classmethod
    def register(cls, platform: str, client_class: Type[BasePlatformClient]):
        """注册平台客户端类"""
        cls._registry[platform] = client_class
        logger.info(f"Registered platform client: {platform} -> {client_class.__name__}")
    
    @classmethod
    def create(
        cls,
        platform: str,
        mode: ClientMode = ClientMode.API,
        cookie: str = "",
        **kwargs
    ) -> BasePlatformClient:
        """创建平台客户端实例"""
        client_class = cls._registry.get(platform)
        if not client_class:
            raise ValueError(f"Unsupported platform: {platform}. Available: {list(cls._registry.keys())}")
        
        # 支持传入 ClientConfig 对象作为第二个参数
        if isinstance(mode, ClientConfig):
            return client_class(mode)
        
        config = ClientConfig(
            platform=platform,
            mode=mode,
            cookie=cookie,
            **kwargs
        )
        
        return client_class(config)


# 装饰器：自动注册平台客户端
def register_platform(platform: str):
    """装饰器：自动注册平台客户端类"""
    def decorator(cls):
        PlatformClientFactory.register(platform, cls)
        return cls
    return decorator
