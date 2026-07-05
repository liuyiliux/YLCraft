"""Agent tools for YLCraft video generation workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.agent.registry import register_tool


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    return {"value": value}


@register_tool(
    name="list_video_backends",
    description="列出当前可用于 AI 视频生成的后端、模型和能力。",
    category="video",
    examples=["列出可用视频生成模型", "看看有没有图生视频后端"],
    input_schema_note="无参数；只读取当前已激活的视频生成后端。",
    output_schema_note="返回 success、default、backends；backends 含 name/model/available_models/capabilities。",
    risk_level="read",
    output_type="video_backend_list",
)
async def list_video_backends() -> dict[str, Any]:
    from app.api.v1.videos import list_backends

    response = await list_backends()
    return _to_plain_dict(response)


@register_tool(
    name="preview_video_generation_request",
    description="预览一次视频生成请求的标准化参数，不真正调用模型。",
    category="video",
    examples=["预览用首帧图生成 5 秒竖屏视频的请求", "检查这次视频生成会用哪个模型和分辨率"],
    input_schema_note="必须提供 prompt；provider/model/duration/resolution/aspect_ratio/start_image/generate_audio 可选。",
    output_schema_note="返回 normalized_request、start_image_exists、cost_warning；不会消耗模型额度。",
    risk_level="read",
    output_type="video_generation_request_preview",
)
async def preview_video_generation_request(
    prompt: str,
    provider: str = "",
    model: str = "",
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "9:16",
    start_image: str = "",
    generate_audio: bool = True,
    seed: int | None = None,
) -> dict[str, Any]:
    if not (prompt or "").strip():
        raise ValueError("prompt 不能为空")
    duration_value = max(1, min(int(duration or 5), 30))
    start_path = Path(start_image) if start_image else None
    return {
        "success": True,
        "normalized_request": {
            "prompt": prompt.strip(),
            "provider": provider or "",
            "model": model or "",
            "duration": duration_value,
            "resolution": resolution or "720p",
            "aspect_ratio": aspect_ratio or "9:16",
            "start_image": start_image or "",
            "generate_audio": bool(generate_audio),
            "seed": seed,
        },
        "start_image_exists": bool(start_path and start_path.exists()),
        "cost_warning": "这只是预览；真正生成视频请调用 generate_video_asset，风险等级为 costly，需要用户确认。",
    }


@register_tool(
    name="generate_video_asset",
    description="调用 YLCraft 视频生成后端生成视频，并在同步完成时尽量保存到素材库/Asset Hub。",
    category="video",
    examples=["根据分镜提示词生成 5 秒竖屏短视频", "用角色首帧图生成一段动作视频"],
    input_schema_note="必须提供 prompt；provider 建议来自 list_video_backends；model/duration/resolution/aspect_ratio/start_image/generate_audio 可选。",
    output_schema_note="同步完成返回 url/local_path/status；异步返回 task_id/status=pending，需要继续调用 poll_video_generation_task。",
    risk_level="costly",
    output_type="video_generation_result",
    cost_hint="会真实调用视频模型，通常比图片生成更贵；执行前应先预览并征得用户确认。",
)
async def generate_video_asset(
    prompt: str,
    provider: str = "",
    model: str = "",
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "9:16",
    start_image: str = "",
    generate_audio: bool = True,
    seed: int | None = None,
) -> dict[str, Any]:
    if not (prompt or "").strip():
        raise ValueError("prompt 不能为空")
    if start_image and not Path(start_image).exists():
        raise ValueError(f"首帧图片不存在: {start_image}")
    from app.api.v1.videos import VideoGenerateRequest, generate_video

    request = VideoGenerateRequest(
        prompt=prompt.strip(),
        provider=provider or None,
        model=model or None,
        duration=max(1, min(int(duration or 5), 30)),
        resolution=resolution or "720p",
        aspect_ratio=aspect_ratio or "9:16",
        start_image=start_image or None,
        generate_audio=bool(generate_audio),
        seed=seed,
    )
    response = await generate_video(request)
    return _to_plain_dict(response)


@register_tool(
    name="poll_video_generation_task",
    description="查询异步视频生成任务状态。",
    category="video",
    examples=["查询刚才视频生成任务是否完成", "轮询视频任务并返回本地路径"],
    input_schema_note="必须提供 generate_video_asset 返回的 task_id；provider 可选，一般不用传。",
    output_schema_note="返回 success/status/progress/progress_message/url/local_path/error。",
    risk_level="read",
    output_type="video_generation_task_status",
)
async def poll_video_generation_task(task_id: str, provider: str = "") -> dict[str, Any]:
    if not (task_id or "").strip():
        raise ValueError("task_id 不能为空")
    from app.api.v1.videos import get_task_status

    response = await get_task_status(task_id=task_id.strip(), provider=provider or None)
    return _to_plain_dict(response)
