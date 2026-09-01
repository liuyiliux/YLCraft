"""pgvector 数据库级近邻检索集成测试。

默认跳过：设置 ``YLCMAFT_PGVECTOR_TEST_URL`` 指向一个 PostgreSQL + pgvector 测试库
（例如 ``postgresql+psycopg://user:pass@localhost:5432/ylcraft_test``）才会真正连接并验证
数据库级近邻检索。生产库本身就是 ``pgvector/pg16``，部署后自动生效；本测试用于在无副作用的
测试库上回归验证 SQL 近邻路径。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine

from app.services.novel_source.service import NovelSourceService

PG_URL = os.getenv("YLCMAFT_PGVECTOR_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="需要设置 YLCMAFT_PGVECTOR_TEST_URL 指向一个 PostgreSQL+pgvector 测试库",
)

_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS novel_source_snapshots (
    id TEXT PRIMARY KEY, title TEXT DEFAULT '', author TEXT DEFAULT '',
    source_kind TEXT DEFAULT 'txt', source_status TEXT DEFAULT 'unknown',
    project_id TEXT, source_asset_id TEXT, original_file_path TEXT DEFAULT '',
    checksum TEXT DEFAULT '', encoding TEXT DEFAULT 'utf-8',
    revision INTEGER DEFAULT 1, parent_snapshot_id TEXT,
    chapter_count INTEGER DEFAULT 0, char_count INTEGER DEFAULT 0,
    last_chapter_ordinal INTEGER DEFAULT 0, indexing_status TEXT DEFAULT 'pending',
    metadata_json TEXT DEFAULT '{}', created_at TIMESTAMP, updated_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS novel_source_chapters (
    id TEXT PRIMARY KEY, snapshot_id TEXT, ordinal INTEGER, title TEXT DEFAULT '',
    start_offset INTEGER DEFAULT 0, end_offset INTEGER DEFAULT 0,
    char_count INTEGER DEFAULT 0, source_chapter_id TEXT, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS novel_text_chunks (
    id TEXT PRIMARY KEY, snapshot_id TEXT, chapter_id TEXT, ordinal INTEGER,
    start_offset INTEGER DEFAULT 0, end_offset INTEGER DEFAULT 0,
    content TEXT DEFAULT '', content_hash TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}', embedding_json TEXT DEFAULT '',
    embedding_model TEXT DEFAULT '', embedding_status TEXT DEFAULT 'pending',
    created_at TIMESTAMP
);
ALTER TABLE novel_text_chunks ADD COLUMN IF NOT EXISTS embedding_vec vector(384);
"""


@pytest.fixture
def pg_session():
    engine = create_engine(PG_URL, future=True)
    with engine.begin() as conn:
        conn.execute(text(_DDL))
    # 每次用例前清空，避免脏数据影响断言。
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE novel_text_chunks, novel_source_chapters, novel_source_snapshots"))
    session = Session(engine)
    yield session
    session.close()
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS novel_text_chunks CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS novel_source_chapters CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS novel_source_snapshots CASCADE"))


def _seed_chunks(session, snapshot_id: str):
    from app.db.models.novel_source import NovelSourceSnapshot, NovelTextChunk

    session.add(
        NovelSourceSnapshot(
            id=snapshot_id, title="pg测试", source_kind="txt",
            indexing_status="pending", metadata_json="{}",
        )
    )
    chunks = [
        NovelTextChunk(id="c1", snapshot_id=snapshot_id, ordinal=1, start_offset=0, end_offset=10, content="林昭推开木门"),
        NovelTextChunk(id="c2", snapshot_id=snapshot_id, ordinal=2, start_offset=10, end_offset=20, content="北岭那场雪灾"),
        NovelTextChunk(id="c3", snapshot_id=snapshot_id, ordinal=3, start_offset=20, end_offset=30, content="沈青砚翻账册"),
    ]
    session.add_all(chunks)
    session.commit()
    # 384 维向量：c1 首维为 1（与查询一致），其余为 0。
    vec_ch1 = [1.0] + [0.0] * 383
    vec_zero = [0.0] * 384
    with session.bind.connect() as conn:
        for chunk_id, vec in (("c1", vec_ch1), ("c2", vec_zero), ("c3", vec_zero)):
            literal = "[" + ",".join(str(v) for v in vec) + "]"
            conn.execute(
                text("UPDATE novel_text_chunks SET embedding_vec = :v::vector WHERE id = :id"),
                {"v": literal, "id": chunk_id},
            )


def test_pgvector_nearest_neighbor_runs_at_database_level(pg_session):
    """PostgreSQL 下走 SQL 近邻，最相似的块排在最前。"""
    snapshot_id = "snap-pg-1"
    _seed_chunks(pg_session, snapshot_id)
    service = NovelSourceService(pg_session)

    query_vec = [1.0] + [0.0] * 383
    results = service.search_chunks(snapshot_id, "林昭", query_embedding=query_vec, top_k=3)

    assert results, "pgvector 路径应返回结果"
    assert results[0]["chunk_id"] == "c1", "最相似块应排第一"
    assert results[0]["retrieval"] == "hybrid"
    assert results[0]["vector_score"] > 0.9


def test_pgvector_falls_back_when_query_dimension_mismatch(pg_session):
    """查询向量不是 384 维时，pgvector 路径不触发（维度与列不一致）。"""
    snapshot_id = "snap-pg-2"
    _seed_chunks(pg_session, snapshot_id)
    service = NovelSourceService(pg_session)

    # 2 维查询向量：_pgvector_usable 应返回 False，回退 Python 路径。
    results = service.search_chunks(snapshot_id, "林昭", query_embedding=[1.0, 0.0], top_k=3)
    assert results
    # 回退路径下，c1 的 embedding_json 为空，按精确词命中的是 c1（含「林昭」）。
    assert results[0]["chunk_id"] == "c1"
