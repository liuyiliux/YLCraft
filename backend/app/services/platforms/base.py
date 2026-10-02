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
        # 浏览器上下文是否已交给 session_pool 管理。
        # True = 所有权归池，客户端退出时**不能关**（否则复用中的会话被关死，
        # 下次搜索报 TargetClosedError）。
        self._patchright_pooled = False
        # 规范化后的 Cookie 头字符串（懒求值，见 header_cookie()）
        self._header_cookie_cache: Optional[str] = None
        
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
        """退出上下文，清理资源。

        ⚠️ 浏览器上下文**一律不在这里关**——它由 session_pool 管理。

        踩过两次（2026-09-27）：
          1. 原来无条件 close() → 复用中的会话被关，下次又要重开浏览器（16 秒）
          2. 按 `_patchright_owned` 判断 → 逻辑写反了：
             自建的那个 owned=True 跳过关闭（对），
             复用的那个 owned=False **反而去关**（错，把池里的会话关死了），
             表现为第 3 次搜索报 TargetClosedError。

        正确做法：只要注册进了池，所有权就归池，客户端退出时什么都不做。
        池按空闲 TTL 回收。真正没登记进池的临时上下文才需要自己收尾。
        """
        if self._http_client:
            await self._http_client.aclose()

        # 已登记到池 → 生命周期归池，本客户端不碰
        if getattr(self, "_patchright_pooled", False):
            return

        # 未经池管理的临时上下文（异常路径才会走到）——收尾释放
        if self._patchright_page:
            try:
                await self._patchright_page.close()
            except Exception:
                pass
        if self._patchright_context:
            try:
                await self._patchright_context.close()
            except Exception:
                pass
    
    # =========================================================================
    # 初始化方法
    # =========================================================================
    
    def header_cookie(self) -> str:
        """返回**可直接放进 HTTP 头**的 Cookie 字符串（`k=v; k2=v2`）。

        这是一个**公共层**方法，不是各平台自己实现的——因为"把 Cookie 放进 header"
        这一步曾多次写错：平台连接里存的是 **Netscape 文件格式**（含
        `# Netscape HTTP Cookie File` 注释头、字段以制表符分隔），直接赋给 `Cookie`
        头会被 httpx 拒绝（`Illegal header value`，头值不允许换行/制表符），
        **请求根本发不出去**，外部表现为"搜索静默返回空"。

        历史上同一代码库里三种写法并存（番茄 `normalize_cookie(...)` 正确、B站与小红书
        直接赋原文均失败），说明**把这一步留给每个平台各写一遍是结构性错误**。因此收在
        基类，并在 `_init_http_client` 里统一覆盖注入：单个平台即便写错也会被纠正。

        对传入格式不敏感：Netscape / `k=v;` / JSON 数组皆可。结果缓存。
        """
        if self._header_cookie_cache is None:
            raw = self.config.cookie or ""
            if raw:
                try:
                    from app.services.cookies.manager import CookieManager

                    raw = CookieManager().extract_raw(raw) or raw
                except Exception as exc:  # noqa: BLE001 - 规范化失败不得阻断请求
                    logger.warning(f"[{self.config.platform}] Cookie 规范化失败，回退使用原文：{exc}")
            self._header_cookie_cache = raw
        return self._header_cookie_cache

    async def _init_http_client(self):
        """初始化 HTTP 客户端（API 模式）"""
        headers = self._build_headers()
        # 统一覆盖注入 Cookie：各平台 `_build_headers` 的写法不一致是历史上多次故障的
        # 来源，因此在基类强制纠正一次，使单个平台即便写错也不会导致请求非法。
        cookie = self.header_cookie()
        if cookie:
            headers["Cookie"] = cookie
        else:
            headers.pop("Cookie", None)
        self._http_client = httpx.AsyncClient(
            headers=headers,
            timeout=self.config.timeout,
            proxy=self.config.proxy,
            follow_redirects=True,
        )
        logger.info(f"[{self.config.platform}] HTTP client initialized (API mode)")
    
    async def _init_patchright(self):
        """初始化 Patchright 浏览器（Patchright 模式）。

        ## 这里修过两个真机 bug（2026-09-26）

        1. **import 路径错了。**
           原写法 `import patchright; patchright.async_playwright()`
           报 `module 'patchright' has no attribute 'async_playwright'`——
           正确入口是 `from patchright.async_api import async_playwright`。
           这个错被上层 `_search_via_platforms` 的 `except Exception` 吞成
           `return []`，表现为"小红书搜不到任何东西"，查了很久才发现。

        2. **改用持久化 profile。**
           原来自己 `launch()`（非持久化，每次全新空 profile），
           与 cookies 采集管理器不一致；且小红书/抖音这类站点会因为
           "每次都是新设备"触发风控。统一走 runtime 的
           `new_context(persistent_platform=...)`。

        另外原实现硬编码 viewport 1920x1080 且不传持久化平台；
        现在统一由 runtime 处理，行为与其它模块一致。
        """
        try:
            from app.services.browser.patchright_runtime import (
                get_patchright_runtime,
            )

            runtime = get_patchright_runtime()
            # 复用浏览器上下文：每次搜索都 new 一个 context 的代价是
            # 开浏览器(2~3s) + 预热首页(6s)，实测单次搜索 16~19 秒。
            # 用 session_pool 按 平台+连接 复用，预热也只做一次。
            from app.services.platforms.session_pool import (
                PooledSession,
                get_session_pool,
            )

            pool = get_session_pool()
            conn_id = getattr(self.config, "conn_id", "") or ""
            session_key = f"{self.config.platform}|{conn_id or '-'}"

            session = pool.get(session_key)
            if session is not None:
                self._patchright_context = session.ctx
                self._patchright_page = session.page
                # 复用的会话归池所有，退出时绝不能关
                self._patchright_pooled = True
                logger.info(
                    "[%s] 复用浏览器会话 key=%s（空闲 %.0fs）",
                    self.config.platform, session_key, session.idle_seconds(),
                )
            else:
                # ⚠️ **微博默认无头**（2026-09-29）
                #
                # 用户反馈"为啥个人中心的微博老是打开浏览器了？"
                #
                # 搜索/用户查询都要走 patchright（微博靠 Service Worker），
                # 而 `patchright_headless` 默认 False → **每次新会话都弹窗口**。
                #
                # 实测（同一个持久化 profile）：
                #     无头：搜索返回 JSON，cards=14  ✅
                #     有头：搜索返回 JSON，cards=13  ✅
                #
                # **两者都能搜到** —— 原注释"无头会被甩验证码页"已过时。
                #
                # 登录流程仍要有头（用户得扫码），但那条走
                # `PatchrightManager`、不经这里，所以不受影响。
                headless = self.config.patchright_headless
                if self.config.platform in ("weibo", "wb"):
                    headless = True
                self._patchright_context = await runtime.new_context(
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    user_agent=self.config.user_agent or self._get_default_user_agent(),
                    persistent_platform=self.config.platform,
                )
                self._patchright_page = await self._patchright_context.new_page()

                # 小红书等站点要求 cookie 进 cookie jar 才认登录态
                # （实测：只放请求头无效）。所以这里显式 add_cookies。
                if self.config.cookie:
                    await self._set_cookies_to_browser()

                # 登记到池里 → 所有权转移给池，本客户端退出时不关
                self._patchright_pooled = True
                pool.put(session_key, PooledSession(
                    ctx=self._patchright_context, page=self._patchright_page,
                ))
                logger.info(
                    "[%s] 新建浏览器会话 key=%s",
                    self.config.platform, session_key,
                )

        except ImportError as exc:
            logger.error(
                "[%s] patchright 未安装：%s。请运行 pip install patchright",
                self.config.platform, exc,
            )
            raise
        except Exception as exc:
            # 必须带上异常类型：此前只打 str(e)，把 ImportError 之类
            # 伪装成了普通描述，排查时被带偏。
            logger.error(
                "[%s] 初始化 Patchright 失败：%s: %s",
                self.config.platform, type(exc).__name__, exc,
            )
            raise
    
    async def _set_cookies_to_browser(self):
        """将 Cookie 字符串设置到浏览器"""
        if not self._patchright_context or not self.config.cookie:
            return
        
        # 必须先用公共的规范化结果：`_parse_cookie_string` 只认 `k=v; k2=v2`，
        # 直接喂 Netscape 原文不会报错，但**一个 cookie 都设不上**——浏览器模式会
        # 静默变成未登录。这是同一类"格式假设不一致"的又一处。
        cookies = self._parse_cookie_string(self.header_cookie())
        
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
    
    async def get_comments(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> List[Dict[str, Any]]:
        """获取评论（可选）。

        ## ⚠️ 2026-10-01 加了 `page` / `cursor` 两个**可选**参数

        原来只有 `(item_id, max_results)` —— 但评论必须能**翻页**
        （一条热门内容几千条评论，只取前 20 条没意义）。

        加可选参数而不是改必填，是为了**不破坏**已有实现：
          · B站有自己的 `get_comments_paged`（游标分页，更完整）
          · 新平台可以按自己平台的分页方式选 `page` 或 `cursor`

        Args:
            item_id: 内容 ID
            max_results: 每页条数
            page: 页码（offset 分页的平台用）
            cursor: 游标（cursor 分页的平台用，如 YouTube/微博）

        Returns:
            评论字典列表。**不强制结构** —— 各平台字段不同，
            由上层（`/api/v1/comments`）归一化。
        """
        raise NotImplementedError(
            f"[{self.config.platform}] get_comments not implemented"
        )

    async def get_comments_page(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """取**一页**评论，并带回游标（可选，比 `get_comments` 更完整）。

        ## 为什么单独加这个方法，而不是改 `get_comments` 的返回类型

        `get_comments` 已经返回 `List[Dict]` 且 5 个平台都实现了 ——
        改返回类型会**破坏全部已实现平台**。

        所以加这个**可选**方法：实现它就能支持"加载更多"，
        不实现则上层退化成"用 page 猜"（可能翻不出新数据）。

        Returns:
            ```python
            {
                "comments": [...],      # 评论列表（各平台字段，上层归一）
                "has_more": bool,       # 还有没有下一页
                "next_cursor": str,     # 下一页游标（**核心**）
                "total": int,           # 总数（拿不到就 0）
            }
            ```

        ## ⚠️ 为什么游标重要

        实测：很多平台的分页是 **cursor 游标不是页码**
        （微博 `max_id`、快手 `pcursor`、X `Bottom cursor`、
        YouTube continuation）。

        上层若只会传 `page`，第二次请求会**拿到和第一次相同的数据**
        —— 前端点"加载更多"看起来没反应（实测踩过同类问题）。

        ## 与 `get_comments` 的关系

        实现者可以让 `get_comments` 调它、只取 `comments` 字段
        （避免两处各写一遍分页逻辑）。
        """
        # 默认实现：退化成调 get_comments（无游标）
        comments = await self.get_comments(
            item_id, max_results=max_results, page=page, cursor=cursor
        )
        return {
            "comments": comments,
            "has_more": len(comments or []) >= max_results,
            "next_cursor": "",
            "total": len(comments or []),
        }

    async def get_replies(
        self,
        item_id: str,
        comment_id: str,
        max_results: int = 20,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """取某条评论的**子回复**（楼中楼，可选）。

        ## 为什么单独一个方法

        子回复**不是**"评论列表的下一页" —— 它是"某条评论下面的回复"，
        参数、端点、甚至**签名函数**都可能不同：

            抖音：端点换 `/comment/list/reply/`，
                  参数用 `comment_id`+`item_id`（不是 aweme_id），
                  且签名要用 `sign_reply`（主评论是 `sign_datail`）
            快手：端点换 `/photo/comment/sublist`，加 `rootCommentId`
            X   ：二级回复在**同一棵** TweetDetail 树里，靠
                  `in_reply_to_status_id_str` 串（不用额外请求）

        Returns:
            与 `get_comments_page` 同构：
            `{comments, has_more, next_cursor, total}`
        """
        raise NotImplementedError(
            f"[{self.config.platform}] get_replies not implemented"
        )

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
    def supported(cls) -> set[str]:
        """已注册的平台名（含别名）。

        ⚠️ **要区分"没实现"和"没搜到"**（2026-09-29）

        实测：前端下拉里有「快手」可点，但后端没客户端 ——
        原来会**静默返回空列表**，用户看到"找到 0 条结果"，
        完全不知道是"这个平台还没实现"。假阴性，排查极费时间。

        调用方（`api/v1/crawler.py`）用这个判断并**显式报 501**。
        """
        return set(cls._registry.keys())
    
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
