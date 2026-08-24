from __future__ import annotations

from pathlib import Path

from app.services.asset_provenance import clean_file, inspect_file


def test_text_provenance_preview_and_cleaning(tmp_path: Path):
    source = tmp_path / "note.txt"
    target = tmp_path / "note-cleaned.txt"
    source.write_text("标题\u200b：\u202e正文", encoding="utf-8")

    report = inspect_file(source, "text/plain")
    assert report.cleanable is True
    assert report.invisible_character_count == 1
    assert report.bidi_control_count == 1

    cleaned = clean_file(source, target)
    assert source.read_text(encoding="utf-8") == "标题\u200b：\u202e正文"
    assert target.read_text(encoding="utf-8") == "标题：正文"
    assert cleaned.cleanable is False


def test_image_metadata_is_removed_without_overwriting_source(tmp_path: Path):
    from PIL import Image, PngImagePlugin

    source = tmp_path / "image.png"
    target = tmp_path / "image-cleaned.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "generated metadata")
    Image.new("RGB", (4, 3), "white").save(source, pnginfo=info)

    report = inspect_file(source, "image/png")
    assert report.cleanable is True
    clean_file(source, target)

    assert source.exists() and target.exists()
    assert "Comment" in inspect_file(source, "image/png").metadata_keys
    assert "Comment" not in inspect_file(target, "image/png").metadata_keys


def test_unsupported_format_is_audit_only(tmp_path: Path):
    source = tmp_path / "clip.xyz"
    target = tmp_path / "clip-cleaned.xyz"
    source.write_bytes(b"opaque bytes")

    report = inspect_file(source, "application/x-unknown")
    assert report.supported is False
    cleaned = clean_file(source, target)
    assert target.read_bytes() == source.read_bytes()
    assert cleaned.cleanable is False


def test_video_audio_are_recognized_for_cleaning(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"fake")

    video_report = inspect_file(video, "video/mp4")
    assert video_report.supported is True
    assert video_report.media_kind == "video"
    assert video_report.cleanable is True

    audio_report = inspect_file(audio, "audio/mpeg")
    assert audio_report.supported is True
    assert audio_report.media_kind == "audio"
    assert audio_report.cleanable is True


def test_pdf_metadata_is_removed_without_overwriting_source(tmp_path: Path):
    from pypdf import PdfReader, PdfWriter

    source = tmp_path / "doc.pdf"
    target = tmp_path / "doc-cleaned.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Author": "SomeAuthor", "/Title": "MyDoc"})
    with open(source, "wb") as fh:
        writer.write(fh)

    report = inspect_file(source, "application/pdf")
    assert report.supported is True
    assert report.media_kind == "document"
    assert report.cleanable is True
    assert "author" in report.metadata_keys

    cleaned = clean_file(source, target)
    assert source.exists() and target.exists()
    assert "author" in inspect_file(source, "application/pdf").metadata_keys  # source untouched
    assert cleaned.cleanable is False
    assert "author" not in inspect_file(target, "application/pdf").metadata_keys
    # 内容与页数保留
    assert len(PdfReader(str(target)).pages) == 1


def test_docx_metadata_is_removed_without_overwriting_source(tmp_path: Path):
    import docx

    source = tmp_path / "doc.docx"
    target = tmp_path / "doc-cleaned.docx"
    document = docx.Document()
    document.add_paragraph("hello world")
    document.core_properties.author = "SomeAuthor"
    document.core_properties.title = "MyDoc"
    document.core_properties.keywords = "kw1;kw2"
    document.save(str(source))

    report = inspect_file(
        source,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert report.supported is True
    assert report.media_kind == "document"
    assert report.cleanable is True
    assert "author" in report.metadata_keys

    cleaned = clean_file(source, target)
    assert source.exists() and target.exists()
    assert "author" in inspect_file(source).metadata_keys  # source untouched
    assert cleaned.cleanable is False
    assert "author" not in inspect_file(target).metadata_keys
    # 内容保留
    assert docx.Document(str(target)).paragraphs[0].text == "hello world"


def test_pdf_docx_extensions_are_detected_by_suffix(tmp_path: Path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    docx = tmp_path / "b.docx"
    docx.write_bytes(b"PK")

    assert inspect_file(pdf).media_kind == "document"
    assert inspect_file(docx).media_kind == "document"


def test_deep_watermark_detect_is_read_only_and_reports_ctrlregen(tmp_path: Path):
    from PIL import Image

    from app.services.asset_provenance import detect_deep_watermark

    source = tmp_path / "img.png"
    Image.new("RGB", (64, 64), "#4a7bb5").save(source)
    before = source.read_bytes()

    result = detect_deep_watermark(source, "image/png")
    assert result.supported is True
    assert result.media_kind == "image"
    assert "score" in result.ctrlregen
    assert "confidence" in result.ctrlregen
    assert result.ctrlregen["method"] == "statistical-ctrlregen-like"
    assert result.synthid["status"] == "skipped"
    # 只读：文件字节不变
    assert source.read_bytes() == before
    # 不伪装成已清理（任何 note 都不宣称能“移除”水印）
    assert all("移除" not in n for n in result.notes)
    # 明确只读上报
    assert any("未修改" in n for n in result.notes)


def test_deep_watermark_detect_image_with_noise_scores_higher(tmp_path: Path):
    """带噪/高频内容的图应得到更高（更强嵌入痕迹）得分，验证统计检测区分度。"""
    import random

    from PIL import Image

    from app.services.asset_provenance import detect_deep_watermark

    flat = tmp_path / "flat.png"
    noisy = tmp_path / "noisy.png"
    Image.new("RGB", (64, 64), (80, 80, 80)).save(flat)
    Image.new("RGB", (64, 64), (80, 80, 80)).save(noisy)
    img = Image.open(noisy)
    rnd = random.Random(42)
    for y in range(img.height):
        for x in range(img.width):
            img.putpixel((x, y), (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    img.save(noisy)

    flat_result = detect_deep_watermark(flat, "image/png")
    noisy_result = detect_deep_watermark(noisy, "image/png")
    assert noisy_result.ctrlregen["score"] > flat_result.ctrlregen["score"]


def test_deep_watermark_detect_unsupported_and_synthid_skipped(tmp_path: Path):
    from app.services.asset_provenance import detect_deep_watermark

    # 文本：返回 unsupported 且不伪装
    text = tmp_path / "note.txt"
    text.write_text("hello", encoding="utf-8")
    result = detect_deep_watermark(text, "text/plain")
    assert result.supported is False
    assert result.media_kind == "text"
    assert result.synthid["status"] == "skipped"

    # 未知格式
    blob = tmp_path / "blob.xyz"
    blob.write_bytes(b"data")
    result = detect_deep_watermark(blob)
    assert result.supported is False
    assert result.media_kind == "unsupported"
    assert all("不伪装" in n for n in result.notes)


def test_deep_watermark_detect_synthid_can_be_enabled_via_env(tmp_path, monkeypatch):
    from PIL import Image

    from app.services.asset_provenance import detect_deep_watermark

    monkeypatch.setenv("YLCRAFT_SYNTHID_DETECT_ENABLED", "1")
    monkeypatch.setenv("YLCRAFT_SYNTHID_DETECT_PROVIDER", "demo-detector")
    source = tmp_path / "img.png"
    Image.new("RGB", (32, 32), "white").save(source)

    result = detect_deep_watermark(source, "image/png")
    assert result.synthid["status"] == "enabled"
    assert result.synthid["provider"] == "demo-detector"
    # 仍只读
    assert "未修改" in " ".join(result.notes)
