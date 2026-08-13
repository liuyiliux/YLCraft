from __future__ import annotations

import ast

from app.db.models.ai_connector import AIConnector
from app.services.ai.backends.video.generic import GenericVideoBackend
from app.services.ai.types import VideoGenerationRequest


def test_generic_video_connector_parses_dashscope_async_contract():
    connector = AIConnector(
        id="wan-video", provider="dashscope", name="阿里百炼 Wan 2.7 文生视频",
        api_key="test-key", provider_type="video", base_url="https://dashscope.aliyuncs.com",
        api_endpoint="/api/v1/services/aigc/video-generation/video-synthesis",
        default_model="wan2.7-t2v-2026-06-12",
        response_config='{"task_id_path":"$.output.task_id","status_path":"$.output.task_status","video_url_path":"$.output.video_url","done_values":["SUCCEEDED"]}',
    )
    backend = GenericVideoBackend(connector)

    assert backend._find({"output": {"task_id": "task-1"}}, "$.output.task_id") == "task-1"
    result = backend._status({"output": {"task_status": "SUCCEEDED", "video_url": "https://example.test/out.mp4"}}, "task-1")
    assert result.status == "done"
    assert result.url.endswith("out.mp4")
    assert backend._size("720p", "16:9") == "1280x720"
    assert backend._size("720p", "9:16") == "405x720"
    assert backend._size("720p", "16:9", "*") == "1280*720"


def test_generic_video_diagnostics_redact_credentials_and_large_media():
    connector = AIConnector(id="video", provider="custom", name="Video", api_key="secret")
    backend = GenericVideoBackend(connector)

    data = backend._redact({
        "Authorization": "Bearer secret",
        "api_key": "secret",
        "image": "data:image/png;base64,abc",
        "prompt": "x" * 2100,
    })

    assert data["Authorization"] == "***"
    assert data["api_key"] == "***"
    assert data["image"] == "<data-uri omitted>"
    assert data["prompt"].endswith("...(truncated)")


def test_generic_video_requests_bypass_environment_proxy():
    tree = ast.parse(GenericVideoBackend.__module__ and open(GenericVideoBackend.__module__.replace(".", "/") + ".py", encoding="utf-8").read())
    clients = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "AsyncClient"]
    assert len(clients) == 2
    assert all(any(keyword.arg == "trust_env" and keyword.value.value is False for keyword in node.keywords) for node in clients)


def test_generic_video_template_exposes_start_image(tmp_path):
    image = tmp_path / "first.png"
    image.write_bytes(b"png-bytes")
    connector = AIConnector(
        id="wan-i2v", provider="dashscope", name="Wan I2V", api_key="secret",
        provider_type="video", base_url="https://example.test", default_model="wan2.7-i2v",
        request_template='{"model":"{{ model }}","input":{"prompt":"{{ prompt }}","img_url":"{{ start_image }}"}}',
    )
    backend = GenericVideoBackend(connector)

    rendered = backend._size("720p", "16:9")
    assert rendered == "1280x720"
    request = VideoGenerationRequest(prompt="motion", start_image=image)
    # The template variables are exercised through the same renderer contract.
    import json
    from jinja2 import Template
    body = json.loads(Template(connector.request_template).render(
        model=request.model or backend.model,
        prompt=request.prompt,
        start_image="data:image/png;base64,cG5nLWJ5dGVz",
    ))
    assert body["input"]["img_url"].startswith("data:image/png;base64,")


def test_dashscope_wan27_i2v_uses_new_media_contract(tmp_path):
    connector = AIConnector(
        id="wan-i2v", provider="dashscope", name="Wan I2V", api_key="secret",
        provider_type="video", base_url="https://dashscope.aliyuncs.com",
        default_model="wan2.7-i2v-2026-04-25",
        request_template='{"model":"{{ model }}","input":{"prompt":"{{ prompt }}","media":[{"type":"first_frame","url":"{{ start_image }}"}]},"parameters":{"resolution":"720P","duration":{{ duration }},"prompt_extend":true}}',
    )
    request = VideoGenerationRequest(prompt="motion", start_image=tmp_path / "first.png")
    request.start_image.write_bytes(b"png-bytes")
    import json
    from jinja2 import Template
    body = json.loads(Template(connector.request_template).render(
        model=request.model or connector.default_model,
        prompt=request.prompt,
        duration=request.duration,
        start_image="data:image/png;base64,cG5nLWJ5dGVz",
    ))
    assert body["model"] == "wan2.7-i2v-2026-04-25"
    assert body["input"]["media"] == [{"type": "first_frame", "url": "data:image/png;base64,cG5nLWJ5dGVz"}]
    assert body["parameters"]["resolution"] == "720P"
