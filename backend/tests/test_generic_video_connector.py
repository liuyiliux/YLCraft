from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path

import pytest
import httpx

from app.db.models.ai_connector import AIConnector
from app.services.ai.backends.video.generic import GenericVideoBackend
from app.services.ai.types import VideoCapability, VideoGenerationRequest


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
    assert backend._dimensions("1080p", "4:3") == (1440, 1080)
    assert backend._frame_count(5, 24) == 121


def test_generic_video_connector_exposes_declared_capability_limits():
    connector = AIConnector(
        id="limited-video", provider="custom", name="Limited Video", api_key="test-key",
        provider_type="video", support_reference_image=True,
        default_params='{"video_capabilities":{"text_to_video":false,"image_to_video":true,"seed_control":true,"generate_audio":false,"resolutions":["720p"],"aspect_ratios":["9:16"],"durations":[5],"max_duration":5}}',
    )
    backend = GenericVideoBackend(connector)

    assert backend.enforce_video_capabilities is True
    assert {capability.value for capability in backend.capabilities} == {"image_to_video", "seed_control"}
    assert backend.video_capabilities.first_frame is True
    assert backend.video_capabilities.supported_resolutions == ["720p"]
    assert backend.video_capabilities.supported_aspect_ratios == ["9:16"]
    assert backend.video_capabilities.supported_durations == [5]
    assert backend.video_capabilities.max_duration == 5


def test_legacy_generic_video_connector_remains_permissive_without_constraints():
    backend = GenericVideoBackend(AIConnector(id="legacy-video", provider="custom", name="Legacy Video"))
    assert backend.enforce_video_capabilities is False


def test_legacy_template_with_start_image_remains_image_to_video_capable():
    backend = GenericVideoBackend(AIConnector(
        id="legacy-i2v", provider="custom", name="Legacy I2V",
        request_template='{"input":{"image":"{{ start_image }}"}}',
    ))
    assert VideoCapability.IMAGE_TO_VIDEO in backend.capabilities


def test_generic_video_unwraps_json_string_poll_response():
    connector = AIConnector(
        id="agnes-video", provider="agnes", name="Agnes", api_key="test-key",
        provider_type="video", base_url="https://api.agnes-ai.cn",
        response_config='{"status_path":"$.status","video_url_path":"$.metadata.url","done_values":["completed"]}',
    )
    backend = GenericVideoBackend(connector)
    payload = '{"status":"completed","metadata":{"url":"https://example.test/video.mp4"}}'
    result = backend._status(payload, "video-1")
    assert result.status == "done"
    assert result.url.endswith("video.mp4")


def test_generic_video_accepts_agnes_top_level_url_response():
    connector = AIConnector(
        id="agnes-video", provider="agnes", name="Agnes", api_key="test-key",
        provider_type="video", base_url="https://api.agnes-ai.cn",
        response_config='{"status_path":"$.status","video_url_path":"$.metadata.url","done_values":["completed"]}',
    )
    backend = GenericVideoBackend(connector)
    payload = '{"status":"completed","internal_status":"completed","url":"https://example.test/agnes.mp4"}'
    result = backend._status(payload, "video-1")
    assert result.status == "done"
    assert result.url.endswith("agnes.mp4")


def test_generic_video_parses_agnes_epoch_completion_time():
    backend = GenericVideoBackend(AIConnector(
        id="agnes-video", provider="agnes", name="Agnes", api_key="test-key",
        provider_type="video", response_config='{"status_path":"$.internal_status"}',
    ))

    result = backend._status({
        "internal_status": "completed",
        "completed_at": 1790152374,
        "url": "https://example.test/agnes.mp4",
    }, "video-1")

    assert result.status == "done"
    assert result.completed_at == 1790152374.0


def test_generic_video_parses_wan_output_end_time():
    backend = GenericVideoBackend(AIConnector(
        id="wan-video", provider="dashscope", name="Wan", api_key="test-key",
        provider_type="video",
        response_config='{"status_path":"$.output.task_status","video_url_path":"$.output.video_url","done_values":["SUCCEEDED"]}',
    ))

    result = backend._status({
        "output": {
            "task_status": "SUCCEEDED",
            "video_url": "https://example.test/wan.mp4",
            "end_time": "2026-09-23T08:32:54Z",
        }
    }, "video-1")

    assert result.status == "done"
    assert result.completed_at == datetime.fromisoformat("2026-09-23T08:32:54+00:00").timestamp()


