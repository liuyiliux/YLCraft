from __future__ import annotations

import json

import pytest

from app.api.v1.model3d_workspace import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    Model3DGenerateRequest,
    Model3DRigRequest,
    _backend_entry,
    _connector_capability,
    _poll_interval_seconds,
    _result_payload,
    _rigging_flags,
    _selected_model,
    _task_dict,
)
from app.db.models.task import Model3DGenerationTask
from app.services.model3d.workspace import Model3DConnectorBackend
from app.db.models.ai_connector import AIConnector


def test_image_to_3d_request_keeps_configured_model_and_source_lineage():
    request = Model3DGenerateRequest(
        provider="Configured 3D Provider", model="provider-image-to-3d-v1", prompt="character statue",
        source_asset_id="image-asset-1",
    )
    assert request.provider == "Configured 3D Provider"
    assert request.model == "provider-image-to-3d-v1"
    assert request.source_asset_id == "image-asset-1"


def test_image_to_3d_request_accepts_provider_options():
    request = Model3DGenerateRequest(
        provider="Tencent Hunyuan 3D Pro", model="3.0", prompt="character statue",
        options={"FaceCount": 1500000, "GenerateType": "Normal", "EnablePBR": True},
    )

    assert request.options["FaceCount"] == 1500000
    assert request.options["EnablePBR"] is True


def test_image_to_3d_api_rejects_model_not_declared_by_connector():
    connector = AIConnector(
        id="model3d", provider="custom", name="Configured 3D Provider",
        default_model="image-to-3d-v1", available_models='["image-to-3d-v1", "image-to-3d-v2"]',
    )

    assert _selected_model(connector, "image-to-3d-v2") == "image-to-3d-v2"
    with pytest.raises(ValueError, match="未在图生 3D 连接器"):
        _selected_model(connector, "unconfigured-model")


def test_image_to_3d_task_history_exposes_result_and_asset_state():
    task = Model3DGenerationTask(
        task_id="model3d-task-1", provider="Configured 3D Provider", model="provider-image-to-3d-v1",
        status="done", prompt="character statue", request_json='{"source_asset_id":"image-1"}',
        result_json='{"url":"https://example.test/model.glb"}', asset_id="model-asset-1",
        progress=100, created_at=1.0,
    )
    serialized = _task_dict(task)
    assert serialized["asset_id"] == "model-asset-1"
    assert serialized["request"]["source_asset_id"] == "image-1"
    assert serialized["result"]["url"].endswith("model.glb")


def test_model3d_poll_interval_falls_back_to_default():
    assert _poll_interval_seconds({"poll_interval": 30}) == 30
    assert _poll_interval_seconds({"poll_interval": "15"}) == 15
    assert _poll_interval_seconds({}) == DEFAULT_POLL_INTERVAL_SECONDS
    assert _poll_interval_seconds({"poll_interval": 0}) == DEFAULT_POLL_INTERVAL_SECONDS
    assert _poll_interval_seconds({"poll_interval": "not-a-number"}) == DEFAULT_POLL_INTERVAL_SECONDS


def test_model3d_backend_entry_reads_poll_interval_from_response_config():
    connector = AIConnector(
        id="tencent-3d", provider="tencent", name="Tencent 3D", default_model="3.0",
        available_models='["3.0", "3.1"]', response_config='{"poll_interval": 30}',
    )
    entry = _backend_entry(connector)
    assert entry["name"] == "Tencent 3D"
    assert entry["model"] == "3.0"
    assert entry["available_models"] == ["3.0", "3.1"]
    assert entry["poll_interval"] == 30


def test_image_to_3d_result_keeps_long_provider_id_outside_local_task_key():
    payload = _result_payload({"task_id": "provider-id", "status": "pending"}, "provider-id" * 40)
    assert payload["provider_task_id"].startswith("provider-id")
    assert payload["task_id"] == "provider-id"


def test_model3d_connector_diagnostics_redact_data_uri_and_credentials():
    connector = AIConnector(id="model3d", provider="custom", name="Custom 3D", api_key="secret-key")
    backend = Model3DConnectorBackend(connector)
    payload = backend._redact({"Authorization": "Bearer secret-key", "image": "data:image/png;base64,abc"})
    assert payload["Authorization"] == "***"
    assert payload["image"] == "<data-uri omitted>"


