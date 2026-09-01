"""确定性文本分块。

分块规则必须稳定：同一份来源重复导入要得到相同的块边界，否则增量提取
的游标和证据锚点都会失效。块只按段落边界聚合，不切断行内内容。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterator

from app.services.novel_source.txt_import import ChapterSpan

DEFAULT_CHUNK_MAX_CHARS = 1200


@dataclass
class ChunkSpan:
    """一个文本块，偏移相对整篇归一化正文。"""

    ordinal: int
    chapter_ordinal: int | None
    start: int
    end: int
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha1(self.content.encode("utf-8")).hexdigest()


def chunk_text(
    text: str,
    chapters: list[ChapterSpan],
    *,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    max_chunks: int | None = None,
) -> list[ChunkSpan]:
    """按章节顺序把正文切成有稳定偏移的文本块。

    块内以换行为分隔保留原文段落顺序；超过 ``max_chars`` 时从下一段落
    断开，单行超长时不切断行内内容，避免把引文切开导致证据无法逐字校验。
    """
    limit = max(200, int(max_chars or DEFAULT_CHUNK_MAX_CHARS))
    spans: list[ChunkSpan] = []

    for chapter in chapters:
        parts: list[str] = []
        current_start = 0
        current_end = 0
        current_len = 0
        for line_start, line_end, stripped in _iter_lines(text, chapter.start, chapter.end):
            if not stripped:
                continue
            if parts and current_len + len(stripped) + 1 > limit:
                spans.append(
                    _build_span(len(spans) + 1, chapter.ordinal, current_start, current_end, parts)
                )
                parts = []
                current_len = 0
            if not parts:
                current_start = line_start
            else:
                current_len += 1
            parts.append(stripped)
            current_len += len(stripped)
            current_end = line_end
            if max_chunks and len(spans) >= max_chunks:
                return spans[:max_chunks]
        if parts:
            spans.append(
                _build_span(len(spans) + 1, chapter.ordinal, current_start, current_end, parts)
            )
        if max_chunks and len(spans) >= max_chunks:
            return spans[:max_chunks]
    return spans


def _build_span(
    ordinal: int,
    chapter_ordinal: int | None,
    start: int,
    end: int,
    parts: list[str],
) -> ChunkSpan:
    return ChunkSpan(
        ordinal=ordinal,
        chapter_ordinal=chapter_ordinal,
        start=start,
        end=end,
        content="\n".join(parts),
    )


def _iter_lines(text: str, start: int, end: int) -> Iterator[tuple[int, int, str]]:
    """遍历区间内的行，返回 (去空白后的起始偏移, 行尾偏移, 去空白内容)。"""
    position = max(0, start)
    limit = min(len(text), end)
    while position < limit:
        newline = text.find("\n", position)
        line_end = limit if newline == -1 or newline >= limit else newline
        raw = text[position:line_end]
        stripped = raw.strip()
        if stripped:
            lead = len(raw) - len(raw.lstrip())
            yield position + lead, line_end, stripped
        position = line_end + 1
