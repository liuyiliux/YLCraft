"""
微信公众号文章解析器

从 HTML 中提取结构化内容：标题、正文、图片、作者、发布时间等。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from html import unescape
from typing import Optional

logger = logging.getLogger("ylcraft.wechat_mp.parser")


class WechatMPParser:
    """
    微信文章 HTML 解析器

    从 mp.weixin.qq.com 的文章 HTML 中提取结构化信息。
    """

    # 微信文章正文容器 ID
    JS_CONTENT_ID = "js_content"

    def parse(self, html: str, article_url: str = "") -> dict:
        """
        解析文章 HTML

        Returns:
            {
                title, author, publish_time, content_html,
                content_text, images[], cover, source_url
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
            "error": "",
        }

        if not html:
            result["error"] = "HTML 为空"
            return result

        try:
            # 标题 — 从 <title> 或 og:title 提取
            result["title"] = self._extract_title(html)

            # 作者 — 从 meta 或 var 提取
            result["author"] = self._extract_author(html)

            # 发布时间 — 从 var ct 或 meta 提取
            result["publish_time"] = self._extract_publish_time(html)

            # 正文 HTML — 从 js_content div 提取
            result["content_html"] = self._extract_content_html(html)

            # 正文纯文本
            result["content_text"] = self._strip_html(result["content_html"])

            # 图片列表
            result["images"] = self._extract_images(html)

            # 封面图
            result["cover"] = self._extract_cover(html)

            # 原文链接
            result["source_url"] = self._extract_source_url(html)

        except Exception as e:
            logger.error(f"[WechatMPParser] 解析异常: {e}")
            result["error"] = str(e)

        return result

    # ── 提取方法 ──────────────────────────────────────────────

    def _extract_title(self, html: str) -> str:
        # 优先 og:title
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html, re.I)
        if m:
            return unescape(m.group(1)).strip()
        # 其次 activity-name
        m = re.search(r'id="activity-name"[^>]*>([^<]+)<', html, re.I)
        if m:
            return unescape(m.group(1)).strip()
        # 最后 <title>
        m = re.search(r"<title>([^<]+)</title>", html, re.I)
        if m:
            return unescape(m.group(1)).strip()
        return ""

    def _extract_author(self, html: str) -> str:
        # 公众号名称
        m = re.search(r'id="js_name"[^>]*>([^<]+)<', html, re.I)
        if m:
            return unescape(m.group(1)).strip()
        # 从 meta author
        m = re.search(r'<meta[^>]+name="author"[^>]+content="([^"]+)"', html, re.I)
        if m:
            return unescape(m.group(1)).strip()
        return ""

    def _extract_publish_time(self, html: str) -> str:
        # var ct = "1234567890"
        m = re.search(r'var\s+ct\s*=\s*["\'](\d{10})["\']', html)
        if m:
            ts = int(m.group(1))
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        # id="publish_time"
        m = re.search(r'id="publish_time"[^>]*>([^<]+)<', html, re.I)
        if m:
            return m.group(1).strip()
        return ""

    def _extract_content_html(self, html: str) -> str:
        # 提取 js_content div
        m = re.search(
            r'<div[^>]+id="js_content"[^>]*>(.*?)</div>\s*(?:<script|<div[^>]+id="js_pc_qr_code"|$)',
            html, re.I | re.DOTALL,
        )
        if m:
            content = m.group(1).strip()
            # 移除 style="visibility: hidden;"
            content = re.sub(r'style="[^"]*visibility\s*:\s*hidden[^"]*"', "", content, flags=re.I)
            return content
        return ""

    def _extract_images(self, html: str) -> list[str]:
        """提取文章中的图片 URL（data-src 优先）"""
        images = []
        for m in re.finditer(r'<img[^>]+data-src="([^"]+)"', html, re.I):
            url = m.group(1)
            if url and not url.startswith("data:"):
                images.append(url)
        # 如果没 data-src，用 src
        if not images:
            for m in re.finditer(r'<img[^>]+src="(https?://[^"]+)"', html, re.I):
                url = m.group(1)
                if url and "avatar" not in url.lower() and "icon" not in url.lower():
                    images.append(url)
        return images

    def _extract_cover(self, html: str) -> str:
        """提取封面图"""
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html, re.I)
        if m:
            return m.group(1)
        return ""

    def _extract_source_url(self, html: str) -> str:
        """提取原文链接"""
        m = re.search(r'id="js_source_url"[^>]+href="([^"]+)"', html, re.I)
        if m:
            return unescape(m.group(1))
        return ""

    # ── 工具方法 ──────────────────────────────────────────────

    def _strip_html(self, html: str) -> str:
        """移除 HTML 标签，保留纯文本"""
        if not html:
            return ""
        text = re.sub(r"<[^>]+>", "", html)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def to_markdown(self, parse_result: dict) -> str:
        """
        将解析结果转为 Markdown

        Args:
            parse_result: parse() 的返回值

        Returns:
            Markdown 格式字符串
        """
        lines = []

        # 标题
        title = parse_result.get("title", "无标题")
        lines.append(f"# {title}")
        lines.append("")

        # 元信息
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

        # 正文（纯文本版）
        content = parse_result.get("content_text", "")
        if content:
            lines.append(content)
        else:
            lines.append("> 暂无正文内容")

        lines.append("")

        # 图片
        images = parse_result.get("images", [])
        if images:
            lines.append("## 图片")
            lines.append("")
            for i, img_url in enumerate(images):
                lines.append(f"![图片 {i + 1}]({img_url})")
                lines.append("")

        return "\n".join(lines)
