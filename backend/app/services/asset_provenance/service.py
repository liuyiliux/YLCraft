"""Non-destructive AI provenance and file metadata audit/cleaning."""

from __future__ import annotations

import mimetypes
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".html", ".htm", ".xml", ".svg"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
_INVISIBLE_RE = re.compile("[\\u200b\\u200c\\u200d\\ufeff\\u2060\\u2066\\u2067\\u2068\\u2069]")
_BIDI_RE = re.compile("[\\u202a-\\u202e\\u2066-\\u2069]")


@dataclass
class ProvenanceReport:
    supported: bool
    media_kind: str
    metadata_keys: list[str]
    invisible_character_count: int
    bidi_control_count: int
    cleanable: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text_controls(value: str) -> tuple[int, int]:
    return len(_INVISIBLE_RE.findall(value)), len(_BIDI_RE.findall(value))


def inspect_file(path: str | Path, mime_type: str = "") -> ProvenanceReport:
    """Inspect supported metadata/provenance markers without changing the file."""
    source = Path(path)
    suffix = source.suffix.lower()
    guessed = mime_type or mimetypes.guess_type(source.name)[0] or ""
    if suffix in TEXT_SUFFIXES or guessed.startswith("text/"):
        try:
            content = source.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ProvenanceReport(False, "text", [], 0, 0, False, [str(exc)])
        invisible, bidi = _text_controls(content)
        return ProvenanceReport(True, "text", [], invisible, bidi, bool(invisible or bidi), ["文本隐形字符和双向控制符可生成清理副本。"] if invisible or bidi else [])

    if suffix in IMAGE_SUFFIXES or guessed.startswith("image/"):
        try:
            from PIL import Image

            with Image.open(source) as image:
                keys = sorted(str(key) for key in (image.info or {}).keys())
                exif_count = len(image.getexif()) if hasattr(image, "getexif") else 0
            return ProvenanceReport(True, "image", sorted(set(keys + (["exif"] if exif_count else []))), 0, 0, bool(keys or exif_count), ["图片可生成去除 EXIF/格式元数据的派生副本。"] if keys or exif_count else [])
        except Exception as exc:
            return ProvenanceReport(False, "image", [], 0, 0, False, [f"图片元数据读取失败：{exc}"])

    if suffix in VIDEO_SUFFIXES or guessed.startswith("video/"):
        return ProvenanceReport(True, "video", ["container-metadata"], 0, 0, True, ["视频可用 ffmpeg 去除容器元数据并生成清理副本。"])
    if suffix in AUDIO_SUFFIXES or guessed.startswith("audio/"):
        return ProvenanceReport(True, "audio", ["container-metadata"], 0, 0, True, ["音频可用 ffmpeg 去除容器元数据并生成清理副本。"])

    return ProvenanceReport(False, "file", [], 0, 0, False, ["当前格式暂只支持审计，不会伪装成已清理。"])


def clean_file(source_path: str | Path, target_path: str | Path) -> ProvenanceReport:
    """Create a cleaned copy. The source file is never modified."""
    source = Path(source_path)
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    report = inspect_file(source)
    if not report.supported:
        shutil.copy2(source, target)
        return report
    if report.media_kind == "text":
        content = source.read_text(encoding="utf-8", errors="replace")
        target.write_text(_BIDI_RE.sub("", _INVISIBLE_RE.sub("", content)), encoding="utf-8")
        return inspect_file(target)

    if report.media_kind in {"video", "audio"}:
        import subprocess

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            shutil.copy2(source, target)
            return ProvenanceReport(False, report.media_kind, [], 0, 0, False, ["未找到 ffmpeg，无法清理容器元数据。"])
        try:
            subprocess.run(
                [ffmpeg, "-y", "-i", str(source), "-map_metadata", "-1", "-c", "copy", str(target)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            shutil.copy2(source, target)
            detail = (exc.stderr or b"").decode("utf-8", errors="replace")[-300:]
            return ProvenanceReport(False, report.media_kind, [], 0, 0, False, [f"ffmpeg 清理失败：{detail}"])
        return inspect_file(target)

    from PIL import Image

    with Image.open(source) as image:
        image_format = image.format or source.suffix.lstrip(".").upper()
        save_kwargs: dict[str, Any] = {}
        if image_format.upper() in {"JPEG", "JPG", "WEBP", "PNG", "TIFF"}:
            save_kwargs["exif"] = b""
        image.save(target, format=image_format, **save_kwargs)
    return inspect_file(target)


class AssetProvenanceService:
    """Coordinates preview/clean operations around an Asset Hub representation."""

    def __init__(self, session):
        self.session = session

    async def preview(self, asset_id: str, representation):
        return inspect_file(representation.file_path, representation.mime_type).to_dict()

    async def clean(self, asset, version, representation, output_dir: str | Path):
        source = Path(representation.file_path)
        target = Path(output_dir) / f"{source.stem}-cleaned{source.suffix}"
        report = clean_file(source, target)
        return target, report.to_dict()
