"""allow standalone previs scenes (binding fields nullable)

Revision ID: 018_allow_standalone_previs_scenes
Revises: 017_add_platform_event_logs
"""

from alembic import op
import sqlalchemy as sa


revision = "018_allow_standalone_previs_scenes"
down_revision = "017_add_platform_event_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 独立预演场景：project_id / storyboard_content_id / panel_number 允许全空。
    with op.batch_alter_table("previs_scene_documents") as batch:
        batch.alter_column("project_id", existing_type=sa.String(length=80), nullable=True)
        batch.alter_column("storyboard_content_id", existing_type=sa.String(length=80), nullable=True)
        batch.alter_column("panel_number", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("previs_scene_documents") as batch:
        batch.alter_column("project_id", existing_type=sa.String(length=80), nullable=False)
        batch.alter_column("storyboard_content_id", existing_type=sa.String(length=80), nullable=False)
        batch.alter_column("panel_number", existing_type=sa.Integer(), nullable=False)
