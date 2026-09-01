"""add world_entities and world_entity_relations for typed complex entities

任务 3.2：为势力/地点/物种/事件/力量体系/物品等复杂实体建立独立实体层与类型化关系，
与通用 ``world_asset`` 事实卡并存（事实卡仍是锁定正典的权威载体，本表是结构化索引）。
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "037_add_world_entities_and_relations"
down_revision = "036_add_novel_chunk_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_entities",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("snapshot_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("domain", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("entity_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("normalized_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("attributes_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("evidence_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("fact_layer", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_candidate_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["novel_source_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_world_entities_project_type", "world_entities", ["project_id", "entity_type"])
    op.create_index(
        "ux_world_entities_project_type_key",
        "world_entities",
        ["project_id", "entity_type", "normalized_key"],
        unique=True,
    )

    op.create_table(
        "world_entity_relations",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_entity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_entity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("relation_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("evidence_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_directed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["creative_projects.id"]),
        sa.ForeignKeyConstraint(["source_entity_id"], ["world_entities.id"]),
        sa.ForeignKeyConstraint(["target_entity_id"], ["world_entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_world_entity_relations_project", "world_entity_relations", ["project_id"])
    op.create_index("ix_world_entity_relations_source", "world_entity_relations", ["source_entity_id"])
    op.create_index("ix_world_entity_relations_target", "world_entity_relations", ["target_entity_id"])


def downgrade() -> None:
    op.drop_table("world_entity_relations")
    op.drop_table("world_entities")
