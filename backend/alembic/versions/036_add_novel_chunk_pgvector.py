"""add pgvector column for novel text chunks nearest-neighbor search (PostgreSQL only)

小说源文本块检索此前在 Python 里对全部块逐条算余弦。生产库是 pgvector/pg16，
这里仅在 PostgreSQL 方言下补一个 ``embedding_vec vector(384)`` 列与 HNSW 索引，
由服务层在检索时走数据库级近邻（``<=>``），SQLite（测试/本地）无 vector 类型则跳过。
"""

from alembic import op

revision = "036_add_novel_chunk_pgvector"
down_revision = "035_add_world_map_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite（测试/本地）无 vector 类型，跳过；运行在 PostgreSQL 上时才加列。
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE novel_text_chunks ADD COLUMN IF NOT EXISTS embedding_vec vector(384)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_novel_text_chunks_embedding_vec "
        "ON novel_text_chunks USING hnsw (embedding_vec vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_novel_text_chunks_embedding_vec")
    op.execute("ALTER TABLE novel_text_chunks DROP COLUMN IF EXISTS embedding_vec")
