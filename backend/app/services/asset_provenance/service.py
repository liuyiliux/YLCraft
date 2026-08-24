"""Non-destructive AI provenance and file metadata audit/cleaning.

能力边界参考 `guillaumemeyer/watermarks-remover`（见 docs/reference/watermarks-remover.md）：
覆盖文本隐形 Unicode / bidi / 空间同形字（Layer A）、图片 EXIF/格式元数据、
音视频容器元数据、以及多种文档格式（OOXML docx/xlsx/pptx、OpenDocument odt、EPUB、PDF）。

设计约定：
- 审计（inspect）永远不改动源文件；清理（clean）总是生成派生副本，源文件保留。
- 未支持的格式只报告审计结果，不会伪装成已清理。
"""

from __future__ import annotations

import mimetypes
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".html", ".htm", ".xml", ".svg"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".avif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
DOCUMENT_SUFFIXES = {".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".epub"}
# OOXML 容器（zip）内用同一套 docProps/core.xml 核心属性清理逻辑
_OOXML_SUFFIXES = {".docx", ".xlsx", ".pptx"}
_PDF_CORE_KEYS = {"author", "creator", "producer", "subject", "title", "keywords"}
# 图片格式结构属性：非作者可写、非 provenance 载体，审计时不计为可清理元数据。
_STRUCTURAL_IMAGE_KEYS = {"version", "background", "transparency", "duration", "loop", "icc_profile", "chromaticity"}

# ---------------------------------------------------------------------------
# Layer A：隐形 Unicode / bidi / 空间同形字 / 标签字符清理（参考 watermarks-remover）
# 覆盖集比早期实现大得多，同时保留"承载负载"的脚本胶水（emoji、连字、选区符）。
# ---------------------------------------------------------------------------

# 直接移除的隐形/格式控制符（零宽、bidi、软连字符、组合连字符、隐式格式等）。
_STRIP_CODEPOINTS: frozenset[int] = frozenset(
    {
        0x00AD,  # 软连字符
        0x034F,  # combining grapheme joiner
        0x061C,  # Arabic letter mark
        0x115F, 0x1160,  # Hangul 填充符
        0x17B4, 0x17B5,  # Khmer 固有元音
        0x180B, 0x180C, 0x180D, 0x180E, 0x180F,  # 蒙古自由变体选择符
        0x200B, 0x200C, 0x200D,  # ZWSP / ZWNJ / ZWJ
        0x200E, 0x200F,  # LRM / RLM
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,  # LRE/RLE/PDF/LRO/RLO
        0x2060, 0x2061, 0x2062, 0x2063, 0x2064,  # 字连接符 / 隐式运算
        0x2066, 0x2067, 0x2068, 0x2069,  # LRI/RLI/FSI/PDI
        0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F,  # 对称交换抑制等
        0xFEFF,  # BOM / ZWNBSP
        0x3164, 0xFFA0,  # Hangul 填充符（兼容 jamo）
        0xFFF9, 0xFFFA, 0xFFFB,  # 行间注解
    }
)
# 空间同形字 → 统一为普通空格 U+0020。
_SPACE_HOMOGLYPHS: dict[int, str] = {
    0x00A0: " ", 0x1680: " ", 0x2000: " ", 0x2001: " ", 0x2002: " ",
    0x2003: " ", 0x2004: " ", 0x2005: " ", 0x2006: " ", 0x2007: " ",
    0x2008: " ", 0x2009: " ", 0x200A: " ", 0x202F: " ", 0x205F: " ",
    0x3000: " ",
}
# 变体选择符（Supplementary Special-purpose）与保留的默认可忽略码位。
_VS_SUPPLEMENT = range(0xE0100, 0xE01F0)
_RESERVED_IGNORABLE_CPS: frozenset[int] = frozenset({0x2065, 0xE0000})
_RESERVED_IGNORABLE_RANGES: tuple[range, ...] = (
    range(0xFFF0, 0xFFF9),
    range(0xE0080, 0xE0100),
    range(0xE01F0, 0xE1000),
)
# 66 个 Unicode 非字符。
_NONCHARACTER_RANGE = range(0xFDD0, 0xFDE0)  # 实际是 FDD0..FDEF，下面按位判断
# 私有用途区。
_PUA_BMP = range(0xE000, 0xF900)
# 标签字符（flag tags 等 stego 载体）。
_TAG_CHARS = range(0xE0001, 0xE0080)

# bidi / 方向控制符（用于报告细分）。
_BIDI_CPS: frozenset[int] = frozenset(
    {0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}
)
# 零宽族（常见编辑载体）。
_ZW_FAMILY: frozenset[int] = frozenset({0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E})

# 承载负载的脚本胶水（这些在特定上下文中是合法的，需要保留）：
_EMOJI_GLUE: frozenset[int] = frozenset({0x200D, 0xFE0E, 0xFE0F})  # ZWJ / VS15 / VS16
_SCRIPT_JOINERS: frozenset[int] = frozenset({0x200C, 0x200D})  # ZWNJ / ZWJ（阿拉伯/印度/高棉等）
_MONGOLIAN_FVS: frozenset[int] = frozenset({0x180B, 0x180C, 0x180D, 0x180F})
_KHMER_VOWELS: frozenset[int] = frozenset({0x17B4, 0x17B5})
_HANGUL_FILLERS: frozenset[int] = frozenset({0x115F, 0x1160, 0x3164, 0xFFA0})
_SCRIPT_GLUE: frozenset[int] = _MONGOLIAN_FVS | _KHMER_VOWELS | _HANGUL_FILLERS
_VARIATION_SELECTORS: frozenset[int] = frozenset(range(0xFE00, 0xFE10))

# 语言分组（用于判断 ZWJ/ZWNJ/变体选择符等是否"承载负载"）。
_ARABIC_RANGE = range(0x0600, 0x0900)
_INDIC_RANGE = range(0x0900, 0x0E00)
_SOUTH_ASIAN_RANGE = range(0x0F00, 0x1100)
_KHMER_RANGE = range(0x1780, 0x1800)
_MONGOLIAN_RANGE = range(0x1800, 0x18B0)


def _is_emoji_base(cp: int) -> bool:
    if 0x1F000 <= cp <= 0x1FAFF:
        return True
    if 0x2190 <= cp <= 0x25FF or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF:
        return True
    if cp in (0x203C, 0x2049, 0x2139, 0x2934, 0x2935, 0x00A9, 0x00AE, 0x2122, 0x3030, 0x303D, 0x3297, 0x3299):
        return True
    return cp in (0x0023, 0x002A) or 0x0030 <= cp <= 0x0039


def _is_reserved_ignorable(cp: int) -> bool:
    if cp in _RESERVED_IGNORABLE_CPS:
        return True
    return any(cp in r for r in _RESERVED_IGNORABLE_RANGES)


def _is_noncharacter(cp: int) -> bool:
    return 0xFDD0 <= cp <= 0xFDEF or (cp & 0xFFFE) == 0xFFFE


def _is_private_use(cp: int) -> bool:
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


def _is_variation_selector(cp: int) -> bool:
    return cp in _VS_SUPPLEMENT or cp in _VARIATION_SELECTORS or cp in _MONGOLIAN_FVS


def _strip_kind(cp: int) -> str:
    if cp in _TAG_CHARS:
        return "tag"
    if _is_noncharacter(cp):
        return "noncharacter"
    if _is_reserved_ignorable(cp):
        return "reserved_ignorable"
    if _is_variation_selector(cp):
        return "variation_selector"
    if cp in _BIDI_CPS:
        return "bidi"
    if cp in _ZW_FAMILY:
        return "zwj_family"
    if _is_private_use(cp):
        return "private_use"
    return "strip"


def _is_joining_script(cp: int) -> bool:
    """ZWJ/ZWNJ 在其母脚本内可能是正交的（波斯 می‌روم、天城文 क्‍ष 等）。"""
    for rng in (_ARABIC_RANGE, _INDIC_RANGE, _SOUTH_ASIAN_RANGE, _KHMER_RANGE, _MONGOLIAN_RANGE):
        if cp in rng:
            return True
    return False


def _is_load_bearing(codepoints: list[int], idx: int) -> bool:
    """判断下标 idx 处的码位是否为"承载负载"的脚本胶水，若是则应保留。

    规则参考 watermarks-remover 的 Layer A：
    - emoji ZWJ/VS 紧跟 emoji 基底之后是可见序列，保留；
    - 变体选择符紧跟 CJK 或同脚本基底保留；
    - 蒙古 FVS 紧跟蒙古字母保留；Khmer 元音紧跟高棉字保留；Hangul 填充符紧跟对应 jamo 保留；
    - ZWJ/ZWNJ 在连接脚本内保留（正交）。
    """
    cp = codepoints[idx]
    prev = codepoints[idx - 1] if idx > 0 else None
    nxt = codepoints[idx + 1] if idx + 1 < len(codepoints) else None

    # emoji 胶水：ZWJ/VS 在 emoji 基底之后
    if cp in _EMOJI_GLUE:
        if prev is not None and (_is_emoji_base(prev) or prev in _EMOJI_GLUE):
            return True
        # ZWJ 连接两段 emoji 序列：前一个是基底/胶水，后一个是基底则保留
        if cp == 0x200D and nxt is not None and _is_emoji_base(nxt) and prev is not None and _is_emoji_base(prev):
            return True
        return False

    # 变体选择符：紧跟 CJK / 同脚本基底
    if cp in _VARIATION_SELECTORS or cp in _VS_SUPPLEMENT:
        return prev is not None and (
            _is_emoji_base(prev)
            or 0x3400 <= prev <= 0x4DBF or 0x4E00 <= prev <= 0x9FFF or 0x20000 <= prev <= 0x323AF
        )

    # 蒙古自由变体选择符：紧跟蒙古字母
    if cp in _MONGOLIAN_FVS:
        return prev is not None and prev in _MONGOLIAN_RANGE
    # Khmer 元音：紧跟高棉字母
    if cp in _KHMER_VOWELS:
        return prev is not None and prev in _KHMER_RANGE
    # Hangul 填充符：紧跟对应 jamo（仅处理合法承接，简化：保留在 CJK 音节内）
    if cp in _HANGUL_FILLERS:
        return prev is not None and (0x1100 <= prev <= 0x11FF or 0x3131 <= prev <= 0x318E or 0xAC00 <= prev <= 0xD7AF)

    # ZWJ/ZWNJ 在连接脚本内（阿拉伯/印度/高棉/蒙古/南亚）
    if cp in _SCRIPT_JOINERS:
        return prev is not None and _is_joining_script(prev)

    return False


def _is_strip_cp(cp: int) -> bool:
    if cp in _STRIP_CODEPOINTS:
        return True
    if cp in _VS_SUPPLEMENT:
        return True
    if cp in _TAG_CHARS:
        return True
    if _is_noncharacter(cp):
        return True
    if _is_reserved_ignorable(cp):
        return True
    if _is_private_use(cp):
        return True
    return False


def _clean_text_layer_a(value: str) -> tuple[str, dict[str, int]]:
    """Layer A 清理：移除隐形/格式控制符（保留负载胶水），并归一化空间同形字。

    返回 (清理后文本, 按类型的移除计数)。
    """
    codepoints = [ord(ch) for ch in value]
    counts: dict[str, int] = {}
    kept: list[str] = []
    i = 0
    n = len(codepoints)
    while i < n:
        cp = codepoints[i]
        # 先尝试空间同形字归一化（安全，不依赖上下文）
        if cp in _SPACE_HOMOGLYPHS:
            kept.append(_SPACE_HOMOGLYPHS[cp])
            counts["space_homoglyph"] = counts.get("space_homoglyph", 0) + 1
            i += 1
            continue
        if _is_strip_cp(cp):
            if _is_load_bearing(codepoints, i):
                kept.append(chr(cp))
            else:
                kind = _strip_kind(cp)
                counts[kind] = counts.get(kind, 0) + 1
            i += 1
            continue
        kept.append(chr(cp))
        i += 1
    return "".join(kept), counts


def _text_controls(value: str) -> tuple[int, int]:
    """兼容旧字段：返回隐形字符数与 bidi 控制符数（二者互不重叠）。

    隐形字符 = 所有应移除的隐形/格式控制符（不含空间同形字、不含 bidi）；
    bidi 控制符单独计数，避免与隐形计数重复。
    """
    invisible = bidi = 0
    for ch in value:
        cp = ord(ch)
        if not _is_strip_cp(cp) or _is_load_bearing([cp], 0):
            continue
        if cp in _BIDI_CPS:
            bidi += 1
        else:
            invisible += 1
    return invisible, bidi


# ---------------------------------------------------------------------------
# 报告模型
# ---------------------------------------------------------------------------


@dataclass
class ProvenanceReport:
    supported: bool
    media_kind: str
    metadata_keys: list[str]
    invisible_character_count: int
    bidi_control_count: int
    cleanable: bool
    notes: list[str]
    # 新增：Layer A Unicode 按类型细分（兼容旧前端，可选字段）
    unicode_breakdown: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------


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
        return ProvenanceReport(
            True, "text", [], invisible, bidi, bool(invisible or bidi),
            ["文本隐形字符、双向控制符与空间同形字可生成清理副本。"] if invisible or bidi else [],
        )

    if suffix in IMAGE_SUFFIXES or guessed.startswith("image/"):
        try:
            from PIL import Image

            with Image.open(source) as image:
                keys = sorted(str(key) for key in (image.info or {}).keys())
                exif_count = len(image.getexif()) if hasattr(image, "getexif") else 0
            # 过滤掉格式结构属性（非作者可写、非 provenance 载体），
            # 避免把 GIF 的 version/background 等误报为可清理元数据。
            keys = [k for k in keys if k.lower() not in _STRUCTURAL_IMAGE_KEYS]
            return ProvenanceReport(True, "image", sorted(set(keys + (["exif"] if exif_count else []))), 0, 0, bool(keys or exif_count), ["图片可生成去除 EXIF/格式元数据的派生副本。"] if keys or exif_count else [])
        except Exception as exc:
            return ProvenanceReport(False, "image", [], 0, 0, False, [f"图片元数据读取失败：{exc}"])

    if suffix in VIDEO_SUFFIXES or guessed.startswith("video/"):
        return ProvenanceReport(True, "video", ["container-metadata"], 0, 0, True, ["视频可用 ffmpeg 去除容器元数据并生成清理副本。"])
    if suffix in AUDIO_SUFFIXES or guessed.startswith("audio/"):
        return ProvenanceReport(True, "audio", ["container-metadata"], 0, 0, True, ["音频可用 ffmpeg 去除容器元数据并生成清理副本。"])

    if suffix in DOCUMENT_SUFFIXES or _is_document_mime(guessed):
        try:
            if suffix == ".pdf" or guessed == "application/pdf":
                keys = _pdf_metadata_keys(source)
            elif suffix in _OOXML_SUFFIXES or "officedocument" in guessed or "spreadsheetml" in guessed or "presentationml" in guessed:
                keys = _ooxml_metadata_keys(source, "docProps/core.xml")
            elif suffix == ".odt":
                keys = _odt_metadata_keys(source)
            elif suffix == ".epub":
                keys = _epub_metadata_keys(source)
            else:
                keys = _ooxml_metadata_keys(source, "docProps/core.xml")
        except Exception as exc:
            return ProvenanceReport(False, "document", [], 0, 0, False, [f"文档元数据读取失败：{exc}"])
        cleanable = bool(keys)
        return ProvenanceReport(True, "document", keys, 0, 0, cleanable, ["文档核心元数据可生成清理副本。"] if cleanable else ["文档未发现可清理的元数据字段。"])

    return ProvenanceReport(False, "file", [], 0, 0, False, ["当前格式暂只支持审计，不会伪装成已清理。"])


def _is_document_mime(guessed: str) -> bool:
    if guessed == "application/pdf":
        return True
    if "officedocument" in guessed or "spreadsheetml" in guessed or "presentationml" in guessed:
        return True
    if guessed == "application/epub+zip" or guessed == "application/vnd.oasis.opendocument.text":
        return True
    return False


# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------


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
        cleaned, _breakdown = _clean_text_layer_a(content)
        target.write_text(cleaned, encoding="utf-8")
        cleaned_report = inspect_file(target)
        cleaned_report.unicode_breakdown = _breakdown
        return cleaned_report

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

    if report.media_kind == "document":
        suffix = source.suffix.lower()
        if suffix == ".pdf":
            _clean_pdf(source, target)
        elif suffix in _OOXML_SUFFIXES:
            _clean_ooxml(source, target, "docProps/core.xml")
        elif suffix == ".odt":
            _clean_odt(source, target)
        elif suffix == ".epub":
            _clean_epub(source, target)
        else:
            _clean_ooxml(source, target, "docProps/core.xml")
        return inspect_file(target)

    from PIL import Image

    with Image.open(source) as image:
        image_format = image.format or source.suffix.lstrip(".").upper()
        save_kwargs: dict[str, Any] = {}
        fmt = image_format.upper()
        if fmt in {"JPEG", "JPG", "WEBP", "PNG", "TIFF"}:
            save_kwargs["exif"] = b""
        if fmt == "GIF":
            # GIF 注释（comment）位于 info，保存时会随文件写回，显式置空以去除。
            save_kwargs["comment"] = b""
        image.save(target, format=image_format, **save_kwargs)
    return inspect_file(target)


# ---------------------------------------------------------------------------
# 文档格式清理
# ---------------------------------------------------------------------------


def _pdf_metadata_keys(path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    keys = []
    for k, v in (reader.metadata or {}).items():
        key = str(k).lstrip("/").lower()
        if key in _PDF_CORE_KEYS and (v or "").strip():
            keys.append(key)
    return sorted(keys)


def _clean_pdf(source: Path, target: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    # 显式置空核心元数据字段（使用 PDF 标准键名），避免 pypdf 在保存时注入默认 Producer。
    writer.add_metadata({f"/{key.capitalize()}": "" for key in sorted(_PDF_CORE_KEYS)})
    with open(target, "wb") as fh:
        writer.write(fh)


def _ooxml_metadata_keys(path: Path, core_path: str) -> list[str]:
    """读取 OOXML（docx/xlsx/pptx）zip 内核心属性的非空字段。"""
    import zipfile
    from xml.etree import ElementTree as ET

    local_to_prop = {
        "creator": "author",
        "description": "comments",
        "keywords": "keywords",
        "subject": "subject",
        "title": "title",
        "category": "category",
        "lastModifiedBy": "last_modified_by",
        "revision": "revision",
        "identifier": "identifier",
        "version": "version",
        "created": "created",
        "modified": "modified",
        "lastPrinted": "last_printed",
        "contentStatus": "content_status",
        "template": "template",
    }
    try:
        with zipfile.ZipFile(path) as zin:
            core_xml = zin.read(core_path)
    except Exception:
        return []
    try:
        root = ET.fromstring(core_xml)
    except Exception:
        return []
    keys: list[str] = []
    for child in root:
        local = child.tag.split("}")[-1]
        prop = local_to_prop.get(local)
        if prop is None:
            continue
        if (child.text or "").strip():
            keys.append(prop)
    return sorted(set(keys))


def _clean_ooxml(source: Path, target: Path, core_path: str) -> None:
    """重写 zip 容器内的 core.xml，删除核心属性元素（避免重新注入时间戳）。"""
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(source) as zin:
        names = zin.namelist()
        payloads = {name: zin.read(name) for name in names}
    core_xml = payloads.get(core_path, b"")
    if core_xml:
        try:
            root = ET.fromstring(core_xml)
            for child in list(root):
                root.remove(child)
            payloads[core_path] = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
        except Exception:
            payloads.pop(core_path, None)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            if name not in payloads:
                continue
            zout.writestr(name, payloads[name])


_ODT_META_PATH = "meta.xml"
_ODT_TEXT_PATH = "content.xml"


def _odt_metadata_keys(path: Path) -> list[str]:
    """OpenDocument 文本（ODT）：meta.xml 中 office:meta 下的 dc:*/meta:* 字段。"""
    import zipfile
    from xml.etree import ElementTree as ET

    try:
        with zipfile.ZipFile(path) as zin:
            meta_xml = zin.read(_ODT_META_PATH)
    except Exception:
        return []
    try:
        root = ET.fromstring(meta_xml)
    except Exception:
        return []
    keys: list[str] = []
    for el in root.iter():
        local = el.tag.split("}")[-1]
        if local in {
            "creator", "date", "creation-date", "language", "subject", "title",
            "description", "keyword", "initial-creator", "generator", "editing-cycles",
        }:
            if (el.text or "").strip():
                keys.append(local)
    return sorted(set(keys))


def _clean_odt(source: Path, target: Path) -> None:
    """删除 ODT 的 meta.xml 中全部元数据子元素（保留 office:meta 根）。"""
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(source) as zin:
        names = zin.namelist()
        payloads = {name: zin.read(name) for name in names}
    meta_xml = payloads.get(_ODT_META_PATH, b"")
    if meta_xml:
        try:
            root = ET.fromstring(meta_xml)
            _ODT_META_LOCALS = {
                "creator", "date", "creation-date", "language", "subject", "title",
                "description", "keyword", "initial-creator", "generator", "editing-cycles",
            }
            # 遍历删除所有 dc:*/meta:* 元数据元素（保留结构根）。
            for parent in list(root.iter()):
                for el in list(parent):
                    local = el.tag.split("}")[-1]
                    if local in _ODT_META_LOCALS:
                        parent.remove(el)
            payloads[_ODT_META_PATH] = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
        except Exception:
            payloads.pop(_ODT_META_PATH, None)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            if name not in payloads:
                continue
            zout.writestr(name, payloads[name])


_EPUB_OPF = "META-INF/container.xml"


def _epub_metadata_keys(path: Path) -> list[str]:
    """EPUB：通过 container.xml 找到 OPF，读取其中 dc: 元数据。"""
    import zipfile
    from xml.etree import ElementTree as ET

    try:
        with zipfile.ZipFile(path) as zin:
            names = zin.namelist()
            container_xml = zin.read(_EPUB_OPF)
    except Exception:
        return []
    try:
        croot = ET.fromstring(container_xml)
        rootfile = None
        for el in croot.iter():
            if el.tag.split("}")[-1] == "rootfile":
                rootfile = el.get("full-path")
                break
    except Exception:
        return []
    if not rootfile:
        return []
    try:
        with zipfile.ZipFile(path) as zin:
            opf = ET.fromstring(zin.read(rootfile))
    except Exception:
        return []
    keys: list[str] = []
    for child in opf.iter():
        local = child.tag.split("}")[-1]
        # EPUB 命名空间通常是 dcterms，dc: 元数据
        ns = child.tag.split("}")[0].strip("{}") if "}" in child.tag else ""
        if "purl.org/dc/elements" in ns and (child.text or "").strip():
            keys.append(local)
    return sorted(set(keys))


def _clean_epub(source: Path, target: Path) -> None:
    """重写 EPUB 的 OPF：删除其中 metadata 内的 dc: 元数据元素，保留容器结构。"""
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(source) as zin:
        names = zin.namelist()
        payloads = {name: zin.read(name) for name in names}
    try:
        croot = ET.fromstring(payloads.get(_EPUB_OPF, b""))
        rootfile = None
        for el in croot.iter():
            if el.tag.split("}")[-1] == "rootfile":
                rootfile = el.get("full-path")
                break
    except Exception:
        rootfile = None
    if rootfile and rootfile in payloads:
        try:
            root = ET.fromstring(payloads[rootfile])
            # 定位 package 下的 metadata 元素，清空其 dc 命名空间子元素。
            for el in root.iter():
                if el.tag.split("}")[-1] == "metadata":
                    for sub in list(el):
                        subns = sub.tag.split("}")[0].strip("{}") if "}" in sub.tag else ""
                        if "purl.org/dc/elements" in subns:
                            el.remove(sub)
            payloads[rootfile] = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
        except Exception:
            pass

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            if name not in payloads:
                continue
            zout.writestr(name, payloads[name])


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
