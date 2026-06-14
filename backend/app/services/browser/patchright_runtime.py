"""Shared Patchright browser runtime.

This module keeps Patchright optional and centralizes the browser launch,
context creation, and simple page-rendered fetching used by higher-level
services.
"""

from __future__ import annotations

import os
import sys
import asyncio
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# Windows 需要 ProactorEventLoop 支持子进程（patchright 内部使用）
if sys.platform == "win32":
    # 检查当前事件循环类型，如果不是 Proactor 则设置
    try:
        loop = asyncio.get_event_loop()
        if not isinstance(loop, asyncio.ProactorEventLoop):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except RuntimeError:
        # 没有事件循环时设置策略
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

PATCHRIGHT_INSTALL_MESSAGE = "Patchright 未安装。请运行: pip install patchright && patchright install chromium"

_DEFAULT_VIEWPORT = {"width": 1280, "height": 800}
_BROWSER_MANAGED_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
    "accept-encoding",
    "cookie",
    "user-agent",
    "referer",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "sec-fetch-user",
    "upgrade-insecure-requests",
}


@dataclass
class BrowserFetchResult:
    url: str
    status_code: int
    headers: Dict[str, str]
    request_headers: Dict[str, str]
    html: str
    cookies: list[Dict[str, Any]]
    resources: list[Dict[str, str]]


class PatchrightBrowserRuntime:
    """Lazy Patchright runtime shared by browser-based services."""

    def __init__(self):
        self._patchright = None
        self._browser = None
        self._headless: Optional[bool] = None
        self._patchright_available: Optional[bool] = None
        self._executable_path: Optional[str] = None

    def is_available(self) -> bool:
        if self._patchright_available is not None:
            return self._patchright_available
        try:
            import patchright  # noqa: F401

            self._patchright_available = True
        except ImportError:
            self._patchright_available = False
        return self._patchright_available

    async def ensure_browser(self, headless: bool = False):
        if self._browser:
            return self._browser

        try:
            from patchright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(PATCHRIGHT_INSTALL_MESSAGE) from exc

        self._patchright = await async_playwright().start()
        launch_options = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        }
        try:
            self._browser = await self._patchright.chromium.launch(**launch_options)
        except Exception:
            executable_path = find_system_browser_executable()
            if not executable_path:
                raise
            self._browser = await self._patchright.chromium.launch(
                **launch_options,
                executable_path=executable_path,
            )
            self._executable_path = executable_path
        self._headless = headless
        return self._browser

    async def new_context(
        self,
        *,
        headless: bool = False,
        user_agent: Optional[str] = None,
        viewport: Optional[Dict[str, int]] = None,
        extra_http_headers: Optional[Dict[str, str]] = None,
    ):
        browser = await self.ensure_browser(headless=headless)
        context_options: Dict[str, Any] = {
            "viewport": viewport or _DEFAULT_VIEWPORT,
        }
        if user_agent:
            context_options["user_agent"] = user_agent
        if extra_http_headers:
            context_options["extra_http_headers"] = extra_http_headers
        return await browser.new_context(**context_options)

    async def fetch_page(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 30000,
        wait_until: str = "networkidle",
        headless: bool = False,
        settle_ms: int = 500,
    ) -> BrowserFetchResult:
        if _should_run_fetch_in_worker_thread():
            return await asyncio.to_thread(
                _fetch_page_in_worker_thread,
                url,
                method,
                headers,
                timeout_ms,
                wait_until,
                headless,
                settle_ms,
            )
        return await self._fetch_page_impl(
            url,
            method=method,
            headers=headers,
            timeout_ms=timeout_ms,
            wait_until=wait_until,
            headless=headless,
            settle_ms=settle_ms,
        )

    async def _fetch_page_impl(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 30000,
        wait_until: str = "networkidle",
        headless: bool = False,
        settle_ms: int = 500,
    ) -> BrowserFetchResult:
        if method.upper() != "GET":
            raise ValueError("browser fetch mode currently supports GET requests only")

        request_headers = _string_headers(headers)
        cookie_header = _pop_header(request_headers, "cookie")
        user_agent = _pop_header(request_headers, "user-agent")
        referer = _pop_header(request_headers, "referer")
        extra_headers = browser_extra_headers(request_headers)

        context = await self.new_context(
            headless=headless,
            user_agent=user_agent,
            extra_http_headers=extra_headers,
        )
        try:
            if cookie_header:
                cookies = cookie_header_to_browser_cookies(cookie_header, url)
                if cookies:
                    await context.add_cookies(cookies)

            page = await context.new_page()
            resources: list[Dict[str, str]] = []
            # 反反爬：禁用页面的 debugger 陷阱（起点等网站常用此手段）
            await page.add_init_script("""
                // 禁用 debugger 陷阱
                (function() {
                    const originalDebugger = window.debugger;
                    Object.defineProperty(window, 'debugger', {
                        get: function() { return function() {}; },
                        set: function() {}
                    });
                    // 禁用 console.log 以避免反爬检测
                    // 拦截 setInterval 中的 debugger
                    const originalSetInterval = window.setInterval;
                    window.setInterval = function(fn, delay) {
                        if (typeof fn === 'function' && fn.toString().indexOf('debugger') !== -1) {
                            return 0;
                        }
                        return originalSetInterval.apply(this, arguments);
                    };
                })();
            """)
            latest_response: Dict[str, Any] = {
                "url": url,
                "status_code": 0,
                "headers": {},
                "request_headers": {},
            }
            page.on("response", lambda response: _record_main_document_response(page, latest_response, response))
            page.on("response", lambda response: _record_interesting_resource(resources, response))
            response = await page.goto(
                url,
                wait_until=wait_until,
                timeout=timeout_ms,
                referer=referer,
            )
            _record_main_document_response(page, latest_response, response)
            if settle_ms > 0:
                await page.wait_for_timeout(settle_ms)
            # 等待字体加载完成（起点等网站使用自定义字体加密章节内容）
            try:
                await page.evaluate("""
                    async () => {
                        if (document.fonts && document.fonts.ready) {
                            await document.fonts.ready;
                        }
                    }
                """)
            except Exception:
                pass
            html = await page.content()
            html = await wait_for_probe_resolution(
                page,
                html,
                status_code=int(latest_response.get("status_code") or (response.status if response else 0)),
            )
            cookies = await context.cookies()
            resources.extend(await _collect_browser_resource_entries(page))
            return BrowserFetchResult(
                url=page.url,
                status_code=int(latest_response.get("status_code") or (response.status if response else 0)),
                headers=latest_response.get("headers") or (dict(response.headers) if response else {}),
                request_headers=latest_response.get("request_headers") or {},
                html=html,
                cookies=cookies,
                resources=_dedupe_resources(resources),
            )
        finally:
            await context.close()

    async def close(self):
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._patchright:
            try:
                await self._patchright.stop()
            except Exception:
                pass
        self._browser = None
        self._patchright = None
        self._headless = None
        self._executable_path = None


