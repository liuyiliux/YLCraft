"""
起点中文网特殊解析器
处理字体加密的VIP章节内容
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class QidianVipParser:
    """
    起点VIP章节解析器
    应对起点的字体加密反爬机制
    """

    # 起点明文章节API（绕过字体加密）
    CHAPTER_API = "https://www.qidian.com/ajax/chapter/getChapter"

    def __init__(self, browser_runtime=None):
        self._browser_runtime = browser_runtime

    async def fetch_via_api(
        self,
        book_id: str,
        chapter_id: str,
        cookie: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        通过起点明文API获取章节内容

        Args:
            book_id: 书籍ID
            chapter_id: 章节ID
            cookie: 用户的VIP登录Cookie

        Returns:
            包含 chapterName 和 content 的字典
        """
        import httpx

        request_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://www.qidian.com/chapter/{book_id}/{chapter_id}/",
            "X-Requested-With": "XMLHttpRequest",
        }
        if headers:
            request_headers.update(_sanitize_request_headers(headers))
        request_headers["Accept"] = "application/json, text/plain, */*"
        request_headers["Referer"] = f"https://www.qidian.com/chapter/{book_id}/{chapter_id}/"
        request_headers["X-Requested-With"] = "XMLHttpRequest"

        params = {
            "bookId": book_id,
            "chapterId": chapter_id,
        }

        if cookie:
            request_headers["Cookie"] = cookie

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            verify=False,
        ) as client:
            response = await client.get(
                self.CHAPTER_API,
                params=params,
                headers=request_headers,
            )
            response.raise_for_status()
            return response.json()

    async def fetch_via_browser(
        self,
        url: str,
        cookie: Optional[str] = None,
        selector: str = "main",
        headers: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        通过浏览器渲染获取章节内容（绕过字体加密）

        Args:
            url: 章节完整URL
            cookie: VIP登录Cookie
            selector: 内容选择器（默认 main）

        Returns:
            章节纯文本内容
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        # Windows 上 asyncio 子进程不支持，使用线程池运行
        def _run_browser_sync():
            """在独立线程中运行浏览器（使用独立事件循环）"""
            from app.services.browser.patchright_runtime import (
                PatchrightBrowserRuntime,
                browser_extra_headers,
                cookie_header_to_browser_cookies,
            )

            async def _browser_task():
                runtime = PatchrightBrowserRuntime()
                context = None
                request_headers = _sanitize_request_headers(headers or {})
                if cookie:
                    request_headers["Cookie"] = cookie
                user_agent = _pop_case_insensitive(request_headers, "User-Agent")
                referer = _pop_case_insensitive(request_headers, "Referer")
                cookie_header = _pop_case_insensitive(request_headers, "Cookie")
                extra_headers = browser_extra_headers(request_headers)

                try:
                    context = await runtime.new_context(
                        headless=False,
                        user_agent=user_agent,
                        extra_http_headers=extra_headers or None,
                    )

                    if cookie_header:
                        cookies = cookie_header_to_browser_cookies(cookie_header, url)
                        if cookies:
                            await context.add_cookies(cookies)

                    page = await context.new_page()
                    goto_options = {"wait_until": "load", "timeout": 30000}
                    if referer:
                        goto_options["referer"] = referer
                    await page.goto(url, **goto_options)
                    # 等待字体加载完成
                    await page.evaluate(
                        """
                        async () => {
                            if (document.fonts && document.fonts.ready) {
                                await document.fonts.ready;
                            }
                        }
                        """
                    )
                    await page.wait_for_timeout(1000)

                    # 获取渲染后的文本
                    content = await page.evaluate(
                        f"""
                        () => {{
                            const elem = document.querySelector('{selector}');
                            return elem ? elem.innerText : '';
                        }}
                        """
                    )
                    return content
                finally:
                    if context is not None:
                        await context.close()
                    await runtime.close()

            # 在独立线程中使用 asyncio.run 创建新事件循环
            return asyncio.run(_browser_task())

        # 使用线程池运行浏览器操作
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = await loop.run_in_executor(executor, _run_browser_sync)
        return result

    async def fetch_chapter(
        self,
        url: str,
        book_id: str,
        chapter_id: str,
        cookie: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
        prefer_api: bool = True,
    ) -> Dict[str, Any]:
        """
        智能获取章节内容
        优先尝试API，失败则回退到浏览器

        Args:
            url: 章节URL
            book_id: 书籍ID
            chapter_id: 章节ID
            cookie: VIP登录Cookie
            prefer_api: 是否优先使用API
        """
        result = {"url": url, "content": "", "method": None, "success": False}

        # 方案一：明文API
        if prefer_api:
            try:
                api_result = await self.fetch_via_api(book_id, chapter_id, cookie, headers=headers)
                if api_result and api_result.get("code") == 0:
                    data = api_result.get("data", {})
                    result["content"] = data.get("content", "")
                    result["title"] = data.get("chapterName", "")
                    result["method"] = "api"
                    result["success"] = bool(result["content"])
                    if result["success"]:
                        return result
            except Exception as e:
                logger.warning(f"API获取失败，回退到浏览器: {e}")

        # 方案二：浏览器渲染
        try:
            content = await self.fetch_via_browser(url, cookie, headers=headers)
            result["content"] = content
            result["method"] = "browser"
            result["success"] = bool(content)
        except Exception as e:
            logger.error(f"浏览器获取失败: {e}")
            result["error"] = str(e)

        return result


# 单例
_qidian_parser: Optional[QidianVipParser] = None


def get_qidian_vip_parser() -> QidianVipParser:
    """获取起点VIP解析器单例"""
    global _qidian_parser
    if _qidian_parser is None:
        _qidian_parser = QidianVipParser()
    return _qidian_parser


def _sanitize_request_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    blocked = {
        "host",
        "content-length",
        "connection",
        "transfer-encoding",
        "accept-encoding",
    }
    output: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key).strip()
        if not name or name.startswith(":") or name.lower() in blocked:
            continue
        if value is None:
            continue
        output[name] = str(value)
    return output


def _pop_case_insensitive(headers: Dict[str, str], name: str) -> Optional[str]:
    target = name.lower()
    for key in list(headers.keys()):
        if key.lower() == target:
            return headers.pop(key)
    return None
