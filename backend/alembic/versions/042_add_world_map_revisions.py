"""add world_map_revisions history table

版本历史（SCN-05）：每次保存（create / update_map CAS 通过）落一条 append-only
快照，供版本列表 / 两版对比 / 回滚（回滚以历史快照为内容产生新 revision，
不改写历史链）。
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "042_add_world_map_revisions"
down_revision = "041_add_ignored_domain_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_map_revisions",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True),
        sa.Column(
            "map_id",
            sqlmodel.sql.sqltypes.AutoString(),
            sa.ForeignKey("world_map_documents.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("map_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
        sa.Column("operator", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_world_map_revisions_map_id", "world_map_revisions", ["map_id"])
    op.create_index("ix_world_map_revisions_revision", "world_map_revisions", ["revision"])
    op.create_index("ix_world_map_revisions_created_at", "world_map_revisions", ["created_at"])


def downgrade() -> None:
    op.drop_table("world_map_revisions")
