"""小说来源快照服务：导入、章节/文本块持久化和证据定位。

TXT 导入和书架导入在这里归一为同一份快照契约，后续提取、检索和审阅
都不需要区分来源类型。来源内容始终只读。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text
from sqlmodel import Session, select

from app.db.models.novel_source import (
    NovelSourceChapter,
    NovelSourceSnapshot,
    NovelTextChunk,
    SnapshotIndexingStatus,
    SourceKind,
    SourceStatus,
)
from app.services.creative_project.service import dumps_json, loads_json
from app.services.asset_file_resolver import project_root, resolve_storage_path, to_storage_path
from app.services.novel_source.chunking import DEFAULT_CHUNK_MAX_CHARS, ChunkSpan, chunk_text
from app.services.novel_source.contracts import EvidenceAnchor
from app.services.novel_source.txt_import import ChapterSpan, chapter_spans_from_segments, parse_txt

logger = logging.getLogger("ylcraft.novel_source")

#: 项目根（YLCraft/）。本地文件一律保存相对路径，保证跨机器可移植。
_PROJECT_ROOT = project_root()
STORAGE_ROOT = _PROJECT_ROOT / "backend" / "app" / "storage" / "novel_sources"

VALID_SOURCE_STATUSES = tuple(item.value for item in SourceStatus)


class NovelSourceService:
    """来源快照的导入与读取。"""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_txt(
        self,
        *,
        raw: bytes,
        file_name: str,
        title: str = "",
        author: str = "",
        source_status: str = SourceStatus.UNKNOWN.value,
        project_id: str | None = None,
        source_asset_id: str | None = None,
        max_chars_per_chunk: int = DEFAULT_CHUNK_MAX_CHARS,
    ) -> NovelSourceSnapshot:
        """导入本地 TXT：保留原文件、落盘归一化正文并生成章节与文本块。"""
        if not raw:
            raise ValueError("上传的 TXT 内容为空")

        parsed = parse_txt(raw)
        if not parsed.text.strip():
            raise ValueError("TXT 解析后没有可用正文")

        safe_name = _safe_file_name(file_name)
        snapshot = NovelSourceSnapshot(
            title=(title or "").strip() or _title_from_file_name(safe_name),
            author=(author or "").strip(),
            source_kind=SourceKind.TXT.value,
            source_status=_normalize_source_status(source_status),
            project_id=project_id or None,
            source_asset_id=source_asset_id or None,
            checksum=parsed.checksum,
            encoding=parsed.encoding,
            char_count=len(parsed.text),
        )
        self.session.add(snapshot)
        self.session.flush()

        source_path = self._persist_source_files(snapshot.id, parsed.text, raw_bytes=raw, file_name=safe_name)
        snapshot.original_file_path = _relative_to_project(source_path)
        self._persist_chapters_and_chunks(snapshot, parsed.chapters, parsed.text, max_chars_per_chunk)

        metadata = {
            "original_upload_path": _relative_to_project(
                self._snapshot_dir(snapshot.id) / f"original{_suffix_of(safe_name)}"
            )
            if raw
            else "",
            "imported_file_name": safe_name,
        }
        snapshot.metadata_json = dumps_json(metadata)
        return self._finalize_snapshot(snapshot)

    def import_bookshelf(
        self,
        *,
        title: str,
        author: str = "",
        chapters: list[dict[str, Any]],
        source_status: str = SourceStatus.SERIAL.value,
        project_id: str | None = None,
        source_asset_id: str | None = None,
        max_chars_per_chunk: int = DEFAULT_CHUNK_MAX_CHARS,
    ) -> NovelSourceSnapshot:
        """导入书架选定章节，落到与 TXT 相同的快照契约。"""
        segments = [
            (
                str(item.get("title") or "").strip(),
                str(item.get("content") or ""),
            )
            for item in chapters
            if isinstance(item, dict)
        ]
        if not any(body.strip() for _, body in segments):
            raise ValueError("没有可导入的章节正文")

        text, spans = chapter_spans_from_segments(segments)
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        source_chapter_ids = [
            str(item.get("chapter_id") or "").strip()
            for item in chapters
            if isinstance(item, dict)
        ]

        snapshot = NovelSourceSnapshot(
            title=(title or "").strip() or "未命名书源",
            author=(author or "").strip(),
            source_kind=SourceKind.BOOKSHELF.value,
            source_status=_normalize_source_status(source_status),
            project_id=project_id or None,
            source_asset_id=source_asset_id or None,
            checksum=checksum,
            encoding="utf-8",
            char_count=len(text),
        )
        self.session.add(snapshot)
        self.session.flush()

        source_path = self._persist_source_files(snapshot.id, text)
        snapshot.original_file_path = _relative_to_project(source_path)
        self._persist_chapters_and_chunks(
            snapshot,
            spans,
            text,
            max_chars_per_chunk,
            source_chapter_ids=source_chapter_ids,
        )
        snapshot.metadata_json = dumps_json({"chapter_sources": len(segments)})
        return self._finalize_snapshot(snapshot)

    def append_bookshelf_chapters(
        self,
        snapshot_id: str,
        *,
        chapters: list[dict[str, Any]],
        max_chars_per_chunk: int = DEFAULT_CHUNK_MAX_CHARS,
    ) -> NovelSourceSnapshot:
        """连载来源的增量同步：在原快照上追加新章节与新文本块。

        已导入的章节不会被重新生成，已有证据锚点保持有效；只有新块进入
        后续提取的增量游标。
        """
        snapshot = self._require_snapshot(snapshot_id)
        if snapshot.source_status != SourceStatus.SERIAL.value:
            raise ValueError("只有连载来源支持增量追加章节")

        existing_titles = {str(item.title).strip() for item in self.list_chapters(snapshot.id)}
        new_items = [
            item
            for item in chapters
            if isinstance(item, dict)
            and str(item.get("title") or "").strip()
            and str(item.get("title") or "").strip() not in existing_titles
            and str(item.get("content") or "").strip()
        ]
        new_segments = [
            (str(item.get("title") or "").strip(), str(item.get("content") or ""))
            for item in new_items
        ]
        if not new_segments:
            raise ValueError("没有需要追加的新章节")
        source_chapter_ids = [str(item.get("chapter_id") or "").strip() or None for item in new_items]

        base_text = self.load_source_text(snapshot.id)
        prefix = base_text if base_text.endswith("\n\n") or not base_text else f"{base_text}\n\n"
        appended_text, appended_spans = chapter_spans_from_segments(new_segments)
        full_text = f"{prefix}{appended_text}"
        offset_shift = len(prefix)

        shifted = [
            ChapterSpan(
                ordinal=snapshot.chapter_count + index + 1,
                title=span.title,
                start=span.start + offset_shift,
                end=span.end + offset_shift,
            )
            for index, span in enumerate(appended_spans)
        ]
        self._persist_source_files(snapshot.id, full_text)
        start_ordinal = snapshot.chapter_count
        for index, span in enumerate(shifted):
            chapter = NovelSourceChapter(
                snapshot_id=snapshot.id,
                ordinal=start_ordinal + index + 1,
                title=span.title,
                start_offset=span.start,
                end_offset=span.end,
                char_count=span.char_count,
                source_chapter_id=source_chapter_ids[index]
                if index < len(source_chapter_ids)
                else None,
            )
            self.session.add(chapter)
        self.session.flush()

        chapter_rows = {
            row.ordinal: row for row in self.list_chapters(snapshot.id)
        }
        chunk_start = _next_chunk_ordinal(self.session, snapshot.id)
        for span in chunk_text(full_text, shifted, max_chars=max_chars_per_chunk):
            chunk_start += 1
            self.session.add(
                self._chunk_row(snapshot.id, span, chapter_rows, ordinal=chunk_start)
            )

        snapshot.char_count = len(full_text)
        return self._finalize_snapshot(snapshot)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_snapshot(self, snapshot_id: str) -> NovelSourceSnapshot | None:
        return self.session.get(NovelSourceSnapshot, snapshot_id)

    def list_snapshots(
        self,
        *,
        project_id: str | None = None,
        source_kind: str | None = None,
        limit: int = 50,
    ) -> list[NovelSourceSnapshot]:
        statement = select(NovelSourceSnapshot)
        if project_id:
            statement = statement.where(NovelSourceSnapshot.project_id == project_id)
        if source_kind:
            statement = statement.where(NovelSourceSnapshot.source_kind == source_kind)
        statement = statement.order_by(NovelSourceSnapshot.created_at.desc()).limit(max(1, min(int(limit or 50), 200)))  # type: ignore[attr-defined]
        return list(self.session.exec(statement).all())

    def list_chapters(self, snapshot_id: str) -> list[NovelSourceChapter]:
        statement = (
            select(NovelSourceChapter)
            .where(NovelSourceChapter.snapshot_id == snapshot_id)
            .order_by(NovelSourceChapter.ordinal)  # type: ignore[attr-defined]
        )
        return list(self.session.exec(statement).all())

    def list_chunks(
        self,
        snapshot_id: str,
        *,
        after_ordinal: int | None = None,
        limit: int = 200,
    ) -> list[NovelTextChunk]:
        statement = select(NovelTextChunk).where(NovelTextChunk.snapshot_id == snapshot_id)
        if after_ordinal is not None:
            statement = statement.where(NovelTextChunk.ordinal > int(after_ordinal))
        statement = statement.order_by(NovelTextChunk.ordinal).limit(max(1, min(int(limit or 200), 2000)))  # type: ignore[attr-defined]
        return list(self.session.exec(statement).all())

    async def index_chunk_embeddings(
        self,
        snapshot_id: str,
        *,
        embedder: Any,
        model_name: str = "",
        max_chunks: int = 2000,
    ) -> dict[str, Any]:
        """为文本块生成可选向量；单块失败不阻断其他块。"""
        snapshot = self._require_snapshot(snapshot_id)
        chunks = self.list_chunks(snapshot_id, limit=max(1, min(int(max_chunks or 2000), 2000)))
        if not chunks:
            return {"snapshot_id": snapshot_id, "indexed": 0, "failed": 0, "total": 0}

        texts = [chunk.content for chunk in chunks]
        try:
            vectors = await embedder(texts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("novel chunk embedding batch failed snapshot=%s: %s", snapshot_id, exc)
            vectors = [None] * len(chunks)

        indexed = failed = 0
        dialect_is_pg = False
        try:
            bind = self.session.bind
            dialect_is_pg = bool(bind and bind.dialect.name == "postgresql")
        except Exception:  # noqa: BLE001
            dialect_is_pg = False

        for chunk, vector in zip(chunks, vectors):
            if vector and isinstance(vector, (list, tuple)):
                values = [float(value) for value in vector]
                chunk.embedding_json = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
                chunk.embedding_model = str(model_name or "unknown")
                chunk.embedding_status = "ready"
                indexed += 1
                # PostgreSQL + 默认 384 维模型：同时写入 pgvector 列，供数据库级近邻检索。
                if dialect_is_pg and len(values) == 384:
                    vec_literal = "[" + ",".join(str(value) for value in values) + "]"
                    self.session.exec(
                        text("UPDATE novel_text_chunks SET embedding_vec = :v::vector WHERE id = :id"),
                        {"v": vec_literal, "id": chunk.id},
                    )
            else:
                chunk.embedding_json = ""
                chunk.embedding_model = str(model_name or "")
                chunk.embedding_status = "failed"
                failed += 1
            self.session.add(chunk)
        self.session.commit()

        if indexed == len(chunks):
            snapshot.indexing_status = SnapshotIndexingStatus.INDEXED.value
        elif indexed > 0:
            snapshot.indexing_status = SnapshotIndexingStatus.INDEXED.value
        elif failed:
            snapshot.indexing_status = SnapshotIndexingStatus.FAILED.value
        else:
            snapshot.indexing_status = SnapshotIndexingStatus.SKIPPED.value
        snapshot.updated_at = datetime.now()
        self.session.add(snapshot)
        self.session.commit()

        return {"snapshot_id": snapshot_id, "indexed": indexed, "failed": failed, "total": len(chunks)}

    def _pgvector_usable(self, snapshot_id: str, dim: int) -> bool:
        """是否走 pgvector 数据库级近邻：仅当 PostgreSQL、查询向量维度与列一致（384）且已有索引向量。"""
        if dim != 384:
            return False
        try:
            bind = self.session.bind
            if bind is None or bind.dialect.name != "postgresql":
                return False
            hit = self.session.exec(
                text(
                    "SELECT 1 FROM novel_text_chunks "
                    "WHERE snapshot_id = :sid AND embedding_vec IS NOT NULL LIMIT 1"
                ),
                {"sid": snapshot_id},
            ).first()
            return hit is not None
        except Exception:  # noqa: BLE001 - 列不存在或方言不支持时安全回退到 Python 路径
            return False

    def search_chunks(
        self,
        snapshot_id: str,
        query: str,
        *,
        query_embedding: list[float] | None = None,
        top_k: int = 10,
        vector_weight: float = 0.65,
        exact_weight: float = 0.35,
        with_neighbors: int = 0,
    ) -> list[dict[str, Any]]:
        """混合召回：精确词命中 + 向量相似度，始终返回来源锚点。

        PostgreSQL + pgvector 环境下走数据库级近邻（``<=>`` 排序出候选集再混合打分），
        避免把全部文本块拉回 Python 逐条算余弦；其它环境回退到精确 + JSON 向量混合。
        ``with_neighbors`` 为每条命中附加前后 N 个文本块作为上下文邻居；邻居只是原文摘录，
        不参与排序，也不冒充命中结果。
        """
        clean_query = str(query or "").strip()
        if not clean_query:
            return []
        qvec = _normalize_vector(query_embedding)
        if qvec and self._pgvector_usable(snapshot_id, len(qvec)):
            results = self._search_chunks_pgvector(
                snapshot_id, clean_query, qvec, top_k, vector_weight, exact_weight
            )
        else:
            results = self._search_chunks_python(
                snapshot_id, clean_query, qvec, top_k, vector_weight, exact_weight
            )
        self._attach_neighbors(snapshot_id, results, with_neighbors)
        return results

    def _search_chunks_pgvector(
        self,
        snapshot_id: str,
        clean_query: str,
        qvec: list[float],
        top_k: int,
        vector_weight: float,
        exact_weight: float,
    ) -> list[dict[str, Any]]:
        terms = [term for term in clean_query.split() if term] or [clean_query]
        candidate_k = max(50, int(top_k) * 5)
        vector_literal = "[" + ",".join(str(value) for value in qvec) + "]"
        rows = self.session.exec(
            text(
                """
                SELECT id, ordinal, chapter_id, start_offset, end_offset, content,
                       1 - (embedding_vec <=> :q::vector) AS vector_score
                FROM novel_text_chunks
                WHERE snapshot_id = :sid AND embedding_vec IS NOT NULL
                ORDER BY embedding_vec <=> :q::vector
                LIMIT :k
                """
            ),
            {"q": vector_literal, "sid": snapshot_id, "k": candidate_k},
        ).all()
        results: list[dict[str, Any]] = []
        for row in rows:
            exact = _lexical_score(row.content, terms)
            vector = float(row.vector_score)
            score = vector_weight * vector + exact_weight * exact
            results.append({
                "chunk_id": row.id,
                "chunk_ordinal": row.ordinal,
                "chapter_id": row.chapter_id,
                "start_offset": row.start_offset,
                "end_offset": row.end_offset,
                "content": row.content,
                "exact_score": round(exact, 6),
                "vector_score": round(vector, 6),
                "score": round(score, 6),
                "retrieval": "hybrid",
            })
        results.sort(key=lambda item: (-item["score"], item["chunk_ordinal"]))
        return results[: max(1, min(int(top_k or 10), 100))]

    def _search_chunks_python(
        self,
        snapshot_id: str,
        clean_query: str,
        qvec: list[float] | None,
        top_k: int,
        vector_weight: float,
        exact_weight: float,
    ) -> list[dict[str, Any]]:
        rows = self.list_chunks(snapshot_id, limit=2000)
        terms = [term for term in clean_query.split() if term] or [clean_query]
        results: list[dict[str, Any]] = []
        for row in rows:
            exact = _lexical_score(row.content, terms)
            vector = 0.0
            if qvec and row.embedding_json:
                try:
                    vector = max(0.0, _cosine(qvec, _normalize_vector(json.loads(row.embedding_json)) or []))
                except (TypeError, ValueError, json.JSONDecodeError):
                    vector = 0.0
            score = vector_weight * vector + exact_weight * exact if qvec else exact
            if score <= 0:
                continue
            results.append({
                "chunk_id": row.id,
                "chunk_ordinal": row.ordinal,
                "chapter_id": row.chapter_id,
                "start_offset": row.start_offset,
                "end_offset": row.end_offset,
                "content": row.content,
                "exact_score": round(exact, 6),
                "vector_score": round(vector, 6),
                "score": round(score, 6),
                "retrieval": "hybrid" if qvec and vector else "exact",
            })
        results.sort(key=lambda item: (-item["score"], item["chunk_ordinal"]))
        return results[: max(1, min(int(top_k or 10), 100))]

    def _attach_neighbors(
        self, snapshot_id: str, results: list[dict[str, Any]], with_neighbors: int
    ) -> None:
        span = max(0, min(int(with_neighbors or 0), 3))
        if not span or not results:
            for item in results:
                item["neighbors"] = []
            return
        lo = min(item["chunk_ordinal"] for item in results) - span
        hi = max(item["chunk_ordinal"] for item in results) + span
        rows = self.session.exec(
            select(NovelTextChunk).where(
                NovelTextChunk.snapshot_id == snapshot_id,
                NovelTextChunk.ordinal >= lo,
                NovelTextChunk.ordinal <= hi,
            )
        ).all()
        by_ordinal = {row.ordinal: row for row in rows}
        for item in results:
            neighbors: list[dict[str, Any]] = []
            seen: set[int] = {item["chunk_ordinal"]}
            for delta in range(-span, span + 1):
                if delta == 0:
                    continue
                row = by_ordinal.get(int(item["chunk_ordinal"]) + delta)
                if row is None or row.ordinal in seen:
                    continue
                seen.add(row.ordinal)
                neighbors.append(
                    {
                        "chunk_id": row.id,
                        "chunk_ordinal": row.ordinal,
                        "start_offset": row.start_offset,
                        "end_offset": row.end_offset,
                        "content": row.content[:300],
                    }
                )
            item["neighbors"] = neighbors

    def load_source_text(self, snapshot_id: str) -> str:
        """读取归一化后的整篇正文，用于证据校验和顺序检索。"""
        snapshot = self._require_snapshot(snapshot_id)
        path = _resolve_storage_path(snapshot.original_file_path)
        if not path or not path.is_file():
            raise ValueError("来源正文文件缺失，无法校验证据")
        return path.read_text(encoding="utf-8", errors="ignore")

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def locate_quote(
        self,
        snapshot_id: str,
        quote: str,
        *,
        source_text: str = "",
        chunks: Iterable[NovelTextChunk] | None = None,
    ) -> EvidenceAnchor | None:
        """把逐字引文定位回具体文本块和字符偏移。

        引文必须逐字存在于正文中，否则返回 None——模型改写或拼接过的引文
        不能作为证据。
        """
        cleaned = str(quote or "").strip()
        if not cleaned:
            return None
        text = source_text or self.load_source_text(snapshot_id)
        index = text.find(cleaned)
        if index < 0:
            return None
        end = index + len(cleaned)
        chunk_rows = list(chunks) if chunks is not None else self.list_chunks(snapshot_id)
        owner = next(
            (
                row
                for row in sorted(chunk_rows, key=lambda item: item.ordinal)
                if row.start_offset <= index < max(row.end_offset, row.start_offset + 1)
            ),
            None,
        )
        if owner is None:
            owner = next(
                (
                    row
                    for row in sorted(chunk_rows, key=lambda item: item.ordinal)
                    if not (row.end_offset <= index or row.start_offset >= end)
                ),
                None,
            )
        return EvidenceAnchor(
            chunk_id=owner.id if owner else "",
            chunk_ordinal=owner.ordinal if owner else 0,
            chapter_ordinal=self._chapter_ordinal_of(owner),
            start_offset=index,
            end_offset=end,
            quote=cleaned,
        )

    def _chapter_ordinal_of(self, chunk: NovelTextChunk | None) -> int | None:
        if chunk is None or not chunk.chapter_id:
            return None
        chapter = self.session.get(NovelSourceChapter, chunk.chapter_id)
        return chapter.ordinal if chapter else None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_snapshot(self, snapshot_id: str) -> NovelSourceSnapshot:
        snapshot = self.session.get(NovelSourceSnapshot, snapshot_id)
        if not snapshot:
            raise ValueError("来源快照不存在")
        return snapshot

    def _snapshot_dir(self, snapshot_id: str) -> Path:
        return _storage_root() / snapshot_id

    def _persist_source_files(
        self,
        snapshot_id: str,
        text: str,
        *,
        raw_bytes: bytes | None = None,
        file_name: str = "",
    ) -> Path:
        directory = self._snapshot_dir(snapshot_id)
        directory.mkdir(parents=True, exist_ok=True)
        source_path = directory / "source.txt"
        source_path.write_text(text, encoding="utf-8")
        if raw_bytes is not None:
            suffix = _suffix_of(file_name) or ".txt"
            (directory / f"original{suffix}").write_bytes(raw_bytes)
        return source_path

    def _persist_chapters_and_chunks(
        self,
        snapshot: NovelSourceSnapshot,
        spans: list[ChapterSpan],
        text: str,
        max_chars_per_chunk: int,
        *,
        source_chapter_ids: list[str] | None = None,
    ) -> None:
        chapter_rows: dict[int, NovelSourceChapter] = {}
        for index, span in enumerate(spans):
            chapter = NovelSourceChapter(
                snapshot_id=snapshot.id,
                ordinal=index + 1,
                title=span.title,
                start_offset=span.start,
                end_offset=span.end,
                char_count=span.char_count,
                source_chapter_id=(source_chapter_ids or [])[index]
                if source_chapter_ids and index < len(source_chapter_ids)
                else None,
            )
            self.session.add(chapter)
            chapter_rows[chapter.ordinal] = chapter
        self.session.flush()

        for ordinal, span in enumerate(
            chunk_text(text, spans, max_chars=max_chars_per_chunk), start=1
        ):
            self.session.add(self._chunk_row(snapshot.id, span, chapter_rows, ordinal=ordinal))

    @staticmethod
    def _chunk_row(
        snapshot_id: str,
        span: ChunkSpan,
        chapter_rows: dict[int, NovelSourceChapter],
        *,
        ordinal: int,
    ) -> NovelTextChunk:
        chapter = chapter_rows.get(span.chapter_ordinal or 0) if span.chapter_ordinal else None
        return NovelTextChunk(
            snapshot_id=snapshot_id,
            chapter_id=chapter.id if chapter else None,
            ordinal=ordinal,
            start_offset=span.start,
            end_offset=span.end,
            content=span.content,
            content_hash=span.content_hash,
        )

    def _finalize_snapshot(self, snapshot: NovelSourceSnapshot) -> NovelSourceSnapshot:
        chapters = self.list_chapters(snapshot.id)
        snapshot.chapter_count = len(chapters)
        snapshot.last_chapter_ordinal = max((row.ordinal for row in chapters), default=0)
        # 向量索引尚未接线；精确/顺序检索已可独立完成证据校验，因此标记为跳过
        # 而不是失败，避免前端把可用来源显示成异常状态。
        snapshot.indexing_status = SnapshotIndexingStatus.SKIPPED.value
        snapshot.updated_at = datetime.now()
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot


def _next_chunk_ordinal(session: Session, snapshot_id: str) -> int:
    rows = session.exec(
        select(NovelTextChunk).where(NovelTextChunk.snapshot_id == snapshot_id)
    ).all()
    return max((int(row.ordinal) for row in rows), default=0)


def _normalize_source_status(value: str) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in VALID_SOURCE_STATUSES else SourceStatus.UNKNOWN.value


def _safe_file_name(file_name: str) -> str:
    name = Path(str(file_name or "novel.txt")).name
    return name[:120] or "novel.txt"


def _suffix_of(file_name: str) -> str:
    return Path(str(file_name or "")).suffix.lower() or ".txt"


def _title_from_file_name(file_name: str) -> str:
    return Path(file_name).stem[:120] or "未命名小说"


def _resolve_storage_path(value: str) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return resolve_storage_path(raw)
    except (OSError, ValueError):
        return None


def _relative_to_project(path: Path) -> str:
    try:
        return to_storage_path(path)
    except ValueError:
        return str(path).replace("\\", "/")


def _normalize_vector(values: Any) -> list[float] | None:
    if not isinstance(values, (list, tuple)) or not values:
        return None
    result = [float(value) for value in values]
    norm = math.sqrt(sum(value * value for value in result))
    return [value / norm for value in result] if norm else None


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _lexical_score(content: str, terms: list[str]) -> float:
    body = str(content or "").lower()
    hits = sum(1 for term in terms if term.lower() in body)
    if not hits:
        return 0.0
    return min(1.0, hits / max(1, len(terms)))


def _storage_root() -> Path:
    """Return the configured source root from the local settings mirror."""
    settings_path = project_root() / "backend" / "app" / "data" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        configured = str(settings.get("novel_source_path") or "").strip()
        if configured:
            resolved = resolve_storage_path(configured)
            resolved.relative_to(project_root())
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return STORAGE_ROOT
