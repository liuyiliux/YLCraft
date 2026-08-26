"""remove legacy sampling defaults from Asset Hub metadata

Revision ID: 023_remove_legacy_asset_sampling_metadata
Revises: 022_seed_platform_prompt_templates
"""

from alembic import op


revision = "023_remove_legacy_asset_sampling_metadata"
down_revision = "022_seed_platform_prompt_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove UI-only legacy defaults that were never provider-returned facts."""
    op.execute(
        """
        UPDATE asset_nodes
        SET metadata_json = jsonb_set(
            metadata_json,
            '{ai_params}',
            COALESCE(metadata_json->'ai_params', '{}'::jsonb)
                - 'steps'
                - 'sampler'
                - 'sampling_params_source',
            true
        )
        WHERE metadata_json ? 'ai_params'
          AND (
              metadata_json->'ai_params' ? 'steps'
              OR metadata_json->'ai_params' ? 'sampler'
              OR metadata_json->'ai_params' ? 'sampling_params_source'
          )
        """
    )


def downgrade() -> None:
    # Deleted values were defaults rather than authoritative generation data.
    pass
