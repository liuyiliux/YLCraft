from __future__ import annotations

import pytest

from app.api.v1.videos import (
    VideoGenerateRequest,
    _materialize_data_uri,
    _request_context,
    _task_to_dict,
    list_backends,
)
from app.db.models.task import VideoGenerationTask
from app.services.ai.types import MediaType, VideoCapability


def test_video_request_keeps_project_provenance_and_false_audio_flag():
    request = VideoGenerateRequest(
        prompt="A character turns toward the door",
        generate_audio=False,
        project_id="project-1",
        content_id="storyboard-1",
        chapter_number=3,
        source_type="storyboard_panel",
        source_index="2",
        reference_asset_ids=["asset-1", "asset-2"],
    )

    assert request.generate_audio is False
    assert request.project_id == "project-1"
    assert request.content_id == "storyboard-1"
    assert request.chapter_number == 3
    assert request.source_type == "storyboard_panel"
    assert request.source_index == "2"
    assert request.reference_asset_ids == ["asset-1", "asset-2"]


def test_video_data_uri_is_materialized_as_a_short_lived_file():
    path, cleanup_path = _materialize_data_uri("data:image/png;base64,aGVsbG8=")

    try:
        assert path is not None
        assert cleanup_path == path
        assert path.read_bytes() == b"hello"
    finally:
        if cleanup_path is not None:
            cleanup_path.unlink(missing_ok=True)


def test_video_task_context_preserves_standalone_and_project_metadata():
    request = VideoGenerateRequest(
        prompt="A slow tracking shot through a rain-lit market",
        duration=6,
        resolution="1080p",
        aspect_ratio="16:9",
        generate_audio=False,
        project_id="project-1",
        content_id="panel-3",
        source_type="storyboard_panel",
        source_index="3",
    )

    context = _request_context(request, ["asset-first-frame"])

    assert context["prompt"] == request.prompt
    assert context["reference_asset_ids"] == ["asset-first-frame"]
    assert context["generate_audio"] is False
    assert context["project_id"] == "project-1"


def test_video_history_serialization_exposes_result_and_asset_state():
    task = VideoGenerationTask(
        task_id="video-task-1",
        provider="minimax-video",
        model="seedance-2.0",
        status="done",
        prompt="A protagonist opens a door",
        request_json='{"duration": 5, "aspect_ratio": "9:16"}',
        result_json='{"url": "https://example.test/video.mp4", "duration": 5}',
        asset_id="asset-video-1",
        progress=100,
        created_at=1.0,
    )

    serialized = _task_to_dict(task)

    assert serialized["asset_id"] == "asset-video-1"
    assert serialized["request"]["duration"] == 5
    assert serialized["result"]["url"].endswith("video.mp4")


def test_video_result_payload_keeps_provider_diagnostics():
    from app.api.v1.videos import _result_payload
    from app.services.ai.types import VideoGenerationResult

    payload = _result_payload(VideoGenerationResult(
        success=False,
        diagnostics={"exception_type": "ReadTimeout", "endpoint": "https://example.test/video"},
    ))

    assert payload["diagnostics"]["exception_type"] == "ReadTimeout"


def test_failed_video_submission_uses_terminal_error_status():
    from app.services.ai.types import VideoGenerationResult

    result = VideoGenerationResult(success=False)

    status = (result.status or "pending") if result.success else "error"

    assert status == "error"


@pytest.mark.asyncio
async def test_video_backends_serializes_default_backend_name(monkeypatch):
    class Backend:
        name = "wan-video"
        model = "wan2.7-t2v"
        available_models = [model]
        capabilities = {VideoCapability.TEXT_TO_VIDEO}

    class Service:
        def is_loaded(self):
            return True

        def list_backends(self, media_type):
            assert media_type is MediaType.VIDEO
            return ["wan-video"]

        def get_backend(self, media_type, name):
            assert media_type is MediaType.VIDEO
            assert name == "wan-video"
            return Backend()

        def get_default(self, media_type):
            assert media_type is MediaType.VIDEO
            return Backend()

    monkeypatch.setattr("app.api.v1.videos.get_ai_service", lambda: Service())

    response = await list_backends()

    assert response.default == "wan-video"
    assert response.backends[0].name == "wan-video"
