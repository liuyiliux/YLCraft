from __future__ import annotations

from app.api.v1.images import ImageGenerateRequest, _asset_generation_params, _image_log_request
from app.api.v1.videos import VideoGenerateRequest, _request_context, _video_log_request
from app.services.ai.visual_planning import build_visual_planning_summary


def test_visual_planning_summary_is_auditable_and_bounded():
    summary = build_visual_planning_summary(
        "image",
        "  a very long prompt " * 500,
        visual_intent="建立主角第一次看见古堡的恐怖感",
        reference_asset_ids=["asset-1", "asset-1", "asset-2"],
        production_plan_id="plan-1",
        production_node_id="panel-3",
        extra={"hidden_reasoning": "不要保存", "shot": {"camera": "slow push in"}},
    )

    assert summary["kind"] == "image"
    assert summary["intent"].startswith("建立主角")
    assert len(summary["prompt"]) <= 4000
    assert summary["reference_assets"] == ["asset-1", "asset-2"]
    assert summary["shot"] == {"camera": "slow push in"}
    assert "hidden_reasoning" not in summary


def test_image_request_and_event_log_keep_visual_plan_context():
    request = ImageGenerateRequest(
        prompt="雨夜古堡",
        project_id="project-1",
        production_plan_id="plan-1",
        production_node_id="node-1",
        planning_summary={"intent": "建立恐怖感", "expected_output": "storyboard_frame"},
    )
    logged = _image_log_request(request)
    assert logged["planning_summary"]["intent"] == "建立恐怖感"
    assert logged["production_node_id"] == "node-1"


def test_asset_generation_metadata_omits_legacy_sampling_defaults():
    assert _asset_generation_params(ImageGenerateRequest(prompt="雨夜古堡")) == {}

    explicit = ImageGenerateRequest(prompt="雨夜古堡", steps=28, sampler="dpmpp_2m")
    assert _asset_generation_params(explicit) == {}


def test_video_request_context_and_event_log_keep_visual_plan_context():
    request = VideoGenerateRequest(
        prompt="海边奔跑",
        project_id="project-1",
        production_plan_id="plan-1",
        production_node_id="shot-2",
        planning_summary={"intent": "展示动作连续性"},
    )
    context = _request_context(request, ["asset-first-frame"])
    logged = _video_log_request(request)
    assert context["planning_summary"]["intent"] == "展示动作连续性"
    assert logged["production_plan_id"] == "plan-1"
    assert context["reference_asset_ids"] == ["asset-first-frame"]