def test_model3d_connector_merges_configured_request_and_poll_headers():
    connector = AIConnector(
        id="model3d", provider="custom", name="Custom 3D", api_key="secret-key",
        response_config='{"request_headers":{"X-Client":"ylcraft"},"poll_headers":{"X-Poll":"1"}}',
    )
    backend = Model3DConnectorBackend(connector)
    assert backend._configured_headers("request_headers") == {
        "Content-Type": "application/json", "Authorization": "Bearer secret-key", "X-Client": "ylcraft",
    }
    assert backend._configured_headers("poll_headers")["X-Poll"] == "1"


def test_model3d_connector_supports_raw_api_key_auth_for_public_presets():
    connector = AIConnector(
        id="model3d", provider="tencent", name="Tencent 3D", api_key="sk-test",
        response_config='{"api_key_prefix":""}',
    )
    assert Model3DConnectorBackend(connector)._headers()["Authorization"] == "sk-test"


def test_model3d_connector_builds_tencent_tc3_headers():
    connector = AIConnector(
        id="tencent-3d", provider="tencent", name="Tencent 3D",
        api_key="AKIDEXAMPLE:secret", api_format="tencent_tc3",
    )
    headers = Model3DConnectorBackend(connector)._tencent_tc3_headers(
        "SubmitHunyuanTo3DProJob", {"Prompt": "cat"},
    )

    assert headers["Host"] == "ai3d.tencentcloudapi.com"
    assert headers["X-TC-Action"] == "SubmitHunyuanTo3DProJob"
    assert headers["X-TC-Version"] == "2025-05-13"
    assert headers["Authorization"].startswith("TC3-HMAC-SHA256 Credential=AKIDEXAMPLE/")


def test_model3d_connector_tc3_rejects_missing_secret_key_separator():
    connector = AIConnector(
        id="tencent-3d", provider="tencent", name="Tencent 3D",
        api_key="sk-not-a-cam-pair", api_format="tencent_tc3",
    )
    with pytest.raises(ValueError, match="SecretId:SecretKey"):
        Model3DConnectorBackend(connector)._tencent_tc3_headers("SubmitHunyuanTo3DProJob", {"Prompt": "cat"})


def test_model3d_connector_tc3_rejects_empty_secret_half():
    connector = AIConnector(
        id="tencent-3d", provider="tencent", name="Tencent 3D",
        api_key="AKIDEXAMPLE:", api_format="tencent_tc3",
    )
    with pytest.raises(ValueError, match="都不能为空"):
        Model3DConnectorBackend(connector)._tencent_tc3_headers("SubmitHunyuanTo3DProJob", {"Prompt": "cat"})


def test_model3d_connector_merges_options_into_tencent_request_body():
    connector = AIConnector(
        id="tencent-3d", provider="tencent", name="Tencent 3D",
        default_params='{"GenerateType":"Normal","FaceCount":500000}',
        request_template='{"Model":"{{ model }}","FaceCount":{{ FaceCount }},"GenerateType":"{{ GenerateType }}","Prompt":"{{ prompt }}"}',
    )
    backend = Model3DConnectorBackend(connector)
    body = backend._render({
        **backend.default_params, "FaceCount": 1500000, "model": "3.0",
        "prompt": "cat", "image_url": "", "image_data": "", "image_base64": "",
    })

    assert body["FaceCount"] == 1500000
    assert body["GenerateType"] == "Normal"


def test_model3d_tc3_action_resolves_defaults_and_overrides():
    backend = Model3DConnectorBackend(AIConnector(
        id="t", provider="tencent", name="T", api_key="AKID:x", api_format="tencent_tc3",
    ))
    assert backend._tc3_action("tencent_submit_action", "SubmitHunyuanTo3DProJob") == "SubmitHunyuanTo3DProJob"
    assert backend._tc3_action("tencent_query_action", "QueryHunyuanTo3DProJob") == "QueryHunyuanTo3DProJob"

    overridden = Model3DConnectorBackend(AIConnector(
        id="t2", provider="tencent", name="T2", api_key="AKID:x", api_format="tencent_tc3",
        response_config='{"tencent_query_action":"CustomQueryAction"}',
    ))
    assert overridden._tc3_action("tencent_query_action", "QueryHunyuanTo3DProJob") == "CustomQueryAction"


