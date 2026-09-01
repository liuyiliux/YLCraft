"""add optional per-chunk embeddings for novel source retrieval"""

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = "034_add_novel_chunk_embeddings"
down_revision = "033_add_world_candidate_last_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "novel_text_chunks",
        sa.Column("embedding_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
    )
    op.add_column(
        "novel_text_chunks",
        sa.Column("embedding_model", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
    )
    op.add_column(
        "novel_text_chunks",
        sa.Column("embedding_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="pending"),
    )
    op.create_index("ix_novel_text_chunks_embedding_model", "novel_text_chunks", ["embedding_model"])
    op.create_index("ix_novel_text_chunks_embedding_status", "novel_text_chunks", ["embedding_status"])


def downgrade() -> None:
    op.drop_index("ix_novel_text_chunks_embedding_status", table_name="novel_text_chunks")
    op.drop_index("ix_novel_text_chunks_embedding_model", table_name="novel_text_chunks")
    op.drop_column("novel_text_chunks", "embedding_status")
    op.drop_column("novel_text_chunks", "embedding_model")
    op.drop_column("novel_text_chunks", "embedding_json")
