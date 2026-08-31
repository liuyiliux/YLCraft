"""add platform event logs ref_id

角色立绘等非项目场景的事件没有 project_id，无法在事件流里精确筛出
某一条资源（如某个角色）的记录，因此补一个通用的 ref_id 关联字段。

Revision ID: 029_add_platform_event_ref_id
Revises: 028_add_character_relationship_world_time
"""

from alembic import op
import sqlalchemy as sa


revision = "029_add_platform_event_ref_id"
down_revision = "028_add_character_relationship_world_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_event_logs",
        sa.Column("ref_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_platform_event_logs_ref_id", "platform_event_logs", ["ref_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_platform_event_logs_ref_id", table_name="platform_event_logs")
    op.drop_column("platform_event_logs", "ref_id")