def test_model3d_tencent_template_omits_polygon_type_outside_lowpoly():
    connector = AIConnector(
        id="tencent-3d", provider="tencent", name="Tencent 3D",
        default_params='{"GenerateType":"Normal","FaceCount":500000}',
        request_template='{"GenerateType":"{{ GenerateType | default("Normal") }}"{% if (GenerateType | default("Normal")) == "LowPoly" %},"PolygonType":"{{ PolygonType | default("triangle") }}"{% endif %}}',
    )
    backend = Model3DConnectorBackend(connector)
    common = {"model": "3.0", "prompt": "cat", "image_url": "", "image_data": "", "image_base64": ""}
    body = backend._render({**backend.default_params, **common})
    assert "PolygonType" not in body
    assert body["GenerateType"] == "Normal"

    lowpoly = backend._render({**backend.default_params, "GenerateType": "LowPoly", "PolygonType": "quadrilateral", **common})
    assert lowpoly["PolygonType"] == "quadrilateral"


def test_model3d_connector_renders_image_or_prompt_request_template():
    connector = AIConnector(
        id="model3d", provider="tencent", name="Tencent 3D",
        request_template='{"Model":"{{ model }}"{% if image_url or image_data %},"ImageUrl":{"Url":"{{ image_url or image_data }}"}{% else %},"Prompt":"{{ prompt }}"{% endif %}}',
    )
    backend = Model3DConnectorBackend(connector)
    assert backend._render({"model": "3.0", "prompt": "cat", "image_url": "", "image_data": ""}) == {
        "Model": "3.0", "Prompt": "cat",
    }


def test_model3d_resolve_model_url_prefers_glb():
    backend = Model3DConnectorBackend(AIConnector(id="t", provider="tencent", name="T", api_key="x"))
    payload = {"Response": {"ResultFile3Ds": [
        {"Type": "OBJ", "Url": "https://example.test/out.zip"},
        {"Type": "GLB", "Url": "https://example.test/out.glb"},
    ]}}
    config = {
        "model_url_path": "$.Response.ResultFile3Ds[0].Url",
        "result_files_path": "$.Response.ResultFile3Ds",
        "prefer_model_type": "GLB",
    }
    assert backend._resolve_model_url(payload, config) == "https://example.test/out.glb"


def test_model3d_resolve_model_url_falls_back_without_preferred_type():
    backend = Model3DConnectorBackend(AIConnector(id="t", provider="tencent", name="T", api_key="x"))
    payload = {"Response": {"ResultFile3Ds": [
        {"Type": "OBJ", "Url": "https://example.test/out.zip"},
    ]}}
    config = {
        "model_url_path": "$.Response.ResultFile3Ds[0].Url",
        "result_files_path": "$.Response.ResultFile3Ds",
        "prefer_model_type": "GLB",
    }
    assert backend._resolve_model_url(payload, config) == "https://example.test/out.zip"


def test_model3d_parse_prefers_glb_when_configured():
    connector = AIConnector(
        id="t", provider="tencent", name="T", api_key="x",
        response_config=json.dumps({
            "status_path": "$.Response.Status",
            "model_url_path": "$.Response.ResultFile3Ds[0].Url",
            "result_files_path": "$.Response.ResultFile3Ds",
            "prefer_model_type": "GLB",
            "done_values": ["DONE"],
        }),
    )
    backend = Model3DConnectorBackend(connector)
    result = backend._parse({
        "Response": {
            "Status": "DONE",
            "ResultFile3Ds": [
                {"Type": "OBJ", "Url": "https://example.test/out.zip"},
                {"Type": "GLB", "Url": "https://example.test/out.glb"},
            ],
        },
    })
    assert result["status"] == "done"
    assert result["url"] == "https://example.test/out.glb"


