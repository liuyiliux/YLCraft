from __future__ import annotations

from app.api.v1.live2d import Live2DModelFromAssetRequest, model_to_response
from app.db.models.live2d import Live2DModel


def test_live2d_asset_request_keeps_asset_source_and_style():
    request = Live2DModelFromAssetRequest(
        asset_id="image-asset-1", name="Hero", style_mode="anime",
    )
    assert request.asset_id == "image-asset-1"
    assert request.style_mode == "anime"


def test_live2d_response_reads_extra_data_not_legacy_metadata_field():
    model = Live2DModel(
        id="live2d-1", name="Hero", extra_data='{"source_asset_id":"image-asset-1"}',
    )
    response = model_to_response(model)
    assert response.metadata["source_asset_id"] == "image-asset-1"


def test_live2d_export_metadata_is_explicitly_not_a_cubism_moc3():
    model = Live2DModel(
        id="live2d-2", name="Hero",
        extra_data='{"export":{"artifact_type":"ylcraft_live2d_config_package","cubism_moc3_included":false}}',
    )
    response = model_to_response(model)
    assert response.metadata["export"]["artifact_type"] == "ylcraft_live2d_config_package"
    assert response.metadata["export"]["cubism_moc3_included"] is False
