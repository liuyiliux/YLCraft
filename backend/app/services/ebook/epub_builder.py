"""
EPUB 构建器 — 将 Markdown/HTML 文件集合打包为 EPUB 电子书
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ylcraft.ebook.builder")


class EpubBuilder:
    """
    EPUB 构建器

    将文件夹中的 Markdown/HTML 文件收集后生成 EPUB 电子书。
    """

    def __init__(self, title: str = "", author: str = "YLCraft", language: str = "zh"):
        self.title = title or "未命名电子书"
        self.author = author
        self.language = language
        self._cover_path: str = ""
        self._chapters: list[dict] = []
        self._output_path: str = ""

    # ── 内容收集 ────────────────────────────────────────────────

    def collect_from_folder(self, folder_path: str) -> int:
        """
        从文件夹收集 Markdown/HTML 文件作为章节

        Returns:
            收集到的章节数
        """
        self._chapters.clear()
        folder = Path(folder_path)
        if not folder.exists():
            logger.warning(f"[EpubBuilder] 文件夹不存在: {folder_path}")
            return 0

        # 收集支持的文件
        files = sorted(
            [f for f in folder.iterdir() if f.suffix.lower() in (".md", ".html", ".htm", ".txt")],
            key=lambda f: f.name,
        )

        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                self._chapters.append({
                    "title": f.stem,
                    "file_name": f.name,
                    "content": content,
                    "is_markdown": f.suffix.lower() == ".md",
                })
            except Exception as e:
                logger.warning(f"[EpubBuilder] 读取文件失败 {f.name}: {e}")

        logger.info(f"[EpubBuilder] 从 {folder_path} 收集到 {len(self._chapters)} 个章节")
        return len(self._chapters)

    def set_chapters(self, chapters: list[dict]) -> None:
        """手动设置章节列表 [{title, content, is_markdown}]"""
        self._chapters = chapters

    def set_cover(self, cover_path: str) -> None:
        self._cover_path = cover_path

    # ── 生成 ────────────────────────────────────────────────────

    def build(self, output_dir: str = "") -> str:
        """
        构建 EPUB 文件

        Returns:
            生成的 .epub 文件路径
        """
        try:
            from ebooklib import epub
        except ImportError:
            raise ImportError(
                "需要安装 ebooklib: pip install ebooklib>=0.18.0"
            )

        import markdown as md_lib

        book = epub.EpubBook()
        book.set_identifier(str(uuid.uuid4()))
        book.set_title(self.title)
        book.set_language(self.language)
        book.add_author(self.author)

        # CSS 样式
        style = """
        body { font-family: "PingFang SC", "Microsoft YaHei", sans-serif; line-height: 1.8; margin: 1em; }
        h1, h2, h3 { color: #333; }
        img { max-width: 100%; height: auto; }
        pre { background: #f5f5f5; padding: 1em; border-radius: 4px; overflow-x: auto; }
        blockquote { border-left: 3px solid #07C160; padding-left: 1em; color: #666; margin: 1em 0; }
        """
        css = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=style)
        book.add_item(css)

        # 封面
        if self._cover_path and os.path.exists(self._cover_path):
            with open(self._cover_path, "rb") as f:
                book.set_cover("cover.jpg", f.read())

        # 章节
        spine = ["nav"]
        epub_chapters = []
        for i, ch in enumerate(self._chapters):
            c = epub.EpubHtml(
                title=ch["title"],
                file_name=f"chapter_{i+1}.xhtml",
                lang=self.language,
            )

            content = ch["content"]
            if ch.get("is_markdown"):
                try:
                    content = md_lib.markdown(content, extensions=["extra", "codehilite"])
                except Exception:
                    pass

            c.content = f"<h2>{ch['title']}</h2>\n{content}"
            c.add_item(css)
            book.add_item(c)
            epub_chapters.append(c)
            spine.append(c)

        # 目录
        book.toc = [(epub.EpubSection(self.title), epub_chapters)]

        # navigation
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = spine

        # 输出路径
        safe_title = "".join(c for c in self.title if c.isalnum() or c in "._- ()（）")[:60]
        if not output_dir:
            output_dir = os.getcwd()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._output_path = str(output_dir / f"{safe_title}.epub")
        epub.write_epub(self._output_path, book)
        logger.info(f"[EpubBuilder] EPUB 已生成: {self._output_path}")

        return self._output_path

    @property
    def output_path(self) -> str:
        return self._output_path

    @property
    def chapter_count(self) -> int:
        return len(self._chapters)
