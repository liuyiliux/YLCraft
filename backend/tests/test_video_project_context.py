from __future__ import annotations

from app.api.v1.videos import VideoGenerateRequest, _materialize_data_uri


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
