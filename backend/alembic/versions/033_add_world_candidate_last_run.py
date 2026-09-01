"""add last_run_id to world_fact_candidates for delta extraction provenance"""

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = "033_add_world_candidate_last_run"
down_revision = "032_add_novel_source_world"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "world_fact_candidates",
        sa.Column("last_run_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index(
        "ix_world_fact_candidates_last_run_id",
        "world_fact_candidates",
        ["last_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_world_fact_candidates_last_run_id", table_name="world_fact_candidates")
    op.drop_column("world_fact_candidates", "last_run_id")
