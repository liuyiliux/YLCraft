"""add character relationship world and time dimension"""
from alembic import op
import sqlalchemy as sa

revision = "028_add_character_relationship_world_time"
down_revision = "027_add_character_extract_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加世界使用关联ID（NULL表示全局关系）
    op.add_column(
        "character_relationships",
        sa.Column("world_usage_id", sa.String(length=64), nullable=True, index=True),
    )
    # 添加时间线阶段（如：前期/中期/后期/回忆/未来等）
    op.add_column(
        "character_relationships",
        sa.Column("timeline_phase", sa.String(length=64), nullable=True, index=True, server_default=""),
    )
    # 添加章节号（用于小说中按章节标记关系变化）
    op.add_column(
        "character_relationships",
        sa.Column("chapter_number", sa.Integer(), nullable=True),
    )
    # 创建复合索引
    op.create_index(
        "ix_character_relationships_world_phase",
        "character_relationships",
        ["character_id", "world_usage_id", "timeline_phase"],
    )


def downgrade() -> None:
    op.drop_index("ix_character_relationships_world_phase", table_name="character_relationships")
    op.drop_column("character_relationships", "chapter_number")
    op.drop_column("character_relationships", "timeline_phase")
    op.drop_column("character_relationships", "world_usage_id")
