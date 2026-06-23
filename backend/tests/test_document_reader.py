from pathlib import Path

import pytest

from app.services.reader.document_reader import DocumentReaderService, ReaderError
from app.services.wechat_mp.epub_exporter import build_epub


def test_reader_loads_markdown_and_rewrites_local_image(tmp_path: Path):
    root = tmp_path / "downloads"
    image_dir = root / "images"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "cover.png"
    image_path.write_bytes(b"png")
    md_path = root / "article.md"
    md_path.write_text("# Reader title\n\n![cover](images/cover.png)\n\nhello", encoding="utf-8")

    doc = DocumentReaderService(root=root).read(str(md_path))

    assert doc["title"] == "Reader title"
    assert doc["format"] == "md"
    assert doc["chapters"][0]["title"] == "Reader title"
    assert "/api/v1/reader/asset?file_path=" in doc["chapters"][0]["content"]


def test_reader_rejects_path_outside_root(tmp_path: Path):
    root = tmp_path / "downloads"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# outside", encoding="utf-8")

    with pytest.raises(ReaderError):
        DocumentReaderService(root=root).read(str(outside))


def test_reader_browses_supported_files_under_root(tmp_path: Path):
    root = tmp_path / "downloads"
    sub = root / "wechat_mp"
    sub.mkdir(parents=True)
    (root / "article.html").write_text("<h1>html</h1>", encoding="utf-8")
    (root / "ignore.bin").write_bytes(b"bin")
    (sub / "book.epub").write_bytes(b"not-real-epub")

    service = DocumentReaderService(root=root)
    listing = service.browse()

    names = [item["name"] for item in listing["items"]]
    assert names == ["wechat_mp", "article.html"]
    assert listing["current_relative_path"] == ""
    assert listing["items"][0]["is_dir"] is True
    assert listing["items"][1]["readable"] is True

    nested = service.browse("wechat_mp")
    assert nested["parent_relative_path"] == ""
    assert nested["items"][0]["name"] == "book.epub"

    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ReaderError):
        service.browse(str(outside))


def test_reader_deletes_file_under_root(tmp_path: Path):
    root = tmp_path / "downloads"
    root.mkdir()
    file_path = root / "article.html"
    file_path.write_text("<h1>html</h1>", encoding="utf-8")

    result = DocumentReaderService(root=root).delete_item("article.html")

    assert result["success"] is True
    assert result["is_dir"] is False
    assert result["deleted_files"] == 1
    assert result["freed_size"] > 0
    assert not file_path.exists()


def test_reader_requires_recursive_delete_for_folder(tmp_path: Path):
    root = tmp_path / "downloads"
    folder = root / "wechat_mp" / "account"
    folder.mkdir(parents=True)
    (folder / "article.html").write_text("<h1>html</h1>", encoding="utf-8")

    service = DocumentReaderService(root=root)

    with pytest.raises(ReaderError, match="递归删除"):
        service.delete_item("wechat_mp")

    result = service.delete_item("wechat_mp", recursive=True)

    assert result["success"] is True
    assert result["is_dir"] is True
    assert result["deleted_files"] == 1
    assert result["deleted_dirs"] == 2
    assert not (root / "wechat_mp").exists()


def test_reader_rejects_delete_root_and_outside_root(tmp_path: Path):
    root = tmp_path / "downloads"
    root.mkdir()
    outside = tmp_path / "outside.html"
    outside.write_text("<h1>outside</h1>", encoding="utf-8")

    service = DocumentReaderService(root=root)

    with pytest.raises(ReaderError, match="下载根目录"):
        service.delete_item(str(root))

    with pytest.raises(ReaderError, match="下载目录内"):
        service.delete_item(str(outside))


def test_reader_uses_custom_root_for_assets(tmp_path: Path):
    root = tmp_path / "custom-root"
    image_dir = root / "images"
    image_dir.mkdir(parents=True)
    (image_dir / "cover.png").write_bytes(b"png")
    md_path = root / "article.md"
    md_path.write_text("# Custom\n\n![cover](images/cover.png)", encoding="utf-8")

    doc = DocumentReaderService(root=root).read(str(md_path))

    assert doc["root_path"] == str(root.resolve())
    assert "root_path=" in doc["chapters"][0]["content"]


def test_reader_promotes_wechat_local_data_src_placeholder(tmp_path: Path):
    root = tmp_path / "downloads"
    image_dir = root / "images"
    image_dir.mkdir(parents=True)
    (image_dir / "wechat.png").write_bytes(b"png")
    html_path = root / "article.html"
    html_path.write_text(
        '<div id="js_content">'
        '<img class="js_img_placeholder" src="data:image/svg+xml,%3Csvg%3E" '
        'data-src="images/wechat.png" />'
        "</div>",
        encoding="utf-8",
    )

    doc = DocumentReaderService(root=root).read(str(html_path))

    content = doc["chapters"][0]["content"]
    assert "data:image/svg+xml" not in content
    assert "/api/v1/reader/asset?file_path=" in content


def test_reader_loads_epub_with_article_local_images(tmp_path: Path):
    root = tmp_path / "downloads"
    article_dir = root / "wechat_mp" / "account" / "2026-06"
    images_dir = article_dir / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "cover.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    md_path = article_dir / "article.md"
    md_path.write_text("# article\n\n![图片](images/cover.png)", encoding="utf-8")
    epub_path = root / "wechat_mp" / "epub" / "book.epub"

    build_epub(
        book_title="book",
        articles=[{
            "title": "chapter",
            "content_html": '<p>hello</p><img src="images/cover.png" />',
            "file_path": str(md_path),
        }],
        out_path=str(epub_path),
        images_base_dir=str(root / "wechat_mp"),
    )

    doc = DocumentReaderService(root=root).read(str(epub_path))

    assert doc["format"] == "epub"
    assert doc["chapters"]
    assert "data:image/png;base64," in doc["chapters"][0]["content"]
