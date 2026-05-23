"""init asset hub

Revision ID: 001
Revises:
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建 asset_nodes 表
    op.create_table(
        'asset_nodes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, index=True),
        sa.Column('asset_type', sa.String(), nullable=False, index=True),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=True, index=True),
        sa.Column('thumbnail_url', sa.String(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, server_default='{}'),
        sa.Column('tags_json', postgresql.JSONB, server_default='[]'),
        sa.Column('use_count', sa.Integer(), server_default='0', index=True),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('phash', sa.String(), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建 asset_versions 表
    op.create_table(
        'asset_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_node_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('version_number', sa.Integer(), nullable=False, index=True),
        sa.Column('prompt_used', sa.Text(), nullable=True),
        sa.Column('model_used', sa.String(), nullable=True),
        sa.Column('params_json', postgresql.JSONB, server_default='{}'),
        sa.Column('lineage_json', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), index=True),
    )

    # 创建 asset_representations 表
    op.create_table(
        'asset_representations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_version_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_versions.id'), nullable=False, index=True),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('format', sa.String(), nullable=True),
        sa.Column('extra_json', postgresql.JSONB, server_default='{}'),
    )

    # 创建 asset_embeddings 表（向量）
    op.create_table(
        'asset_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_node_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=False, unique=True, index=True),
        sa.Column('embedding', Vector(1024), nullable=True),
        sa.Column('embedding_model', sa.String(), server_default='paraphrase-multilingual-MiniLM-L12-v2'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建 asset_relations 表
    op.create_table(
        'asset_relations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('relation_type', sa.String(), nullable=False, index=True),
        sa.Column('context_json', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建 tags 表
    op.create_table(
        'tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, index=True),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tags.id'), nullable=True, index=True),
        sa.Column('level', sa.Integer(), server_default='0', index=True),
        sa.Column('path', sa.String(), nullable=False, index=True),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=True, index=True),
        sa.Column('asset_count', sa.Integer(), server_default='0', index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建 asset_tag_links 表
    op.create_table(
        'asset_tag_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_node_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tags.id'), nullable=False, index=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('source', sa.String(), server_default='manual'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建 ai_models 表
    op.create_table(
        'ai_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_node_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('model_type', sa.String(), nullable=False, index=True),
        sa.Column('base_model', sa.String(), nullable=False, index=True),
        sa.Column('file_hash', sa.String(), nullable=False, index=True),
        sa.Column('civitai_model_id', sa.String(), server_default='', index=True),
        sa.Column('civitai_version_id', sa.String(), server_default=''),
        sa.Column('trigger_words', sa.String(), server_default=''),
        sa.Column('recommended_weight', sa.Float(), server_default='1.0'),
        sa.Column('training_resolution', sa.String(), server_default=''),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), server_default='0'),
        sa.Column('preview_urls', sa.Text(), server_default='[]'),
    )


def downgrade() -> None:
    op.drop_table('ai_models')
    op.drop_table('asset_tag_links')
    op.drop_table('tags')
    op.drop_table('asset_relations')
    op.drop_table('asset_embeddings')
    op.drop_table('asset_representations')
    op.drop_table('asset_versions')
    op.drop_table('asset_nodes')
