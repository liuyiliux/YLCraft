"""add performance indexes

Revision ID: 003
Revises: 002
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 为 asset_nodes 表添加常用索引
    op.create_index(
        'idx_asset_nodes_created_desc',
        'asset_nodes',
        ['created_at'],
        postgresql_where=sa.text('created_at IS NOT NULL')
    )

    op.create_index(
        'idx_asset_nodes_quality_score',
        'asset_nodes',
        ['quality_score'],
        postgresql_where=sa.text('quality_score IS NOT NULL')
    )

    # 2. 为 asset_versions 表添加索引
    op.create_index(
        'idx_asset_versions_asset_node_created',
        'asset_versions',
        ['asset_node_id', 'created_at']
    )

    # 3. 为 asset_embeddings 表添加备用索引（IVFFlat）
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_embeddings_embedding_ivfflat
        ON asset_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)

    # 4. 为 asset_relations 表添加复合索引
    op.create_index(
        'idx_asset_relations_source_type',
        'asset_relations',
        ['source_id', 'relation_type']
    )

    op.create_index(
        'idx_asset_relations_target_type',
        'asset_relations',
        ['target_id', 'relation_type']
    )

    # 5. 为 tags 表添加复合索引
    op.create_index(
        'idx_tags_category_asset_count',
        'tags',
        ['category', 'asset_count']
    )

    # 6. 创建函数用于自动更新 updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # 7. 为 asset_nodes 表创建 updated_at 触发器
    op.execute("""
        DROP TRIGGER IF EXISTS update_asset_nodes_updated_at ON asset_nodes;
        CREATE TRIGGER update_asset_nodes_updated_at
            BEFORE UPDATE ON asset_nodes
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

    # 8. 添加注释
    op.execute("COMMENT ON COLUMN asset_nodes.updated_at IS '自动更新触发器';")


def downgrade() -> None:
    op.drop_index('idx_asset_nodes_created_desc', table_name='asset_nodes')
    op.drop_index('idx_asset_nodes_quality_score', table_name='asset_nodes')
    op.drop_index('idx_asset_versions_asset_node_created', table_name='asset_versions')
    op.execute("DROP INDEX IF EXISTS idx_asset_embeddings_embedding_ivfflat;")
    op.drop_index('idx_asset_relations_source_type', table_name='asset_relations')
    op.drop_index('idx_asset_relations_target_type', table_name='asset_relations')
    op.drop_index('idx_tags_category_asset_count', table_name='tags')

    op.execute("DROP TRIGGER IF EXISTS update_asset_nodes_updated_at ON asset_nodes;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
