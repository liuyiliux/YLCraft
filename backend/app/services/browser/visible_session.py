"""Visible Patchright browser sessions for interactive debugging."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import uuid
from typing import Any, Dict, Optional

from app.services.browser.patchright_runtime import (
    PatchrightBrowserRuntime,
    _collect_browser_resource_entries,
    _dedupe_resources,
    _record_interesting_resource,
    browser_extra_headers,
    cookie_header_to_browser_cookies,
    wait_for_probe_resolution,
)


class VisibleBrowserSessionManager:
    """Manage long-lived visible browser pages on a dedicated event loop."""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._runtime: Optional[PatchrightBrowserRuntime] = None
        self._sessions: Dict[str, Dict[str, Any]] = {}

    async def start_session(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, Any]] = None,
        wait_until: str = "domcontentloaded",
        timeout_ms: int = 45000,
    ) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        future = self._submit(self._start_session(session_id, url, headers or {}, wait_until, timeout_ms))
        return await asyncio.wrap_future(future)

    async def snapshot_session(self, session_id: str) -> Dict[str, Any]:
        future = self._submit(self._snapshot_session(session_id))
        return await asyncio.wrap_future(future)

    async def close_session(self, session_id: str) -> bool:
        future = self._submit(self._close_session(session_id))
        return await asyncio.wrap_future(future)

    def _submit(self, coro):
        self._ensure_worker_loop()
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _ensure_worker_loop(self):
        if self._loop and self._loop.is_running():
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run_loop, name="ylcraft-visible-browser", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("visible browser worker failed to start")

    def _run_loop(self):
        if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()

    async def _ensure_runtime(self) -> PatchrightBrowserRuntime:
        if self._runtime is None:
            self._runtime = PatchrightBrowserRuntime()
        return self._runtime

    async def _start_session(
        self,
        session_id: str,
        url: str,
        headers: Dict[str, Any],
        wait_until: str,
        timeout_ms: int,
    ) -> Dict[str, Any]:
        request_headers = _string_headers(headers)
        cookie_header = _pop_header(request_headers, "cookie")
        user_agent = _pop_header(request_headers, "user-agent")
        referer = _pop_header(request_headers, "referer")
        extra_headers = browser_extra_headers(request_headers)

        runtime = await self._ensure_runtime()
        context = await runtime.new_context(
            headless=False,
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
            self._sessions[session_id] = {
                "context": context,
                "page": page,
                "created_at": time.time(),
                "status_code": int(latest_response.get("status_code") or (response.status if response else 0)),
                "headers": latest_response.get("headers") or (dict(response.headers) if response else {}),
                "request_headers": latest_response.get("request_headers") or {},
                "latest_response": latest_response,
                "resources": resources,
            }
            return {
                "session_id": session_id,
                "url": page.url,
                "status_code": int(latest_response.get("status_code") or (response.status if response else 0)),
                "headers": latest_response.get("headers") or (dict(response.headers) if response else {}),
            }
        except Exception:
            await context.close()
            raise

    async def _snapshot_session(self, session_id: str) -> Dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("browser session does not exist")
        page = session["page"]
        if page.is_closed():
            await self._close_session(session_id)
            raise ValueError("browser session page is closed")

        html = await page.content()
        latest_response = session.get("latest_response") or {}
        html = await wait_for_probe_resolution(
            page,
            html,
            status_code=int(latest_response.get("status_code") or session.get("status_code", 0)),
        )
        cookies = await session["context"].cookies()
        resources = _dedupe_resources(
            list(session.get("resources") or []) + await _collect_browser_resource_entries(page)
        )
        return {
            "session_id": session_id,
            "url": page.url,
            "status_code": int(latest_response.get("status_code") or session.get("status_code", 0)),
            "headers": latest_response.get("headers") or session.get("headers", {}),
            "request_headers": latest_response.get("request_headers") or session.get("request_headers", {}),
            "html": html,
            "cookies": cookies,
            "resources": resources,
        }

    async def _close_session(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if not session:
            return False
        try:
            await session["context"].close()
        except Exception:
            pass
        if not self._sessions and self._runtime:
            await self._runtime.close()
            self._runtime = None
        return True


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


_visible_browser_session_manager: Optional[VisibleBrowserSessionManager] = None


def get_visible_browser_session_manager() -> VisibleBrowserSessionManager:
    global _visible_browser_session_manager
    if _visible_browser_session_manager is None:
        _visible_browser_session_manager = VisibleBrowserSessionManager()
    return _visible_browser_session_manager
