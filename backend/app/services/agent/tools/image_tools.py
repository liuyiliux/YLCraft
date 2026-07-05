"""Agent tools for YLCraft image generation workflows."""

from __future__ import annotations

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


def _compact_reference_images(reference_images: list[str] | None) -> list[str]:
    items = reference_images or []
    compacted: list[str] = []
    for item in items[:8]:
        text = str(item or "")
        if text.startswith("data:image") or len(text) > 180:
            compacted.append(f"{text[:80]}...(truncated, len={len(text)})")
        else:
            compacted.append(text)
    return compacted


@register_tool(
    name="list_image_backends",
    description="列出当前可用于 AI 生图的后端、模型、尺寸和参考图能力。",
    category="image",
    examples=["列出可用生图模型", "看看哪个图片后端支持参考图"],
    input_schema_note="无参数；只读取当前已激活的 image 类型模型配置。",
    output_schema_note="返回 success、default、backends；backends 含 name/provider/model/available_models/supported_sizes/support_reference_image。",
    risk_level="read",
    output_type="image_backend_list",
)
async def list_image_backends() -> dict[str, Any]:
    from app.api.v1.images import list_backends

    response = await list_backends()
    return _to_plain_dict(response)


@register_tool(
    name="preview_image_generation_request",
    description="预览一次生图请求的标准化参数，不真正调用模型，适合让智能体先向用户确认花费型操作。",
    category="image",
    examples=["预览用魔塔生成角色九宫格的请求", "检查这次分镜生图会带哪些参考图"],
    input_schema_note=(
        "必须提供 prompt；provider/model/size/n/negative_prompt/reference_images 可选；"
        "project_id/content_id/source_type/character_ids/reference_asset_ids 用于后续 lineage。"
    ),
    output_schema_note="返回 normalized_request、reference_image_count、lineage_hint、cost_warning；不会消耗模型额度。",
    risk_level="read",
    output_type="image_generation_request_preview",
)
async def preview_image_generation_request(
    prompt: str,
    negative_prompt: str = "",
    provider: str = "",
    model: str = "",
    size: str = "1024x1024",
    n: int = 1,
    style: str = "",
    source_image: str = "",
    reference_images: list[str] | None = None,
    project_id: str = "",
    content_id: str = "",
    source_type: str = "",
    source_index: str = "",
    source_title: str = "",
    chapter_number: str = "",
    reference_asset_ids: list[str] | None = None,
    character_ids: list[str] | None = None,
    portrait_node_ids: list[str] | None = None,
) -> dict[str, Any]:
    if not (prompt or "").strip():
        raise ValueError("prompt 不能为空")
    safe_n = max(1, min(int(n or 1), 4))
    normalized = {
        "prompt": prompt.strip(),
        "negative_prompt": negative_prompt or "",
        "provider": provider or "",
        "model": model or "",
        "size": size or "1024x1024",
        "n": safe_n,
        "style": style or "",
        "source_image": source_image or "",
        "reference_images": _compact_reference_images(reference_images),
    }
    lineage_hint = {
        "project_id": project_id,
        "content_id": content_id,
        "source_type": source_type,
        "source_index": source_index,
        "source_title": source_title,
        "chapter_number": chapter_number,
        "reference_asset_ids": reference_asset_ids or [],
        "character_ids": character_ids or [],
        "portrait_node_ids": portrait_node_ids or [],
    }
    return {
        "success": True,
        "normalized_request": normalized,
        "reference_image_count": len(reference_images or []),
        "lineage_hint": {key: value for key, value in lineage_hint.items() if value not in ("", [], None)},
        "cost_warning": "这只是预览；真正生图请调用 generate_image_asset，风险等级为 costly，需要用户确认。",
    }


@register_tool(
    name="generate_image_asset",
    description="调用 YLCraft 图片生成后端生成图片，并尽量保存到素材库/Asset Hub。",
    category="image",
    examples=["按当前角色视觉卡生成主立绘", "用分镜提示词生成漫画格图片并关联项目"],
    input_schema_note=(
        "必须提供 prompt；provider 建议来自 list_image_backends；model/size/n/negative_prompt/reference_images 可选；"
        "project_id/content_id/source_type/source_index/character_ids/reference_asset_ids 会写入生成 lineage。"
    ),
    output_schema_note=(
        "同步模型返回 url/local_path/asset_hub_node_id/all_asset_hub_node_ids；异步模型返回 task_id/external_task_id/status=pending，"
        "需继续调用 poll_image_generation_task。"
    ),
    risk_level="costly",
    output_type="image_generation_result",
    cost_hint="会真实调用图片模型，可能产生 API 费用；执行前应先预览并征得用户确认。",
)
async def generate_image_asset(
    prompt: str,
    negative_prompt: str = "",
    provider: str = "",
    model: str = "",
    size: str = "1024x1024",
    n: int = 1,
    style: str = "",
    seed: int | None = None,
    steps: int = 20,
    cfg_scale: float = 7.0,
    sampler: str = "euler",
    source_image: str = "",
    reference_images: list[str] | None = None,
    project_id: str = "",
    content_id: str = "",
    source_type: str = "agent",
    source_index: str = "",
    source_title: str = "",
    chapter_number: str = "",
    reference_asset_ids: list[str] | None = None,
    character_ids: list[str] | None = None,
    portrait_node_ids: list[str] | None = None,
    portrait_version_ids: list[str] | None = None,
) -> dict[str, Any]:
    if not (prompt or "").strip():
        raise ValueError("prompt 不能为空")
    from app.api.v1.images import ImageGenerateRequest, generate_image

    request = ImageGenerateRequest(
        prompt=prompt.strip(),
        negative_prompt=negative_prompt or "",
        provider=provider or None,
        model=model or None,
        size=size or "1024x1024",
        n=max(1, min(int(n or 1), 4)),
        style=style or None,
        seed=seed,
        steps=steps,
        cfg_scale=cfg_scale,
        sampler=sampler or "euler",
        source_image=source_image or None,
        reference_images=reference_images or [],
        project_id=project_id or None,
        content_id=content_id or None,
        source_type=source_type or "agent",
        source_index=source_index or None,
        source_title=source_title or None,
        chapter_number=chapter_number or None,
        reference_asset_ids=reference_asset_ids or [],
        character_ids=character_ids or [],
        portrait_node_ids=portrait_node_ids or [],
        portrait_version_ids=portrait_version_ids or [],
    )
    response = await generate_image(request)
    return _to_plain_dict(response)


@register_tool(
    name="poll_image_generation_task",
    description="查询异步图片生成任务状态，并在完成时触发保存到素材库。",
    category="image",
    examples=["查询刚才魔塔生图任务是否完成", "轮询图片生成任务并返回素材 ID"],
    input_schema_note="必须提供 generate_image_asset 返回的 task_id；provider 可选，一般不用传。",
    output_schema_note="返回 success/status/progress/url/local_path/asset_hub_node_id/all_asset_hub_node_ids/error。",
    risk_level="read",
    output_type="image_generation_task_status",
)
async def poll_image_generation_task(task_id: str, provider: str = "") -> dict[str, Any]:
    if not (task_id or "").strip():
        raise ValueError("task_id 不能为空")
    from app.api.v1.images import poll_image_task

    response = await poll_image_task(task_id=task_id.strip(), provider=provider or None)
    return _to_plain_dict(response)
