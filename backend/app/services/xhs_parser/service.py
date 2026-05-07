r"""
YLCraft — 小红书图文链接解析服务

解析小红书笔记链接，提取标题、正文、图片列表等信息。
优先从 window.__INITIAL_STATE__ 提取 JSON，降级到 Meta 标签和 DOM 解析。

参考：F:\workspace\图文\yiliu\backend\src\services\xiaohongshu_service.py
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("ylcraft.xhs_parser")

# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class XhsNote:
    """小红书笔记解析结果"""
    title: str = ""
    description: str = ""
    images: list[str] = field(default_factory=list)
    author: str = ""
    author_id: str = ""
    likes: int = 0
    covers: list[str] = field(default_factory=list)  # 封面图列表（取前N张）
    source_url: str = ""
    note_id: str = ""

    @property
    def cover_url(self) -> str:
        """兼容旧字段"""
        return self.images[0] if self.images else ""


# =============================================================================
# 小红书解析服务
# =============================================================================

class XhsParserService:
    """小红书图文链接解析服务"""

    # 小红书笔记 URL 格式
    NOTE_PATTERNS = [
        r"xiaohongshu\.com/explore/([a-f0-9]+)",
        r"xiaohongshu\.com/discovery/item/([a-f0-9]+)",
        r"xhs\.cn/t/([a-f0-9]+)",
    ]

    # User-Agent 池
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    ]

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.delay_range = (1.0, 3.0)

    def _random_ua(self) -> str:
        return random.choice(self.USER_AGENTS)

    def _delay(self):
        """随机延迟，模拟真实用户"""
        time.sleep(random.uniform(*self.delay_range))

    def _get_headers(self, referer: str = "https://www.xiaohongshu.com/") -> dict:
        return {
            "User-Agent": self._random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": referer,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def _extract_note_id(self, url: str) -> Optional[str]:
        """从 URL 中提取笔记 ID"""
        for pattern in self.NOTE_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    # -------------------------------------------------------------------------
    # 核心解析方法
    # -------------------------------------------------------------------------

    def parse(self, url: str) -> Optional[XhsNote]:
        """
        解析小红书笔记链接。

        Args:
            url: 小红书笔记链接（支持多种格式）

        Returns:
            XhsNote 对象，解析失败返回 None
        """
        note_id = self._extract_note_id(url)
        if not note_id:
            logger.warning(f"[XhsParser] 无法从 URL 提取笔记 ID: {url}")
            return None

        logger.info(f"[XhsParser] 开始解析笔记: note_id={note_id}")
        self._delay()

        # 发送请求
        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout,
                allow_redirects=True,
            )
            if response.status_code != 200:
                logger.error(f"[XhsParser] HTTP {response.status_code}: {url}")
                return None
        except requests.RequestException as e:
            logger.error(f"[XhsParser] 请求失败: {e}")
            return None

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # 策略1: window.__INITIAL_STATE__（最准确）
        note = self._parse_initial_state(soup, url, note_id)
        if note and (note.title or note.description or note.images):
            logger.info(f"[XhsParser] ✅ INITIAL_STATE 解析成功: {note.title[:30]}")
            return note

        # 策略2: Meta og: 标签（兜底信息）
        note = self._parse_meta_tags(soup, url)
        if note.title or note.description:
            logger.info(f"[XhsParser] ⚠️ Meta 标签解析: {note.title[:30]}")
            return note

        logger.warning(f"[XhsParser] ❌ 所有解析策略均失败: {url}")
        return None

    def _parse_initial_state(
        self, soup: BeautifulSoup, url: str, note_id: str
    ) -> Optional[XhsNote]:
        """策略1: 从 window.__INITIAL_STATE__ 提取 JSON 数据"""
        scripts = soup.find_all("script")

        for script in scripts:
            text = script.string or ""
            if "window.__INITIAL_STATE__" not in text:
                continue

            try:
                # 提取 JSON 字符串
                json_str = text.replace("window.__INITIAL_STATE__=", "").replace(
                    "undefined", "null"
                )
                if json_str.strip().endswith(";"):
                    json_str = json_str.strip()[:-1]

                data = json.loads(json_str)

                # 查找笔记数据 — 多种路径兼容
                note_data = None
                detail_map = None

                # 路径 A: note.noteDetailMap[noteId]
                if "note" in data and "noteDetailMap" in data["note"]:
                    detail_map = data["note"]["noteDetailMap"]
                    note_data = detail_map.get(note_id)
                    if not note_data:
                        # 尝试遍历
                        for k, v in detail_map.items():
                            if isinstance(v, dict) and v.get("note", {}).get("noteId") == note_id:
                                note_data = v.get("note")
                                break

                # 路径 B: note.note（直接）
                if not note_data and "note" in data and "note" in data["note"]:
                    note_data = data["note"]["note"]

                # 路径 C: note.firstNote
                if not note_data and "note" in data and "firstNote" in data["note"]:
                    note_data = data["note"]["firstNote"]

                if not note_data:
                    continue

                # 解包嵌套结构
                if isinstance(note_data, dict) and "note" in note_data:
                    note_data = note_data["note"]

                # 提取字段
                title = note_data.get("title", "") or note_data.get("displayTitle", "")
                description = note_data.get("desc", "") or note_data.get("description", "")

                # 图片列表
                images = []
                image_list = note_data.get("imageList") or note_data.get("imagesList") or []
                for img in image_list:
                    img_url = (
                        img.get("urlDefault")
                        or img.get("url")
                        or (img.get("infoList", [{}])[0].get("url") if img.get("infoList") else "")
                    )
                    if img_url:
                        if img_url.startswith("//"):
                            img_url = "https:" + img_url
                        images.append(img_url)

                # 作者信息
                user = note_data.get("user", {})
                author = user.get("nickname", "")
                author_id = user.get("userId", "") or user.get("id", "")

                # 点赞数
                interact = note_data.get("interactInfo", {}) or {}
                likes = note_data.get("likedCount", 0) or interact.get("likedCount", 0) or 0

                return XhsNote(
                    title=title,
                    description=description,
                    images=images,
                    covers=images[:9],  # 取前9张
                    author=author,
                    author_id=author_id,
                    likes=int(likes) if likes else 0,
                    source_url=url,
                    note_id=note_id,
                )

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"[XhsParser] INITIAL_STATE 解析异常: {e}")
                continue

        return None

    def _parse_meta_tags(
        self, soup: BeautifulSoup, url: str
    ) -> Optional[XhsNote]:
        """策略2: 从 Meta og: 标签提取兜底信息"""
        title = ""
        description = ""
        cover_url = ""

        # og:title
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "")

        # og:description
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", "")

        # og:image
        og_image = soup.find("meta", property="og:image")
        if og_image:
            cover_url = og_image.get("content", "")
            if cover_url.startswith("//"):
                cover_url = "https:" + cover_url

        # 如果 title 还是空的，尝试 title tag
        if not title and soup.title:
            title = soup.title.string.replace(" - 小红书", "").strip()

        if not title:
            return None

        return XhsNote(
            title=title,
            description=description,
            images=[cover_url] if cover_url else [],
            covers=[cover_url] if cover_url else [],
            source_url=url,
        )


# =============================================================================
# 全局实例
# =============================================================================

_xhs_parser: Optional[XhsParserService] = None


def get_xhs_parser() -> XhsParserService:
    global _xhs_parser
    if _xhs_parser is None:
        _xhs_parser = XhsParserService()
    return _xhs_parser