def cookie_header_to_browser_cookies(cookie_header: str, url: str) -> list[Dict[str, str]]:
    origin = _origin_url(url)
    pairs = _parse_cookie_pairs(cookie_header)
    return [
        {
            "name": name,
            "value": value,
            "url": origin,
        }
        for name, value in pairs
        if name
    ]


def browser_extra_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for key, value in _string_headers(headers).items():
        if key.lower() in _BROWSER_MANAGED_HEADERS:
            continue
        output[key] = value
    return output


def find_system_browser_executable() -> Optional[str]:
    env_path = os.getenv("PATCHRIGHT_EXECUTABLE_PATH", "").strip()
    candidates = [
        env_path,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _should_run_fetch_in_worker_thread() -> bool:
    # Uvicorn can run with a Windows Selector event loop, which cannot spawn
    # Patchright's driver subprocess. A dedicated Proactor loop in a worker
    # thread keeps browser-rendered test requests compatible with that setup.
    return sys.platform == "win32"


def _fetch_page_in_worker_thread(
    url: str,
    method: str,
    headers: Optional[Dict[str, Any]],
    timeout_ms: int,
    wait_until: str,
    headless: bool,
    settle_ms: int,
) -> BrowserFetchResult:
    async def runner() -> BrowserFetchResult:
        runtime = PatchrightBrowserRuntime()
        try:
            return await runtime._fetch_page_impl(
                url,
                method=method,
                headers=headers,
                timeout_ms=timeout_ms,
                wait_until=wait_until,
                headless=headless,
                settle_ms=settle_ms,
            )
        finally:
            await runtime.close()

    if hasattr(asyncio, "ProactorEventLoop"):
        loop = asyncio.ProactorEventLoop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(runner())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    return asyncio.run(runner())


def _parse_cookie_pairs(cookie_header: str) -> list[tuple[str, str]]:
    source = (cookie_header or "").strip()
    if not source:
        return []

    simple = SimpleCookie()
    try:
        simple.load(source)
        pairs = [(morsel.key, morsel.value) for morsel in simple.values()]
        if pairs:
            return pairs
    except CookieError:
        pass

    pairs: list[tuple[str, str]] = []
    for item in source.split(";"):
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        pairs.append((name.strip(), value.strip()))
    return pairs


def _origin_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _string_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not headers:
        return {}
    output: Dict[str, str] = {}
    for key, value in headers.items():
        if value is None:
            continue
        name = str(key).strip()
        if not name:
            continue
        output[name] = str(value)
    return output


def _pop_header(headers: Dict[str, str], name: str) -> Optional[str]:
    for key in list(headers.keys()):
        if key.lower() == name.lower():
            return headers.pop(key)
    return None


def _record_main_document_response(page: Any, latest_response: Dict[str, Any], response: Any) -> None:
    if response is None:
        return
    try:
        if response.request.resource_type != "document":
            return
    except Exception:
        pass
    try:
        if response.frame != page.main_frame:
            return
    except Exception:
        pass
    try:
        latest_response["url"] = response.url
        latest_response["status_code"] = response.status
        latest_response["headers"] = dict(response.headers)
        latest_response["request_headers"] = dict(response.request.headers)
    except Exception:
        return


def _record_interesting_resource(resources: list[Dict[str, str]], response: Any) -> None:
    if response is None:
        return
    try:
        url = str(response.url)
        resource_type = str(response.request.resource_type or "")
        content_type = str(response.headers.get("content-type") or "")
        lower = url.lower()
        if (
            resource_type in {"font", "stylesheet", "script", "xhr", "fetch"}
            or any(token in lower for token in ("font", "woff", "ttf", "otf", "eot", "chapter", "ajax", "content"))
        ):
            resources.append(
                {
                    "url": url,
                    "type": resource_type,
                    "status": str(response.status),
                    "content_type": content_type,
                }
            )
    except Exception:
        return


async def _collect_browser_resource_entries(page: Any) -> list[Dict[str, str]]:
    try:
        entries = await page.evaluate(
            """
            () => (performance.getEntriesByType('resource') || []).map((entry) => ({
                url: entry.name || '',
                type: entry.initiatorType || '',
                status: '',
                content_type: '',
            }))
            """
        )
    except Exception:
        return []
    output: list[Dict[str, str]] = []
    for entry in entries or []:
        url = str((entry or {}).get("url") or "")
        lower = url.lower()
        resource_type = str((entry or {}).get("type") or "")
        if (
            resource_type in {"css", "link", "script", "xmlhttprequest", "fetch"}
            or any(token in lower for token in ("font", "woff", "ttf", "otf", "eot", "chapter", "ajax", "content"))
        ):
            output.append(
                {
                    "url": url,
                    "type": resource_type,
                    "status": str((entry or {}).get("status") or ""),
                    "content_type": str((entry or {}).get("content_type") or ""),
                }
            )
    return output


def _dedupe_resources(resources: list[Dict[str, str]], limit: int = 160) -> list[Dict[str, str]]:
    deduped: list[Dict[str, str]] = []
    seen: set[str] = set()
    for item in resources:
        url = str((item or {}).get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(
            {
                "url": url,
                "type": str((item or {}).get("type") or ""),
                "status": str((item or {}).get("status") or ""),
                "content_type": str((item or {}).get("content_type") or ""),
            }
        )
        if len(deduped) >= limit:
            break
    return deduped


def looks_like_probe_shell(html: str, status_code: int = 0) -> bool:
    source = (html or "").lower()
    if status_code and status_code != 202 and "probe.js" not in source:
        return False
    if "probe.js" in source or "probev3.js" in source:
        return True
    stripped = source.strip()
    return status_code == 202 and len(stripped) < 2500 and "<script" in stripped and len(_strip_html_text(stripped)) < 120


async def wait_for_probe_resolution(
    page: Any,
    html: str,
    *,
    status_code: int = 0,
    timeout_ms: int = 12000,
    interval_ms: int = 500,
) -> str:
    if not looks_like_probe_shell(html, status_code):
        return html

    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
    current = html
    while asyncio.get_running_loop().time() < deadline:
        await page.wait_for_timeout(interval_ms)
        try:
            await page.wait_for_load_state("networkidle", timeout=1500)
        except Exception:
            pass
        current = await page.content()
        if not looks_like_probe_shell(current):
            return current
    return current


def _strip_html_text(html: str) -> str:
    return " ".join(
        part.strip()
        for part in html.replace("<", " <").replace(">", "> ").split()
        if not part.startswith("<")
    )


_patchright_runtime: Optional[PatchrightBrowserRuntime] = None


def get_patchright_runtime() -> PatchrightBrowserRuntime:
    global _patchright_runtime
    if _patchright_runtime is None:
        _patchright_runtime = PatchrightBrowserRuntime()
    return _patchright_runtime
