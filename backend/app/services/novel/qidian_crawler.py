"""
起点中文网爬虫
自动识别VIP章节并使用QidianVipParser处理字体加密
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


class QidianCrawler:
    """
    起点中文网爬虫
    - VIP章节自动使用QidianVipParser绕过字体加密
    - 免费章节使用普通HTML解析
    """

    HOST = "https://www.qidian.com"
    MOBILE_HOST = "https://m.qidian.com"

    # 章节URL匹配模式
    CHAPTER_URL_PATTERN = re.compile(
        r'qidian\.com/chapter/(\d+)/(\d+)/'
    )

    def __init__(self, cookie: Optional[str] = None):
        self.cookie = cookie
        self._vip_parser = None  # 延迟加载

    @property
    def vip_parser(self):
        """延迟加载VIP解析器"""
        if self._vip_parser is None:
            from app.services.novel.qidian_parser import QidianVipParser
            self._vip_parser = QidianVipParser()
        return self._vip_parser

    @staticmethod
    def is_vip_chapter(content: str) -> bool:
        """
        检测是否为VIP章节（被字体加密的内容）
        特征:
        1. 包含大量Unicode扩展区字符
        2. 包含 r-font-encrypt class
        """
        if 'r-font-encrypt' in content:
            return True
        content = _repair_mojibake_text(content)
        # 检测Unicode扩展B/C/D区字符（起点乱码特征）
        encrypted_chars = sum(
            1 for c in content
            if 0x3400 <= ord(c) <= 0x4DBF
            or 0x20000 <= ord(c) <= 0x2FFFF
            or 0x30000 <= ord(c) <= 0x3FFFF
            or 0xE000 <= ord(c) <= 0xF8FF
            or 0xF900 <= ord(c) <= 0xFAFF
        )
        return encrypted_chars > 50  # 大量扩展区字符视为加密内容

    def extract_book_chapter_id(self, url: str) -> Optional[Dict[str, str]]:
        """
        从章节URL提取 bookId 和 chapterId
        """
        match = self.CHAPTER_URL_PATTERN.search(url)
        if match:
            return {
                "book_id": match.group(1),
                "chapter_id": match.group(2),
            }
        return None

    async def fetch_chapter_content(
        self,
        url: str,
        cookie: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        智能获取章节内容
        - 检测到VIP章节 → 使用QidianVipParser
        - 免费章节 → 使用普通解析

        Returns:
            {"title": "...", "content": "...", "is_vip": bool, "method": "api|browser|http"}
        """
        cookie = cookie or self.cookie
        ids = self.extract_book_chapter_id(url)
        result = {
            "url": url,
            "title": "",
            "content": "",
            "is_vip": False,
            "method": None,
            "success": False,
        }

        if not ids:
            result["error"] = "无效的起点章节URL"
            return result

        # 优先尝试 API（最快，且能拿到明文）
        try:
            api_result = await self.vip_parser.fetch_via_api(
                book_id=ids["book_id"],
                chapter_id=ids["chapter_id"],
                cookie=cookie,
                headers=headers,
            )
            if api_result and api_result.get("code") == 0:
                data = api_result.get("data", {})
                result["content"] = data.get("content", "")
                result["title"] = data.get("chapterName", "")
                result["method"] = "api"
                result["success"] = bool(result["content"])
                if result["success"]:
                    return result
        except Exception as e:
            logger.warning(f"起点API获取失败，尝试浏览器: {e}")

        # 浏览器渲染（兜底方案）
        try:
            content = await self.vip_parser.fetch_via_browser(url, cookie, headers=headers)
            result["content"] = content
            result["method"] = "browser"
            result["is_vip"] = self.is_vip_chapter(content)
            result["success"] = bool(content) and not result["is_vip"]
            if content and result["is_vip"]:
                result["error"] = "qidian browser content is still font-encrypted"
        except Exception as e:
            logger.error(f"浏览器获取失败: {e}")
            result["error"] = str(e)

        return result

    # 实现BaseCrawler的同步接口
    def download_chapter(self, url: str) -> str:
        """同步下载章节内容（兼容旧接口）"""
        import asyncio
        result = asyncio.run(self.fetch_chapter_content(url))
        return result.get("content", "")

    def parse_toc(self, html: str) -> List[Dict[str, str]]:
        """解析目录"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        chapters = []
        for elem in soup.select(".volume-chapters li a"):
            chapters.append({
                "title": elem.get_text(strip=True),
                "url": urljoin(self.HOST, elem.get("href", "")),
            })
        return chapters


def _repair_mojibake_text(text: str) -> str:
    if not text:
        return ""
    markers = ("ã", "ä", "å", "æ", "è", "é", "ï¼", "ï¤", "â", "Â")
    marker_hits = sum(text.count(marker) for marker in markers)
    if marker_hits < 3 and not (len(text) >= 20 and marker_hits / len(text) > 0.05):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text