def test_generic_video_completion_time_accepts_epoch_millis_and_naive_iso():
    backend = GenericVideoBackend(AIConnector(id="video", provider="custom", name="Video"))

    assert backend._completion_timestamp(1790152374000) == 1790152374.0
    naive = "2026-09-23T16:32:54"
    assert backend._completion_timestamp(naive) == datetime.fromisoformat(naive).astimezone().timestamp()
    assert backend._completion_timestamp("not-a-time") is None


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
    # Resolve the source file relative to this test file so the assertion
    # works regardless of the pytest working directory (repo root or backend/).
    source_path = Path(__file__).resolve().parents[1] / (
        GenericVideoBackend.__module__.replace(".", "/") + ".py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
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


def _shipped_agnes_video_backend() -> GenericVideoBackend:
    preset_path = Path(__file__).resolve().parents[2] / "examples" / "ai-connectors" / "agnes-video-v2.json"
    spec = json.loads(preset_path.read_text(encoding="utf-8"))["connectors"][0]
    return GenericVideoBackend(AIConnector(
        id=spec["id"], provider=spec["provider"], name=spec["name"], api_key="test-key",
        provider_type=spec["provider_type"], base_url=spec["base_url"],
        api_endpoint=spec["api_endpoint"], default_model=spec["default_model"],
        request_template=spec["request_template"],
        response_config=json.dumps(spec["response_config"]),
        default_params=json.dumps(spec["default_params"]),
    ))


def test_shipped_agnes_video_preset_renders_multi_line_prompt():
    """Regression: a multi-line prompt used to break json.loads in _generate.

    2026-10-31 复现：`json.decoder.JSONDecodeError: Invalid control character
    at: line 1 column 147` —— 模板里 `"prompt":"{{ prompt }}"` 直接内插原文，
    提示词里的换行让渲染结果不是合法 JSON，请求根本没发出去。
    """
    backend = _shipped_agnes_video_backend()
    prompt = '镜头缓慢推近\n特写：「雨夜里的霓虹」\t第二段\\结尾'
    body = backend._render_request_body(
        VideoGenerationRequest(prompt=prompt, duration=5, resolution="720p", aspect_ratio="9:16"),
        "",
    )

    assert body["prompt"] == prompt  # 转义后仍是原始文本，供应商解码后拿到换行和引号
    assert body["model"] == "agnes-video-v2.0"
    assert (body["width"], body["height"]) == (405, 720)
    assert body["num_frames"] == 121


def test_generic_video_template_can_use_prompt_json_placeholder():
    backend = GenericVideoBackend(AIConnector(
        id="json-video", provider="custom", name="JSON Video",
        request_template='{"model":"{{ model }}","prompt":{{ prompt_json }},"size":"{{ size }}"}',
    ))
    prompt = '多行\n提示词 "带引号"'
    body = backend._render_request_body(VideoGenerationRequest(prompt=prompt), "")

    assert body["prompt"] == prompt
    assert body["size"] == "405x720"


def test_generic_video_unrepairable_template_reports_actionable_error():
    backend = GenericVideoBackend(AIConnector(
        id="bad-video", provider="custom", name="Bad Video",
        request_template='{"model":"{{ model }}","prompt":}',
    ))

    with pytest.raises(ValueError) as excinfo:
        backend._render_request_body(VideoGenerationRequest(prompt="hello"), "")

    message = str(excinfo.value)
    assert "request_template" in message
    assert "prompt_json" in message
    assert "Bad Video" in message


async def test_generic_video_submits_multi_line_prompt_as_valid_json(monkeypatch):
    """端到端：多行提示词真的发到供应商请求体里，而不是卡在 json.loads。"""
    captured: dict = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            return httpx.Response(
                200,
                json={"video_id": "vid-1", "status": "queued"},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("app.services.ai.backends.video.generic.httpx.AsyncClient", FakeAsyncClient)
    backend = _shipped_agnes_video_backend()
    prompt = "第一幕：雨夜\n第二幕：霓虹灯牌「特写」\t第三幕：收尾"

    result = await backend.generate(
        VideoGenerationRequest(prompt=prompt, duration=5, resolution="720p", aspect_ratio="9:16")
    )

    assert result.success is True
    assert result.task_id == "vid-1"
    assert captured["url"].endswith("/v1/videos")
    assert captured["json"]["prompt"] == prompt
    assert "\n" in captured["json"]["prompt"]


async def test_failed_video_generation_records_the_requested_model():
    """回归：失败台账曾写成连接器默认模型，看不出真正发出去的是已下线的 2.0。"""

    class ExplodingBackend(GenericVideoBackend):
        async def _generate(self, req):  # noqa: ANN001 - test stub
            raise RuntimeError("当前分组不支持模型 agnes-video-v2.0，请更换模型后重试")

    backend = ExplodingBackend(AIConnector(
        id="agnes", provider="agnes", name="agnes-video-2.5-flash",
        api_key="test-key", default_model="agnes-video-2.5-flash",
    ))

    result = await backend.generate(VideoGenerationRequest(prompt="x", model="agnes-video-v2.0"))

    assert result.success is False
    assert result.model == "agnes-video-v2.0"
    assert "agnes-video-v2.0" in result.error


def _scripted_backend(monkeypatch, script, calls, sleeps):
    """Shipped Agnes backend whose submit responses follow ``script`` (status, json)."""
    queue = list(script)

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, headers=None, json=None):
            calls.append(json)
            status, body = queue.pop(0) if len(queue) > 1 else queue[0]
            return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("app.services.ai.backends.video.generic.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.services.ai.backends.video.generic.asyncio.sleep", fake_sleep)
    return _shipped_agnes_video_backend()


async def test_generic_video_retries_when_provider_queue_is_full(monkeypatch):
    """2026-10-31 实测：Agnes 返回 503 {"code":"video_queue_full"}，应短暂重试而不是直接失败。"""
    calls: list = []
    sleeps: list = []
    backend = _scripted_backend(monkeypatch, [
        (503, {"code": "video_queue_full", "message": "视频队列已满，请稍后重试"}),
        (200, {"video_id": "vid-9", "status": "queued"}),
    ], calls, sleeps)

    result = await backend.generate(
        VideoGenerationRequest(prompt="雨夜街道", duration=5, resolution="720p", aspect_ratio="9:16")
    )

    assert result.success is True
    assert result.task_id == "vid-9"
    assert len(calls) == 2
    assert sleeps == [3.0]
    assert result.diagnostics["submit_attempt"] == 2


async def test_generic_video_busy_provider_reports_actionable_error(monkeypatch):
    """重试仍无容量时，用户要看到「队列已满、稍后重试」，而不是裸 HTTPStatusError。"""
    calls: list = []
    sleeps: list = []
    backend = _scripted_backend(monkeypatch, [
        (503, {"code": "video_queue_full", "message": "视频队列已满，请稍后重试"}),
    ], calls, sleeps)

    result = await backend.generate(
        VideoGenerationRequest(prompt="雨夜街道", duration=5, resolution="720p", aspect_ratio="9:16")
    )

    assert result.success is False
    assert len(calls) == 3
    assert sleeps == [3.0, 8.0]
    assert "繁忙" in result.error
    assert "队列已满" in result.error
    assert "不是连接器配置问题" in result.error
    assert result.diagnostics["http_status"] == 503
    assert [item["delay_seconds"] for item in result.diagnostics["retries"]] == [3.0, 8.0]


async def test_generic_video_surfaces_provider_rejection_reason(monkeypatch):
    """模型/参数被拒时透出供应商原始说明，且不做无意义的重试。"""
    calls: list = []
    sleeps: list = []
    backend = _scripted_backend(monkeypatch, [
        (404, {"error": {"code": "model_not_found", "message": "当前分组不支持模型 agnes-video-v2.0，请更换模型后重试"}}),
    ], calls, sleeps)

    result = await backend.generate(VideoGenerationRequest(prompt="x", model="agnes-video-v2.0"))

    assert result.success is False
    assert "model_not_found" in result.error
    assert "当前分组不支持模型 agnes-video-v2.0" in result.error
    assert len(calls) == 1
    assert sleeps == []
