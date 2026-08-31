"""add character voice fields

speech_json 管"怎么说"（口头禅/句式/语速/方言），
voice_json + voice_asset_id 管"用什么声音说"（对接 TTS 与音频素材）。
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "030_add_character_voice_fields"
down_revision = "029_add_platform_event_ref_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column(
            "voice_json",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "characters",
        sa.Column(
            "voice_asset_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("characters", "voice_asset_id")
    op.drop_column("characters", "voice_json")
