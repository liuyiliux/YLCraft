"""
微信公众号文章解析器

从 HTML 中提取结构化内容：标题、正文、图片、作者、发布时间等。
使用 BeautifulSoup 解析，避免正则截断嵌套标签导致的丢内容问题。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from html import unescape
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger("ylcraft.wechat_mp.parser")

# 选择可用的解析后端：优先 lxml，缺失时退回标准库 html.parser
try:
    import lxml  # noqa: F401
    _PARSER = "lxml"
except ImportError:  # pragma: no cover
    _PARSER = "html.parser"


class WechatMPParser:
    """
    微信文章 HTML 解析器

    从 mp.weixin.qq.com 的文章 HTML 中提取结构化信息。
    """

    # 微信文章正文容器 ID
    JS_CONTENT_ID = "js_content"

    # 微信特有音视频/卡片标签，降级为占位文本
    _CARD_TAGS = {
        "mpvoice", "mpvideosnap", "mpvideo", "mp-common-mpaudio",
        "mp-common-mpmusic", "mp-common-profile",
    }

    def parse(self, html: str, article_url: str = "") -> dict:
        """
        解析文章 HTML

        Returns:
            {
                title, author, publish_time, content_html, content_text,
                images[], cover, source_url, article_url, error
            }
        """
        result = {
            "title": "",
            "author": "",
            "publish_time": "",
            "content_html": "",
            "content_text": "",
            "images": [],
            "cover": "",
            "source_url": "",
            "article_url": article_url,
            "error": "",
        }

        if not html:
            result["error"] = "HTML 为空"
            return result

        try:
            soup = self._make_soup(html)

            result["title"] = self._extract_title(soup, html)
            result["author"] = self._extract_author(soup, html)
            result["publish_time"] = self._extract_publish_time(soup, html)
            result["content_html"] = self._extract_content_html(soup)
            result["content_text"] = self._strip_html(result["content_html"])
            result["images"] = self._extract_images(soup)
            result["cover"] = self._extract_cover(soup)
            result["source_url"] = self._extract_source_url(soup)
        except Exception as e:
            logger.error(f"[WechatMPParser] 解析异常: {e}")
            result["error"] = str(e)

        return result

    # ── 解析后端 ──────────────────────────────────────────────

    @staticmethod
    def _make_soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, _PARSER)

    # ── 提取方法 ──────────────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup, html: str) -> str:
        node = soup.find("meta", attrs={"property": "og:title"})
        if node and node.get("content"):
            return unescape(node["content"]).strip()
        node = soup.find(id="activity-name")
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
        if soup.title and soup.title.get_text(strip=True):
            return soup.title.get_text(strip=True)
        # 兜底正则
        m = re.search(r"<title>([^<]+)</title>", html, re.I)
        return unescape(m.group(1)).strip() if m else ""

    def _extract_author(self, soup: BeautifulSoup, html: str) -> str:
        node = soup.find(id="js_name")
        if node:
            txt = node.get_text(strip=True)
            if txt:
                return txt
        node = soup.find("meta", attrs={"name": "author"})
        if node and node.get("content"):
            return unescape(node["content"]).strip()
        m = re.search(r'<meta[^>]+name="author"[^>]+content="([^"]+)"', html, re.I)
        return unescape(m.group(1)).strip() if m else ""

    def _extract_publish_time(self, soup: BeautifulSoup, html: str) -> str:
        # var ct = "1234567890"（脚本变量，正则最稳）
        m = re.search(r'var\s+ct\s*=\s*["\'](\d{10})["\']', html)
        if m:
            ts = int(m.group(1))
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        node = soup.find(id="publish_time")
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
        return ""

    def _extract_content_html(self, soup: BeautifulSoup) -> str:
        node = soup.find("div", id=self.JS_CONTENT_ID)
        if not node:
            return ""
        # 移除隐藏节点（visibility:hidden / display:none）
        for tag in list(node.find_all(True)):
            style = (tag.get("style") or "").replace(" ", "").lower()
            if "visibility:hidden" in style or "display:none" in style:
                tag.decompose()
        return node.decode_contents()

    def _extract_images(self, soup: BeautifulSoup) -> list[str]:
        """提取文章中的图片 URL（data-src 优先）"""
        images: list[str] = []
        seen: set[str] = set()
        for img in soup.find_all("img"):
            url = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("src")
                or ""
            )
            if not url or url.startswith("data:"):
                continue
            low = url.lower()
            if "avatar" in low or "icon" in low:
                continue
            if url not in seen:
                seen.add(url)
                images.append(url)
        return images

    def _extract_cover(self, soup: BeautifulSoup) -> str:
        node = soup.find("meta", attrs={"property": "og:image"})
        if node and node.get("content"):
            return node["content"]
        return ""

    def _extract_source_url(self, soup: BeautifulSoup) -> str:
        node = soup.find(id="js_source_url")
        if node and node.get("href"):
            return unescape(node["href"])
        return ""

    # ── 工具方法 ──────────────────────────────────────────────

    def _strip_html(self, html: str) -> str:
        """移除 HTML 标签，保留纯文本"""
        if not html:
            return ""
        return self._make_soup(html).get_text(separator=" ")

    def _html_to_markdown(self, html: str) -> str:
        """
        将 HTML 正文转换为 Markdown 格式（基于节点遍历）。
        保留段落、标题、加粗、斜体、链接、列表、代码块、引用、表格等。
        """
        if not html:
            return ""
        soup = self._make_soup(html)
        md = self._render_node(soup)
        md = re.sub(r"[ \t]+\n", "\n", md)
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md.strip()

    def _render_node(self, node) -> str:
        """递归渲染 BeautifulSoup 节点为 Markdown 文本"""
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ""

        name = node.name.lower()
        if name in ("script", "style"):
            return ""
        if name in self._CARD_TAGS:
            return "\n（音视频卡片）\n"

        inner = "".join(self._render_node(c) for c in node.children)

        if name == "p":
            return f"\n\n{inner}\n\n"
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1])
            return f"\n\n{'#' * level} {inner.strip()}\n\n"
        if name in ("strong", "b"):
            return f"**{inner.strip()}**" if inner.strip() else inner
        if name in ("em", "i"):
            return f"*{inner.strip()}*" if inner.strip() else inner
        if name == "a":
            href = node.get("href", "")
            text = inner.strip()
            return f"[{text}]({href})" if href and text else text
        if name == "img":
            src = (
                node.get("data-src")
                or node.get("data-original")
                or node.get("src")
                or ""
            )
            return f"\n![图片]({src})\n" if src else ""
        if name == "br":
            return "\n"
        if name == "hr":
            return "\n\n---\n\n"
        if name == "pre":
            return f"\n\n```\n{inner.strip()}\n```\n\n"
        if name == "blockquote":
            lines = inner.strip().splitlines() or [""]
            return "\n" + "\n".join(f"> {ln}" for ln in lines) + "\n"
        if name in ("ul", "ol"):
            return self._render_list(node, ordered=(name == "ol"))
        if name == "li":
            return f"- {inner.strip()}\n"
        if name == "table":
            return self._render_table(node)
        if name in ("thead", "tbody", "tfoot", "tr", "td", "th"):
            return inner
        if name == "section":
            # 微信排版核心标签：保留子节点内容，不输出自身
            return inner
        if name == "div":
            return f"{inner}\n"
        return inner

    def _render_list(self, node: Tag, ordered: bool) -> str:
        items: list[str] = []
        idx = 1
        for li in node.find_all("li", recursive=False):
            txt = "".join(self._render_node(c) for c in li.children).strip()
            txt = re.sub(r"\s+", " ", txt)
            if ordered:
                items.append(f"{idx}. {txt}")
                idx += 1
            else:
                items.append(f"- {txt}")
        return "\n" + "\n".join(items) + "\n" if items else ""

    def _render_table(self, node: Tag) -> str:
        rows = node.find_all("tr")
        if not rows:
            return ""
        table: list[list[str]] = []
        for r in rows:
            cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            if cells:
                table.append(cells)
        if not table:
            return ""
        header = table[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        for row in table[1:]:
            row = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(row) + " |")
        return "\n\n" + "\n".join(lines) + "\n\n"

    def to_markdown(self, parse_result: dict) -> str:
        """
        将解析结果转为 Markdown

        Args:
            parse_result: parse() 的返回值

        Returns:
            Markdown 格式字符串
        """
        lines = []

        title = parse_result.get("title", "无标题")
        lines.append(f"# {title}")
        lines.append("")

        author = parse_result.get("author", "")
        pub_time = parse_result.get("publish_time", "")
        source = parse_result.get("source_url", "")
        article_url = parse_result.get("article_url", "")

        if author:
            lines.append(f"**作者**: {author}")
        if pub_time:
            lines.append(f"**发布时间**: {pub_time}")
        if article_url:
            lines.append(f"**原文链接**: [{title}]({article_url})")
        if source:
            lines.append(f"**来源**: {source}")
        lines.append("")
        lines.append("---")
        lines.append("")

        content_html = parse_result.get("content_html", "")
        if content_html:
            lines.append(self._html_to_markdown(content_html))
        else:
            lines.append("> 暂无正文内容")

        lines.append("")
        return "\n".join(lines)
