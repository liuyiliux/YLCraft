"""Metadata helpers for local readable document assets."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup


READABLE_DOCUMENT_EXTENSIONS = {
    ".epub",
    ".htm",
    ".html",
    ".markdown",
    ".md",
    ".text",
    ".txt",
}

READABLE_DOCUMENT_TYPES = {"ARTICLE", "TEXT", "DOCUMENT", "NOVEL"}


def is_readable_document_asset(asset_type: str = "", file_path: str = "") -> bool:
    suffix = Path(file_path or "").suffix.lower()
    return (asset_type or "").upper() in READABLE_DOCUMENT_TYPES and suffix in READABLE_DOCUMENT_EXTENSIONS


def extract_document_asset_metadata(file_path: str | Path) -> dict[str, str]:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return {}

    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return _extract_html_metadata(path)
    if suffix in {".md", ".markdown"}:
        return _extract_markdown_metadata(path)
    if suffix == ".epub":
        return _extract_epub_metadata(path)
    if suffix in {".txt", ".text"}:
        return {"title": path.stem}
    return {}


def extract_document_cover_source(file_path: str | Path) -> str:
    path = Path(file_path)
    metadata = extract_document_asset_metadata(path)
    return resolve_document_cover_source(path, metadata.get("cover_ref", ""))


def resolve_document_cover_source(file_path: str | Path, cover_ref: str = "") -> str:
    ref = (cover_ref or "").strip()
    if not ref:
        return ""
    if _is_external_or_data_ref(ref):
        return ref

    path = Path(file_path)
    if Path(ref).is_absolute():
        candidate = Path(ref)
    else:
        clean = _strip_ref_suffix(ref)
        if not clean or clean.startswith(("/", "\\")):
            return ""
        candidate = path.parent / clean

    try:
        resolved = candidate.resolve()
        if not Path(ref).is_absolute():
            resolved.relative_to(path.parent.resolve())
    except (OSError, ValueError):
        return ""

    return str(resolved) if resolved.exists() and resolved.is_file() else ""


def _extract_html_metadata(path: Path) -> dict[str, str]:
    raw = _read_text(path)
    soup = BeautifulSoup(raw or "", "html.parser")
    return {
        "title": _first(
            _meta_content(soup, property_="og:title"),
            _meta_content(soup, name="twitter:title"),
            soup.title.get_text(" ", strip=True) if soup.title else "",
            _heading_text(soup),
            path.stem,
        ),
        "author": _first(
            _meta_content(soup, name="author"),
            _meta_content(soup, property_="article:author"),
            _node_text(soup, id_="js_name"),
            _node_text(soup, class_="profile_nickname"),
        ),
        "cover_ref": _first(
            _meta_content(soup, property_="og:image"),
            _meta_content(soup, name="twitter:image"),
            _first_image_ref(soup),
        ),
        "source_url": _first(
            _meta_content(soup, property_="og:url"),
            _node_href(soup, id_="js_source_url"),
        ),
    }


def _extract_markdown_metadata(path: Path) -> dict[str, str]:
    text = _read_text(path)
    return {
        "title": _first(_markdown_title(text), path.stem),
        "author": _first(_frontmatter_value(text, "author")),
        "cover_ref": _first(_markdown_image_ref(text)),
        "source_url": _first(_frontmatter_value(text, "source_url"), _frontmatter_value(text, "url")),
    }


def _extract_epub_metadata(path: Path) -> dict[str, str]:
    try:
        from ebooklib import ITEM_COVER, epub
    except Exception:
        return {"title": path.stem}

    try:
        book = epub.read_epub(str(path))
    except Exception:
        return {"title": path.stem}

    title = ""
    author = ""
    try:
        titles = book.get_metadata("DC", "title") or []
        creators = book.get_metadata("DC", "creator") or []
        if titles:
            title = str(titles[0][0]).strip()
        if creators:
            author = str(creators[0][0]).strip()
    except Exception:
        pass

    cover_ref = ""
    try:
        covers = list(book.get_items_of_type(ITEM_COVER))
        if covers:
            cover_ref = covers[0].get_name() or ""
    except Exception:
        cover_ref = ""

    return {"title": title or path.stem, "author": author, "cover_ref": cover_ref}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _meta_content(soup: BeautifulSoup, name: str = "", property_: str = "") -> str:
    attrs: dict[str, Any] = {}
    if name:
        attrs["name"] = name
    if property_:
        attrs["property"] = property_
    node = soup.find("meta", attrs=attrs)
    return str(node.get("content") or "").strip() if node else ""


def _heading_text(soup: BeautifulSoup) -> str:
    node = soup.find(["h1", "h2", "h3"])
    return node.get_text(" ", strip=True) if node else ""


def _node_text(soup: BeautifulSoup, id_: str = "", class_: str = "") -> str:
    attrs: dict[str, Any] = {}
    if id_:
        attrs["id"] = id_
    if class_:
        attrs["class"] = class_
    node = soup.find(attrs=attrs)
    return node.get_text(" ", strip=True) if node else ""


def _node_href(soup: BeautifulSoup, id_: str = "") -> str:
    node = soup.find(id=id_)
    return str(node.get("href") or "").strip() if node else ""


def _first_image_ref(soup: BeautifulSoup) -> str:
    for img in soup.find_all("img"):
        src = _first(
            str(img.get("src") or ""),
            str(img.get("data-src") or ""),
            str(img.get("data-original") or ""),
            str(img.get("data-backsrc") or ""),
        )
        if not src:
            continue
        lower = src.lower()
        if "avatar" in lower or "icon" in lower:
            continue
        return src
    return ""


def _markdown_title(text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            return match.group(1).strip()
    return ""


def _markdown_image_ref(text: str) -> str:
    match = re.search(r"!\[[^\]]*]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)", text or "")
    if not match:
        return ""
    return match.group(1).strip().strip("<>'\"")


def _frontmatter_value(text: str, key: str) -> str:
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    pattern = rf"^{re.escape(key)}\s*:\s*(.+)$"
    for line in text[3:end].splitlines():
        match = re.match(pattern, line.strip(), re.I)
        if match:
            return match.group(1).strip().strip("'\"")
    return ""


def _first(*values: str) -> str:
    for value in values:
        clean = (value or "").strip()
        if clean:
            return clean
    return ""


def _is_external_or_data_ref(ref: str) -> bool:
    parsed = urlparse(ref)
    return parsed.scheme.lower() in {"http", "https", "data"}


def _strip_ref_suffix(ref: str) -> str:
    clean = unquote(ref).strip()
    clean = clean.split("#", 1)[0].split("?", 1)[0]
    return clean.replace("\\", "/")