def _rigging_connector() -> AIConnector:
    return AIConnector(
        id="tencent-rigging", provider="tencent", name="Tencent Hunyuan Auto Rigging",
        api_key="AKIDEXAMPLE:secret", api_format="tencent_tc3",
        default_model="hunyuan-auto-rigging",
        default_params='{"FileType":"GLB"}',
        request_template='{"File3D":{"Url":"{{ image_url }}","Type":"{{ FileType | default(\'GLB\') }}"}{% if MotionType %},"MotionType":{{ MotionType }}{% endif %}}',
        response_config=json.dumps({
            "capability": "rigging",
            "tencent_submit_action": "SubmitAutoRiggingJob",
            "tencent_query_action": "DescribeAutoRiggingJob",
            "task_id_path": "$.Response.JobId",
            "status_path": "$.Response.Status",
            "result_files_path": "$.Response.ResultFile3Ds",
            "prefer_model_type": "GLB",
            "done_values": ["DONE"],
            "failed_values": ["FAIL"],
        }),
    )


def test_rigging_request_motion_type_is_optional_and_bounded():
    skeleton_only = Model3DRigRequest(provider="Tencent Hunyuan Auto Rigging", source_asset_id="asset-1")
    assert skeleton_only.motion_type is None

    with_motion = Model3DRigRequest(provider="Tencent Hunyuan Auto Rigging", source_asset_id="asset-1", motion_type=1)
    assert with_motion.motion_type == 1

    with pytest.raises(ValueError):
        Model3DRigRequest(provider="Tencent Hunyuan Auto Rigging", source_asset_id="asset-1", motion_type=49)


def test_rigging_template_omits_motion_type_for_skeleton_only():
    backend = Model3DConnectorBackend(_rigging_connector())
    common = {"model": "hunyuan-auto-rigging", "prompt": "",
              "image_url": "https://example.test/model.glb", "image_data": "", "image_base64": ""}
    body = backend._render({**backend.default_params, **common})
    assert body == {"File3D": {"Url": "https://example.test/model.glb", "Type": "GLB"}}

    rigged = backend._render({**backend.default_params, "MotionType": 12, **common})
    assert rigged["MotionType"] == 12
    assert rigged["File3D"]["Type"] == "GLB"


def test_rigging_connector_declares_describe_query_action_not_query_prefix():
    backend = Model3DConnectorBackend(_rigging_connector())
    assert backend._tc3_action("tencent_submit_action", "SubmitHunyuanTo3DProJob") == "SubmitAutoRiggingJob"
    assert backend._tc3_action("tencent_query_action", "QueryHunyuanTo3DProJob") == "DescribeAutoRiggingJob"


def test_rigging_parse_maps_wait_run_done_fail_statuses():
    backend = Model3DConnectorBackend(_rigging_connector())
    for raw_status, expected in (("WAIT", "pending"), ("RUN", "pending"), ("DONE", "done"), ("FAIL", "error")):
        payload = {"Response": {"Status": raw_status, "ResultFile3Ds": []}}
        assert backend._parse(payload, fallback_task_id="job-1")["status"] == expected


def test_connector_capability_defaults_to_generation_and_reads_rigging():
    generation = AIConnector(id="g", provider="tencent", name="G")
    assert _connector_capability(generation) == "generation"
    assert _connector_capability(_rigging_connector()) == "rigging"

    entry = _backend_entry(_rigging_connector())
    assert entry["capability"] == "rigging"
    assert _backend_entry(generation)["capability"] == "generation"


def test_rigging_flags_derive_tags_from_extracted_metadata():
    flags, tags = _rigging_flags({"bones": 1, "animations": ["walk"]})
    assert flags == {"has_bones": True, "has_animations": True}
    assert tags == ["rigged", "animated"]

    flags, tags = _rigging_flags({"vertices": 100})
    assert flags == {"has_bones": False, "has_animations": False}
    assert tags == []


def test_rigging_task_history_entry_exposes_kind():
    task = Model3DGenerationTask(
        task_id="model3d-rig-1", kind="rigging", provider="Tencent Hunyuan Auto Rigging",
        model="hunyuan-auto-rigging", status="pending", prompt="绑骨蒙皮（仅骨骼）",
        request_json='{"source_asset_id":"asset-1","motion_type":null}',
        result_json='{"provider_task_id":"job-1"}', created_at=1.0,
    )
    serialized = _task_dict(task)
    assert serialized["kind"] == "rigging"
    assert serialized["request"]["source_asset_id"] == "asset-1"
