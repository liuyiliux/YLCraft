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
