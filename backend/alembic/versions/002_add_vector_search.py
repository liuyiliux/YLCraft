"""add vector search support

Revision ID: 002
Revises: 001
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AssetEmbedding 表已在 001 创建，这里添加 HNSW 索引
    # 使用 pgvector 的 ivfflat 或 hnsw 索引加速向量搜索

    # 创建 HNSW 索引（推荐，性能更好）
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_embeddings_embedding_hnsw
        ON asset_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200);
    """)

    # 添加 fulltext_search 辅助列（用于混合搜索）
    op.add_column('asset_nodes',
        sa.Column('fulltext_vector', postgresql.TSVECTOR(), nullable=True))

    # 创建 GIN 索引用于全文搜索
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_nodes_fulltext
        ON asset_nodes
        USING gin (fulltext_vector);
    """)

    # 添加向量搜索辅助表（缓存搜索结果）
    op.create_table(
        'asset_search_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('query_hash', sa.String(64), nullable=False, index=True),
        sa.Column('result_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column('total_count', sa.Integer(), server_default='0'),
        sa.Column('params_json', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )

    # 创建搜索历史表
    op.create_table(
        'search_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('query_text', sa.Text(), nullable=True),
        sa.Column('query_vector_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('result_count', sa.Integer(), server_default='0'),
        sa.Column('filters_json', postgresql.JSONB, server_default='{}'),
        sa.Column('search_type', sa.String(), server_default='hybrid'),
        sa.Column('user_id', sa.String(), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建相似资产记录表（用于"还喜欢"推荐）
    op.create_table(
        'similar_asset_pairs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_a_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('asset_b_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('similarity_score', sa.Float(), nullable=False, index=True),
        sa.Column('embedding_type', sa.String(), server_default='image'),
        sa.Column('computed_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建索引
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_similar_pairs_score
        ON similar_asset_pairs (similarity_score DESC);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_similar_pairs_a
        ON similar_asset_pairs (asset_a_id, similarity_score DESC);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_similar_pairs_b
        ON similar_asset_pairs (asset_b_id, similarity_score DESC);
    """)


def downgrade() -> None:
    op.drop_table('similar_asset_pairs')
    op.drop_table('search_history')
    op.drop_table('asset_search_cache')
    op.drop_column('asset_nodes', 'fulltext_vector')
    op.execute("DROP INDEX IF EXISTS idx_asset_embeddings_embedding_hnsw;")
