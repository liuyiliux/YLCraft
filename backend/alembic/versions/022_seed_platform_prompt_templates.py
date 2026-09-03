"""seed built-in platform and prompt templates once through Alembic

Revision ID: 022_seed_platform_prompt_templates
Revises: 021_add_external_api_key_quota
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.services.ai.platform_templates_seed import (
    CREATIVE_PROJECT_TEMPLATE_SEEDS,
    PLATFORM_TEMPLATE_SEEDS,
    VIDEO_PROMPT_TEMPLATE_SEEDS,
)


revision = "022_seed_platform_prompt_templates"
down_revision = "021_add_external_api_key_quota"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Insert only missing built-ins; database values remain the source of truth."""
    bind = op.get_bind()
    # 离线模式（`alembic upgrade --sql`）没有真实连接：SELECT 会返回 None，
    # 且 SQLAlchemy 无法为 JSONB 字面量生成渲染（非 ASCII 直接 CompileError）。
    # 因此离线只输出 DDL，种子数据交给运行时的 seed_platform_templates() 保证；
    # 在线升级行为不变（按 platform 查重后插入）。
    if getattr(op.get_context(), "as_sql", False):
        return
    templates = sa.table(
        "platform_templates",
        sa.column("id", sa.UUID()),
        sa.column("platform", sa.String()),
        sa.column("name", sa.String()),
        sa.column("template_scope", sa.String()),
        sa.column("template_stage", sa.String()),
        sa.column("description", sa.String()),
        sa.column("system_template", sa.Text()),
        sa.column("outline_template", sa.String()),
        sa.column("image_template", sa.String()),
        sa.column("page_structure", postgresql.JSONB()),
        sa.column("variables", postgresql.JSONB()),
        sa.column("video_template", sa.String()),
        sa.column("default_size", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )

    for raw in [*PLATFORM_TEMPLATE_SEEDS, *VIDEO_PROMPT_TEMPLATE_SEEDS, *CREATIVE_PROJECT_TEMPLATE_SEEDS]:
        if bind.execute(
            sa.text("SELECT 1 FROM platform_templates WHERE platform = :platform"),
            {"platform": raw["platform"]},
        ).first():
            continue
        seed = dict(raw)
        # Keep defaults in sync with seed_platform_templates() at runtime.
        seed.setdefault("template_scope", "image_platform")
        seed.setdefault("template_stage", "platform")
        seed.setdefault("description", None)
        seed.setdefault("system_template", "")
        seed.setdefault("variables", {})
        seed["id"] = uuid.UUID(str(seed["id"]))
        bind.execute(templates.insert().values(**seed))


def downgrade() -> None:
    # Seed data may have been edited by a user after upgrade, so downgrading
    # schema revisions must not delete those database-owned templates.
    pass
