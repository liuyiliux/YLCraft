"""
微信公众号文章 EPUB 导出

- 单篇：标题=书名，正文=一个章节
- 多篇合并：书名=自定义，每篇一个章节
- 自动把正文引用的本地图片（images/xxx）作为 EPUB 资源嵌入
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import unquote

from ebooklib import epub

logger = logging.getLogger("ylcraft.wechat_mp.epub_exporter")

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}


def build_epub(
    book_title: str,
    articles: list[dict],
    out_path: str,
    cover_image_path: str = "",
    images_base_dir: str = "",
) -> str:
    """
    构建 EPUB 并写入 out_path。

    Args:
        book_title: 书名
        articles: [{title, author, publish_time, content_html, source_url}]
                  content_html 应为已本地化图片的 HTML（图片引用 images/xxx）。
        out_path: 输出 .epub 路径
        cover_image_path: 可选封面图绝对路径
        images_base_dir: 图片所在根目录（含 images/ 子目录）；默认取 out_path 父目录

    Returns:
        out_path
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = Path(images_base_dir) if images_base_dir else out.parent

    book = epub.EpubBook()
    book.set_identifier(f"ylcraft-wechat-{book_title}")
    book.set_title(book_title)
    book.set_language("zh-CN")
    if articles:
        first_author = articles[0].get("author", "")
        if first_author:
            book.add_author(first_author)

    chapters: list[epub.EpubHtml] = []
    embedded_images: set[str] = set()

    for i, art in enumerate(articles, start=1):
        title = art.get("title") or f"第{i}章"
        content_html = art.get("content_html", "")
        file_name = f"chap_{i:03d}.xhtml"
        article_base = _article_base_dir(art, base)
        image_map: dict[str, str] = {}

        # 嵌入该章节引用的本地图片资源，并把章节内图片 src 改写为 EPUB 内部路径。
        for img_rel in _extract_local_images(content_html):
            epub_rel = _epub_image_name(i, img_rel)
            image_map[img_rel] = epub_rel
            if epub_rel not in embedded_images:
                _add_image(book, article_base, img_rel, epub_rel)
                embedded_images.add(epub_rel)

        if image_map:
            content_html = _rewrite_image_refs(content_html, image_map)

        chap = epub.EpubHtml(title=title, file_name=file_name)
        chap.set_content(f"<h1>{_escape(title)}</h1>{content_html}")

        book.add_item(chap)
        chapters.append(chap)

    # 目录 + spine
    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = ["nav", *chapters]

    # 封面
    if cover_image_path and Path(cover_image_path).exists():
        try:
            data = Path(cover_image_path).read_bytes()
            ext = Path(cover_image_path).suffix.lower() or ".jpg"
            # create_page=False：本机 ebooklib 版本的 EpubCoverHtml 分页会触发
            # lxml "Document is empty"（见 _get_nav -> get_pages_for_items），
            # 故仅嵌入封面图资源 + metadata，不生成 cover xhtml 页。
            # Apple Books / Calibre 仍会据 cover-image metadata 显示封面。
            book.set_cover(f"cover{ext}", data, create_page=False)
        except Exception as e:
            logger.warning(f"[EpubExporter] 设置封面失败（忽略）: {e}")

    epub.write_epub(str(out), book, {})
    return str(out)


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _extract_local_images(html: str) -> list[str]:
    """从 content_html 中提取本地图片引用（images/xxx 形式，相对路径）。"""
    found: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'src=["\']([^"\']*?images/[^"\']+)["\']', html or "", re.I):
        rel = m.group(1)
        idx = rel.find("images/")
        if idx >= 0:
            rel = rel[idx:]
        if rel not in seen:
            seen.add(rel)
            found.append(rel)
    return found


def _article_base_dir(article: dict, fallback: Path) -> Path:
    file_path = article.get("file_path") or ""
    if file_path:
        path = Path(file_path)
        if path.exists() and path.is_file():
            return path.parent
    return fallback


def _epub_image_name(chapter_index: int, rel: str) -> str:
    rel = unquote(rel).replace("\\", "/").lstrip("/")
    name = rel.split("images/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name) or f"image_{chapter_index}.jpg"
    return f"images/ch{chapter_index:03d}_{name}"


def _rewrite_image_refs(html: str, image_map: dict[str, str]) -> str:
    if not html or not image_map:
        return html
    for old, new in image_map.items():
        html = html.replace(old, new)
    return html


def _add_image(book: epub.EpubBook, base: Path, rel: str, epub_name: str) -> None:
    """把本地图片文件作为资源加入 EPUB。"""
    fpath = base / rel
    if not fpath.exists():
        logger.debug(f"[EpubExporter] 图片不存在，跳过: {fpath}")
        return
    try:
        ext = fpath.suffix.lower()
        media = _MEDIA_TYPES.get(ext, "image/jpeg")
        item = epub.EpubImage(
            file_name=epub_name,
            media_type=media,
            content=fpath.read_bytes(),
        )
        book.add_item(item)
    except Exception as e:
        logger.warning(f"[EpubExporter] 嵌入图片失败 {rel}: {e}")
