"""allow snapshot-less generation runs and candidates

生成链路（无原文、只凭想法）没有来源快照：运行记录与候选都必须允许
``snapshot_id`` 为空。提取链路的行为完全不变（仍带快照与证据）。

对应 openspec/changes/ai-progressive-world-building 任务 4。
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "040_allow_snapshotless_generation_runs"
down_revision = "039_add_world_building_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("world_extraction_runs") as batch_op:
        batch_op.alter_column(
            "snapshot_id",
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        )
    with op.batch_alter_table("world_fact_candidates") as batch_op:
        batch_op.alter_column(
            "snapshot_id",
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        )


def downgrade() -> None:
    # 只有不存在无快照记录时才能收紧回 NOT NULL。
    connection = op.get_bind()
    for table in ("world_extraction_runs", "world_fact_candidates"):
        rows = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE snapshot_id IS NULL")
        ).scalar()
        if rows:
            raise RuntimeError(
                f"{table} 存在 {rows} 条无快照记录（生成链路产出），无法回退为 NOT NULL"
            )
    with op.batch_alter_table("world_fact_candidates") as batch_op:
        batch_op.alter_column(
            "snapshot_id",
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        )
    with op.batch_alter_table("world_extraction_runs") as batch_op:
        batch_op.alter_column(
            "snapshot_id",
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        )
