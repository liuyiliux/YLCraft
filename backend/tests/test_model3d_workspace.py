from __future__ import annotations

from app.api.v1.model3d_workspace import Model3DGenerateRequest, _task_dict
from app.db.models.task import Model3DGenerationTask


def test_image_to_3d_request_keeps_configured_model_and_source_lineage():
    request = Model3DGenerateRequest(
        provider="Hunyuan 3D", model="Hunyuan3D-2", prompt="character statue",
        source_asset_id="image-asset-1",
    )
    assert request.provider == "Hunyuan 3D"
    assert request.model == "Hunyuan3D-2"
    assert request.source_asset_id == "image-asset-1"


def test_image_to_3d_task_history_exposes_result_and_asset_state():
    task = Model3DGenerationTask(
        task_id="model3d-task-1", provider="Hunyuan 3D", model="Hunyuan3D-2",
        status="done", prompt="character statue", request_json='{"source_asset_id":"image-1"}',
        result_json='{"url":"https://example.test/model.glb"}', asset_id="model-asset-1",
        progress=100, created_at=1.0,
    )
    serialized = _task_dict(task)
    assert serialized["asset_id"] == "model-asset-1"
    assert serialized["request"]["source_asset_id"] == "image-1"
    assert serialized["result"]["url"].endswith("model.glb")
