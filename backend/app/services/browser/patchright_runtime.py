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
}


@dataclass
class BrowserFetchResult:
    url: str
    status_code: int
    headers: Dict[str, str]
    html: str


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
            response = await page.goto(
                url,
                wait_until=wait_until,
                timeout=timeout_ms,
                referer=referer,
            )
            if settle_ms > 0:
                await page.wait_for_timeout(settle_ms)
            html = await page.content()
            return BrowserFetchResult(
                url=page.url,
                status_code=response.status if response else 0,
                headers=dict(response.headers) if response else {},
                html=html,
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


_patchright_runtime: Optional[PatchrightBrowserRuntime] = None


def get_patchright_runtime() -> PatchrightBrowserRuntime:
    global _patchright_runtime
    if _patchright_runtime is None:
        _patchright_runtime = PatchrightBrowserRuntime()
    return _patchright_runtime
