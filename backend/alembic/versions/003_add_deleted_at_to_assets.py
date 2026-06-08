"""create assets, asset_collections, asset_tags tables

这些表在早期通过 SQLModel.create_all() 创建，未纳入初始合并迁移 001。
现在统一纳入迁移管理，直接建表包含 deleted_at 字段。

Revision ID: 003
Revises: 002
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- assets 表 ----
    op.create_table(
        'assets',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('type', sa.String(), index=True, nullable=False),
        sa.Column('platform', sa.String(), server_default='', index=True),
        sa.Column('title', sa.String(), server_default='', index=True),
        sa.Column('author', sa.String(), server_default=''),
        sa.Column('cover_url', sa.String(), server_default=''),
        sa.Column('duration', sa.Integer(), server_default='0'),
        sa.Column('width', sa.Integer(), server_default='0'),
        sa.Column('height', sa.Integer(), server_default='0'),
        sa.Column('file_path', sa.String(), server_default=''),
        sa.Column('file_size', sa.BigInteger(), server_default='0'),
        sa.Column('mime_type', sa.String(), server_default=''),
        sa.Column('status', sa.String(), server_default='parsed', index=True),
        sa.Column('progress', sa.Integer(), server_default='0'),
        sa.Column('source_type', sa.String(), server_default='', index=True),
        sa.Column('metadata_json', sa.Text(), server_default='{}'),
        sa.Column('tags', sa.Text(), server_default='[]'),
        sa.Column('source_url', sa.String(), server_default='', unique=True, index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(), nullable=True, index=True),
    )
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_assets_deleted_at
        ON assets (deleted_at)
        WHERE deleted_at IS NOT NULL
    """)

    # ---- asset_collections 表 ----
    op.create_table(
        'asset_collections',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), server_default='', index=True),
        sa.Column('description', sa.String(), server_default=''),
        sa.Column('cover_asset_id', sa.String(), server_default=''),
        sa.Column('collection_type', sa.String(), server_default='manual'),
        sa.Column('smart_rules', sa.Text(), server_default='{}'),
        sa.Column('asset_ids', sa.Text(), server_default='[]'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(), nullable=True, index=True),
    )

    # ---- asset_tags 表 ----
    op.create_table(
        'asset_tags',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('color', sa.String(), server_default='#1890ff'),
        sa.Column('asset_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('asset_tags')
    op.drop_table('asset_collections')
    op.drop_table('assets')
