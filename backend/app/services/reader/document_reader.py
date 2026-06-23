"""Safe local document reading for Markdown, HTML, text, and EPUB files."""

from __future__ import annotations

import base64
import html
import mimetypes
import os
import posixpath
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from bs4 import BeautifulSoup

from app.core.config import ensure_download_path


class ReaderError(ValueError):
    """Raised when a local document cannot be read safely."""


class DocumentReaderService:
    """Read documents from the configured downloads directory."""

    _IMAGE_EXTENSIONS = {
        ".avif",
        ".bmp",
        ".gif",
        ".jpeg",
        ".jpg",
        ".png",
        ".svg",
        ".webp",
    }
    _SUPPORTED_EXTENSIONS = {
        ".epub",
        ".htm",
        ".html",
        ".markdown",
        ".md",
        ".text",
        ".txt",
    }
    _DANGEROUS_TAGS = {
        "base",
        "embed",
        "form",
        "iframe",
        "input",
        "link",
        "meta",
        "object",
        "script",
        "select",
        "style",
        "textarea",
    }

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or ensure_download_path()).resolve()

    def read(self, file_path: str) -> dict[str, Any]:
        path = self.resolve_document_path(file_path)
        suffix = path.suffix.lower()

        if suffix not in self._SUPPORTED_EXTENSIONS:
            raise ReaderError(f"暂不支持预览 {suffix or '未知'} 格式")

        if suffix == ".epub":
            title, chapters = self._read_epub(path)
        else:
            raw = path.read_text(encoding="utf-8", errors="ignore")
            if suffix in {".md", ".markdown"}:
                title = self._extract_markdown_title(raw) or path.stem
                content = self._markdown_to_html(raw)
            elif suffix in {".html", ".htm"}:
                title = self._extract_html_title(raw) or path.stem
                content = self._extract_body_content(raw)
            else:
                title = path.stem
                content = self._plain_text_to_html(raw)

            content = self._sanitize_html(content, base_dir=path.parent)
            chapters = [{
                "id": "main",
                "title": title,
                "content": content,
                "content_type": "html",
                "order": 0,
            }]

        if not chapters:
            raise ReaderError("文件中没有可预览的正文内容")

        stat = path.stat()
        return {
            "success": True,
            "title": title or path.stem,
            "root_path": str(self.root),
            "file_path": str(path),
            "file_name": path.name,
            "format": suffix.lstrip("."),
            "file_size": stat.st_size,
            "modified_at": stat.st_mtime,
            "chapters": chapters,
        }

    def read_many(self, file_paths: list[str], title: str = "") -> dict[str, Any]:
        paths = [p for p in file_paths if p]
        if not paths:
            raise ReaderError("缺少文件路径")
        if len(paths) == 1:
            return self.read(paths[0])

        docs = [self.read(p) for p in paths]
        chapters: list[dict[str, Any]] = []
        total_size = 0
        newest_mtime = 0.0

        for doc in docs:
            total_size += int(doc.get("file_size") or 0)
            newest_mtime = max(newest_mtime, float(doc.get("modified_at") or 0))
            for chapter in doc.get("chapters") or []:
                chapter_title = chapter.get("title") or doc.get("title") or "未命名文章"
                chapters.append({
                    **chapter,
                    "id": f"{len(chapters)}-{chapter.get('id') or doc.get('file_name')}",
                    "title": chapter_title,
                    "order": len(chapters),
                })

        return {
            "success": True,
            "title": title or f"本地文章合集（{len(docs)} 篇）",
            "root_path": str(self.root),
            "file_path": docs[0].get("file_path", ""),
            "file_name": f"{len(docs)} 个文件",
            "format": "collection",
            "file_size": total_size,
            "modified_at": newest_mtime,
            "chapters": chapters,
        }

    def browse(self, directory: str = "") -> dict[str, Any]:
        current = self._resolve_browse_directory(directory)
        parent_relative_path = ""
        if current != self.root:
            parent_relative_path = self._relative_path(current.parent)

        items: list[dict[str, Any]] = []
        try:
            children = list(current.iterdir())
        except OSError as exc:
            raise ReaderError(f"读取目录失败: {exc}") from exc

        for child in children:
            if child.name.startswith("."):
                continue
            try:
                stat = child.stat()
            except OSError:
                continue

            is_dir = child.is_dir()
            suffix = child.suffix.lower()
            readable = child.is_file() and suffix in self._SUPPORTED_EXTENSIONS
            if not is_dir and not readable:
                continue

            items.append({
                "name": child.name,
                "path": str(child.resolve()),
                "relative_path": self._relative_path(child),
                "is_dir": is_dir,
                "readable": readable,
                "format": "folder" if is_dir else suffix.lstrip("."),
                "file_size": 0 if is_dir else stat.st_size,
                "modified_at": stat.st_mtime,
            })

        items.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
        return {
            "success": True,
            "root_path": str(self.root),
            "current_path": str(current),
            "current_relative_path": self._relative_path(current),
            "parent_relative_path": parent_relative_path,
            "items": items,
            "supported_formats": sorted(ext.lstrip(".") for ext in self._SUPPORTED_EXTENSIONS),
        }

    def delete_item(self, target_path: str, recursive: bool = False) -> dict[str, Any]:
        path = self._resolve_delete_target(target_path)
        if path == self.root:
            raise ReaderError("不能删除下载根目录")
        if not path.exists():
            raise ReaderError("文件或文件夹不存在")

        is_dir = path.is_dir()
        if is_dir and not recursive:
            raise ReaderError("删除文件夹需要确认递归删除")
        if not is_dir and not path.is_file():
            raise ReaderError("只能删除文件或文件夹")

        relative_path = self._relative_path(path)
        parent_relative_path = self._relative_path(path.parent)
        if is_dir:
            deleted_files, deleted_dirs, freed_size = self._directory_stats(path)
            try:
                shutil.rmtree(path)
            except OSError as exc:
                raise ReaderError(f"删除文件夹失败: {exc}") from exc
        else:
            try:
                freed_size = path.stat().st_size
                path.unlink()
            except OSError as exc:
                raise ReaderError(f"删除文件失败: {exc}") from exc
            deleted_files = 1
            deleted_dirs = 0

        return {
            "success": True,
            "path": str(path),
            "relative_path": relative_path,
            "parent_relative_path": parent_relative_path,
            "is_dir": is_dir,
            "deleted_files": deleted_files,
            "deleted_dirs": deleted_dirs,
            "freed_size": freed_size,
            "message": "已删除文件夹" if is_dir else "已删除文件",
        }

    def resolve_document_path(self, file_path: str) -> Path:
        path = self._resolve_under_root(file_path)
        if not path.exists() or not path.is_file():
            raise ReaderError("文件不存在")
        return path

    def resolve_image_path(self, file_path: str) -> Path:
        path = self.resolve_document_path(file_path)
        if path.suffix.lower() not in self._IMAGE_EXTENSIONS:
            raise ReaderError("只允许预览下载目录内的图片资源")
        return path

    def _resolve_under_root(self, file_path: str) -> Path:
        if not file_path:
            raise ReaderError("缺少文件路径")

        raw = unquote(file_path).strip()
        path = Path(raw)
        if not path.is_absolute():
            path = self.root / path

        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ReaderError("只能读取下载目录内的文件") from exc
        return resolved

    def _resolve_delete_target(self, target_path: str) -> Path:
        if not target_path:
            raise ReaderError("缺少文件路径")

        raw = unquote(target_path).strip()
        path = Path(raw)
        if not path.is_absolute():
            path = self.root / path

        candidate = Path(os.path.abspath(path))
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ReaderError("只能删除下载目录内的文件") from exc

        if self._path_contains_symlink(candidate):
            raise ReaderError("不支持删除符号链接")

        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ReaderError("只能删除下载目录内的文件") from exc
        return candidate

    def _resolve_browse_directory(self, directory: str) -> Path:
        if directory:
            path = self._resolve_under_root(directory)
        else:
            path = self.root
        if not path.exists() or not path.is_dir():
            raise ReaderError("目录不存在")
        return path

    def _relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            rel = resolved.relative_to(self.root)
        except ValueError as exc:
            raise ReaderError("只能浏览下载目录内的文件") from exc
        value = str(rel).replace("\\", "/")
        return "" if value == "." else value

    @staticmethod
    def _directory_stats(path: Path) -> tuple[int, int, int]:
        files = 0
        dirs = 1
        size = 0
        for current, dirnames, filenames in os.walk(path, followlinks=False):
            dirs += len(dirnames)
            for filename in filenames:
                files += 1
                try:
                    size += Path(current, filename).lstat().st_size
                except OSError:
                    continue
        return files, dirs, size

    def _path_contains_symlink(self, path: Path) -> bool:
        current = path
        while True:
            try:
                current.relative_to(self.root)
            except ValueError:
                return False
            try:
                if current.is_symlink():
                    return True
            except OSError:
                return True
            if current == self.root:
                return False
            current = current.parent

    def _read_epub(self, path: Path) -> tuple[str, list[dict[str, Any]]]:
        try:
            from ebooklib import ITEM_DOCUMENT, epub
        except ImportError as exc:
            raise ReaderError("后端缺少 ebooklib，无法预览 EPUB") from exc

        try:
            book = epub.read_epub(str(path))
        except Exception as exc:
            raise ReaderError(f"EPUB 解析失败: {exc}") from exc

        title = self._epub_title(book) or path.stem
        item_lookup = {
            self._normalize_epub_name(item.get_name()): item
            for item in book.get_items()
            if item.get_name()
        }

        docs = []
        seen_names: set[str] = set()
        for spine_item in getattr(book, "spine", []) or []:
            idref = spine_item[0] if isinstance(spine_item, tuple) else spine_item
            item = book.get_item_with_id(idref)
            if item is None:
                continue
            name = self._normalize_epub_name(item.get_name())
            if name and name not in seen_names:
                seen_names.add(name)
                docs.append(item)

        if not docs:
            docs = list(book.get_items_of_type(ITEM_DOCUMENT))

        chapters: list[dict[str, Any]] = []
        for item in docs:
            name = self._normalize_epub_name(item.get_name())
            if not name or name.lower().endswith(("nav.xhtml", "toc.xhtml")):
                continue

            raw = item.get_content().decode("utf-8", errors="ignore")
            body = self._extract_body_content(raw)
            body = self._rewrite_epub_refs(body, name, item_lookup)
            body = self._sanitize_html(body)

            text = BeautifulSoup(body, "html.parser").get_text(strip=True)
            if not text and "<img" not in body:
                continue

            chapter_title = self._extract_chapter_heading(raw) or f"第 {len(chapters) + 1} 章"
            chapters.append({
                "id": name or f"chapter-{len(chapters)}",
                "title": chapter_title,
                "content": body,
                "content_type": "html",
                "order": len(chapters),
            })

        return title, chapters

    def _markdown_to_html(self, text: str) -> str:
        try:
            import markdown as markdown_lib

            return markdown_lib.markdown(
                text,
                extensions=["extra", "fenced_code", "sane_lists", "tables"],
                output_format="html5",
            )
        except Exception:
            return self._basic_markdown_to_html(text)

    def _basic_markdown_to_html(self, text: str) -> str:
        blocks: list[str] = []
        paragraph: list[str] = []
        code_lines: list[str] = []
        in_code = False
        list_type: str | None = None

        def inline(value: str) -> str:
            escaped = html.escape(value)
            escaped = re.sub(
                r"!\[([^\]]*)\]\(([^)]+)\)",
                lambda m: f'<img alt="{m.group(1)}" src="{html.escape(m.group(2), quote=True)}" />',
                escaped,
            )
            escaped = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
                escaped,
            )
            escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
            escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
            return escaped

        def flush_paragraph() -> None:
            nonlocal paragraph
            if paragraph:
                blocks.append(f"<p>{inline(' '.join(paragraph))}</p>")
                paragraph = []

        def close_list() -> None:
            nonlocal list_type
            if list_type:
                blocks.append(f"</{list_type}>")
                list_type = None

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code:
                    blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                    code_lines = []
                    in_code = False
                else:
                    flush_paragraph()
                    close_list()
                    in_code = True
                continue

            if in_code:
                code_lines.append(line)
                continue

            if not stripped:
                flush_paragraph()
                close_list()
                continue

            heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading:
                flush_paragraph()
                close_list()
                level = len(heading.group(1))
                blocks.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
                continue

            unordered = re.match(r"^[-*+]\s+(.+)$", stripped)
            ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
            if unordered or ordered:
                flush_paragraph()
                target = "ul" if unordered else "ol"
                if list_type != target:
                    close_list()
                    blocks.append(f"<{target}>")
                    list_type = target
                value = (unordered or ordered).group(1)
                blocks.append(f"<li>{inline(value)}</li>")
                continue

            paragraph.append(stripped)

        if in_code:
            blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
        flush_paragraph()
        close_list()
        return "\n".join(blocks)

    def _plain_text_to_html(self, text: str) -> str:
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        return "\n".join(f"<p>{html.escape(p).replace(chr(10), '<br />')}</p>" for p in paragraphs)

    def _sanitize_html(self, content: str, base_dir: Path | None = None) -> str:
        soup = BeautifulSoup(content or "", "html.parser")

        for tag in soup.find_all(self._DANGEROUS_TAGS):
            tag.decompose()

        for tag in soup.find_all(True):
            for attr in list(tag.attrs):
                lower = attr.lower()
                value = tag.get(attr)
                value_text = " ".join(value) if isinstance(value, list) else str(value or "")
                if lower.startswith("on") or lower == "srcdoc":
                    del tag.attrs[attr]
                    continue
                if lower in {"href", "src"} and value_text.strip().lower().startswith("javascript:"):
                    del tag.attrs[attr]
                    continue
                if lower == "style" and re.search(r"expression\s*\(|javascript:", value_text, re.I):
                    del tag.attrs[attr]

            if tag.name == "a" and tag.get("href"):
                tag["target"] = "_blank"
                tag["rel"] = "noreferrer"

        if base_dir is not None:
            self._promote_local_data_src(soup)
            self._rewrite_local_refs(soup, base_dir)

        for li in soup.find_all("li"):
            if not li.get_text(strip=True) and not li.find("img"):
                li.decompose()

        return str(soup)

    def _promote_local_data_src(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(["img", "source", "video", "audio"]):
            src = str(tag.get("src") or "")
            if src and not self._looks_like_placeholder_src(src):
                continue
            data_src = (
                str(tag.get("data-src") or "")
                or str(tag.get("data-original") or "")
                or str(tag.get("data-backsrc") or "")
            )
            if data_src and not self._is_external_ref(data_src):
                tag["src"] = data_src

    def _rewrite_local_refs(self, soup: BeautifulSoup, base_dir: Path) -> None:
        for tag in soup.find_all(["img", "source", "video", "audio"]):
            src = tag.get("src")
            if not src or self._is_external_ref(src):
                continue
            target = self._local_ref_to_path(base_dir, src)
            if target and target.suffix.lower() in self._IMAGE_EXTENSIONS:
                tag["src"] = self._asset_url(target)

    def _local_ref_to_path(self, base_dir: Path, ref: str) -> Path | None:
        clean = unquote(ref).split("#", 1)[0].split("?", 1)[0].strip()
        if not clean or clean.startswith(("/", "\\")):
            return None
        candidate = (base_dir / clean).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            return None
        return candidate if candidate.exists() and candidate.is_file() else None

    def _rewrite_epub_refs(
        self,
        content: str,
        item_name: str,
        item_lookup: dict[str, Any],
    ) -> str:
        soup = BeautifulSoup(content or "", "html.parser")
        for tag in soup.find_all(["img", "source"]):
            src = tag.get("src")
            if not src or self._is_external_ref(src):
                continue
            resolved = self._resolve_epub_ref(item_name, src)
            asset = item_lookup.get(resolved)
            if not asset:
                continue
            media_type = getattr(asset, "media_type", "") or mimetypes.guess_type(resolved)[0] or "application/octet-stream"
            encoded = base64.b64encode(asset.get_content()).decode("ascii")
            tag["src"] = f"data:{media_type};base64,{encoded}"
        return str(soup)

    def _asset_url(self, path: Path) -> str:
        return (
            f"/api/v1/reader/asset?file_path={quote(str(path), safe='')}"
            f"&root_path={quote(str(self.root), safe='')}"
        )

    @staticmethod
    def _is_external_ref(ref: str) -> bool:
        lower = ref.strip().lower()
        return lower.startswith((
            "#",
            "/api/",
            "/uploads/",
            "blob:",
            "data:",
            "http://",
            "https://",
            "mailto:",
            "tel:",
        ))

    @staticmethod
    def _looks_like_placeholder_src(ref: str) -> bool:
        lower = ref.strip().lower()
        if not lower:
            return True
        return (
            "data:image/svg+xml" in lower
            or "js_img_placeholder" in lower
            or "wx_img_placeholder" in lower
        )

    @staticmethod
    def _extract_body_content(raw: str) -> str:
        soup = BeautifulSoup(raw or "", "html.parser")
        node = soup.find(id="js_content") or soup.body or soup
        if getattr(node, "contents", None):
            return "".join(str(child) for child in node.contents)
        return str(node)

    @staticmethod
    def _extract_markdown_title(text: str) -> str:
        for line in text.splitlines():
            match = re.match(r"^#\s+(.+)$", line.strip())
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _extract_html_title(raw: str) -> str:
        soup = BeautifulSoup(raw or "", "html.parser")
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content"):
            return str(meta["content"]).strip()
        if soup.title and soup.title.get_text(strip=True):
            return soup.title.get_text(strip=True)
        return DocumentReaderService._extract_chapter_heading(raw)

    @staticmethod
    def _extract_chapter_heading(raw: str) -> str:
        soup = BeautifulSoup(raw or "", "html.parser")
        heading = soup.find(["h1", "h2", "h3"])
        if heading:
            return heading.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _epub_title(book: Any) -> str:
        try:
            values = book.get_metadata("DC", "title") or []
            if values:
                return str(values[0][0]).strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _normalize_epub_name(name: str) -> str:
        return posixpath.normpath((name or "").replace("\\", "/")).lstrip("./")

    @classmethod
    def _resolve_epub_ref(cls, item_name: str, ref: str) -> str:
        clean = unquote(ref).split("#", 1)[0].split("?", 1)[0]
        return cls._normalize_epub_name(posixpath.join(posixpath.dirname(item_name), clean))
