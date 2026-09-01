"""TXT 来源导入：编码探测、章节切分与原文保存。

导入只做传输噪声归一（BOM、CRLF），不改写正文内容；原文件按快照目录
原样落盘，后续所有证据偏移都基于归一化后的整篇正文计算。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable

#: 无 BOM 时的候选编码顺序。带 UTF-8 BOM 的文件单独识别。
CANDIDATE_ENCODINGS: tuple[str, ...] = ("utf-8", "gb18030", "gbk", "big5")
UTF8_BOM = b"\xef\xbb\xbf"

# 中英混排小说最常见的章节标题形态。故意不做激进匹配：宁可少切一章，
# 也不能把正文里的句子当成章节标题，否则证据偏移和章节溯源都会错位。
CHAPTER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(?:第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章节回卷篇集])\s*\S{0,60}\s*$"),
    re.compile(r"^\s*(?:Chapter|CHAPTER|chapter)\s+[0-9ivxlcdmIVXLCDM]+\b[^\n]{0,60}$"),
    re.compile(r"^\s*(?:卷\s*[0-9零一二三四五六七八九十百千万两]+\s*[：:])?\s*(?:序章|楔子|引子|尾声|后记|番外|终章)\s*\S{0,40}\s*$"),
    re.compile(r"^\s*\d{1,5}\s*[.、]\s*\S[^\n]{0,60}$"),
)

MAX_TITLE_LENGTH = 80


@dataclass
class ChapterSpan:
    """归一化正文中的一个章节区间，偏移相对整篇正文。"""

    ordinal: int
    title: str
    start: int
    end: int

    @property
    def char_count(self) -> int:
        return max(0, self.end - self.start)


@dataclass
class ParsedSource:
    """TXT 解析结果。"""

    text: str
    encoding: str
    checksum: str
    chapters: list[ChapterSpan] = field(default_factory=list)


def source_checksum(raw: bytes) -> str:
    """原文件校验和，用于识别同一来源的重复导入。"""
    return hashlib.sha256(raw).hexdigest()


def detect_encoding(raw: bytes) -> str:
    """按候选编码顺序探测，优先 utf-8，中文旧文件回退 gb18030。"""
    if raw.startswith(UTF8_BOM):
        return "utf-8-sig"
    for encoding in CANDIDATE_ENCODINGS:
        try:
            raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        return encoding
    return "utf-8"


def decode_source(raw: bytes) -> tuple[str, str]:
    """解码原文，返回 (文本, 实际使用的编码)。"""
    encoding = detect_encoding(raw)
    try:
        return raw.decode(encoding), encoding
    except UnicodeDecodeError:
        # 编码探测失败时用替换策略兜底，保证导入不会因为个别坏字节整体失败。
        return raw.decode("utf-8", errors="replace"), "utf-8"


def normalize_source_text(text: str) -> str:
    """只归一传输噪声：去 BOM、统一换行。不改动正文用字。"""
    normalized = text.replace("\ufeff", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized


def detect_chapters(text: str) -> list[ChapterSpan]:
    """按行扫描章节标题，返回带稳定偏移的章节区间。

    没有识别到任何章节标题时退化为单章，保证后续分块和证据链路仍然可用。
    """
    headings: list[tuple[int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and len(stripped) <= MAX_TITLE_LENGTH and _is_chapter_heading(stripped):
            headings.append((offset, stripped))
        offset += len(line)

    if not headings:
        return [ChapterSpan(ordinal=1, title="全文", start=0, end=len(text))]

    spans: list[ChapterSpan] = []
    total = len(text)
    for index, (start, title) in enumerate(headings):
        # 标题行本身不进入正文区间，避免章节正文以标题开头导致证据重复。
        line_end = text.find("\n", start)
        body_start = (line_end + 1) if line_end != -1 else total
        end = headings[index + 1][0] if index + 1 < len(headings) else total
        if end < body_start:
            end = body_start
        spans.append(
            ChapterSpan(
                ordinal=index + 1,
                title=title[:MAX_TITLE_LENGTH],
                start=body_start,
                end=end,
            )
        )
    return [span for span in spans if span.end > span.start] or [
        ChapterSpan(ordinal=1, title="全文", start=0, end=len(text))
    ]


def _is_chapter_heading(line: str) -> bool:
    return any(pattern.match(line) for pattern in CHAPTER_PATTERNS)


def parse_txt(raw: bytes) -> ParsedSource:
    """把原始字节解析为归一化正文 + 章节区间 + 校验和。"""
    decoded, encoding = decode_source(raw)
    text = normalize_source_text(decoded)
    return ParsedSource(
        text=text,
        encoding=encoding,
        checksum=source_checksum(raw),
        chapters=detect_chapters(text),
    )


def chapter_spans_from_segments(
    segments: Iterable[tuple[str, str]],
) -> tuple[str, list[ChapterSpan]]:
    """把书架来源的 [(标题, 正文)] 序列拼成与 TXT 一致的章节结构。

    书架来源的章节边界是明确的，不需要再做标题识别，但最终必须落到
    同一套「整篇正文 + 稳定偏移」契约上，TXT 和书架才能共用后续链路。
    """
    parts: list[str] = []
    spans: list[ChapterSpan] = []
    cursor = 0
    for index, (title, body) in enumerate(segments, start=1):
        cleaned = normalize_source_text(str(body or "")).strip()
        if not cleaned:
            continue
        heading = f"{title}\n" if str(title or "").strip() else ""
        start = cursor + len(heading)
        parts.append(f"{heading}{cleaned}\n\n")
        cursor = start + len(cleaned) + 2
        spans.append(
            ChapterSpan(
                ordinal=len(spans) + 1,
                title=str(title or "").strip() or f"第{index}章",
                start=start,
                end=start + len(cleaned),
            )
        )
    return "".join(parts), spans
