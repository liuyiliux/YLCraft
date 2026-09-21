"""add previs motion assets and seed built-in motions

Revision ID: 044_add_previs_motion_assets
Revises: 043_add_writing_style_profiles

建表 + 灌入内置动作。种子数据从 app 包导入（与 `022_seed_platform_prompt_templates`
同一范式），**不在这里复制一份姿势数据**——复制会让"种子"出现两个真源，而动作数据将来
一定会改。代价是重跑旧迁移会得到当时的最新种子，这对参考数据来说正是想要的行为。

已有库若要补新动作，跑 `python -m app.scripts.seed_previs_motions`（按 slug 幂等 upsert），
不需要再写一个数据迁移。
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.services.previs.motion_seed import seed_motion_specs
from app.services.previs.motion_service import LICENSE_GENERATED, ORIGIN_GENERATED

revision = "044_add_previs_motion_assets"
down_revision = "043_add_writing_style_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "previs_motion_assets",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("carrier", sa.String(length=20), nullable=False, server_default="params"),
        sa.Column("skeleton", sa.String(length=60), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fps", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("frame_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loopable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("origin", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("license", sa.String(length=200), nullable=True),
        sa.Column("license_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_previs_motion_assets_slug", "previs_motion_assets", ["slug"], unique=True)
    op.create_index("ix_previs_motion_assets_carrier", "previs_motion_assets", ["carrier"], unique=False)
    op.create_index("ix_previs_motion_assets_skeleton", "previs_motion_assets", ["skeleton"], unique=False)
    op.create_index("ix_previs_motion_assets_category", "previs_motion_assets", ["category"], unique=False)
    op.create_index("ix_previs_motion_assets_is_active", "previs_motion_assets", ["is_active"], unique=False)
    op.create_index("ix_previs_motion_assets_created_at", "previs_motion_assets", ["created_at"], unique=False)
    op.create_index("ix_previs_motion_assets_updated_at", "previs_motion_assets", ["updated_at"], unique=False)

    # 离线模式（`alembic upgrade --sql`）没有真实连接：SELECT 会失败，且 SQLAlchemy 无法为
    # JSONB 字面量渲染 SQL。离线只出 DDL，种子数据交给运行时的 seed_default_motions() 保证。
    if getattr(op.get_context(), "as_sql", False):
        return

    bind = op.get_bind()
    table = sa.table(
        "previs_motion_assets",
        sa.column("id", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("carrier", sa.String()),
        sa.column("skeleton", sa.String()),
        sa.column("category", sa.String()),
        sa.column("tags_json", postgresql.JSONB()),
        sa.column("duration_seconds", sa.Float()),
        sa.column("fps", sa.Integer()),
        sa.column("frame_count", sa.Integer()),
        sa.column("loopable", sa.Boolean()),
        sa.column("payload_json", postgresql.JSONB()),
        sa.column("file_path", sa.String()),
        sa.column("origin", sa.String()),
        sa.column("license", sa.String()),
        sa.column("license_url", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    existing = {row[0] for row in bind.execute(sa.select(table.c.slug)).fetchall()}
    now = datetime.utcnow()
    rows = [
        {
            "id": f"motion-{spec['slug']}",
            "slug": spec["slug"],
            "name": spec["name"],
            "carrier": spec["carrier"],
            "skeleton": spec["skeleton"],
            "category": spec["category"],
            "tags_json": list(spec["tags"]),
            "duration_seconds": spec["duration_seconds"],
            "fps": spec["fps"],
            "frame_count": spec["frame_count"],
            "loopable": spec["loopable"],
            "payload_json": spec["payload"],
            "file_path": None,
            "origin": ORIGIN_GENERATED,
            "license": LICENSE_GENERATED,
            "license_url": None,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        for spec in seed_motion_specs()
        if spec["slug"] not in existing
    ]
    if rows:
        op.bulk_insert(table, rows)


def downgrade() -> None:
    op.drop_index("ix_previs_motion_assets_updated_at", table_name="previs_motion_assets")
    op.drop_index("ix_previs_motion_assets_created_at", table_name="previs_motion_assets")
    op.drop_index("ix_previs_motion_assets_is_active", table_name="previs_motion_assets")
    op.drop_index("ix_previs_motion_assets_category", table_name="previs_motion_assets")
    op.drop_index("ix_previs_motion_assets_skeleton", table_name="previs_motion_assets")
    op.drop_index("ix_previs_motion_assets_carrier", table_name="previs_motion_assets")
    op.drop_index("ux_previs_motion_assets_slug", table_name="previs_motion_assets")
    op.drop_table("previs_motion_assets")
