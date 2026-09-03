"""世界地图的视觉派生编排：生图提示词优化 + 成图生成。

真人 `/world-map` 页面与 Agent 工具共用本模块，避免两套调用各写一遍：
结构化 ``map_json`` 永远是正典，这里只产出派生视觉资产（提示词改写 / 成图）。

纪律：
- 提示词优化只改写文本，不落库、不生成图（消耗一次 LLM 文本配额）。
- 成图只以引用形式记回 ``map_json.visuals``，不改区域/据点/路线等空间关系；
  并发导致 revision 冲突时放弃回写，不回滚已生成的成图。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlmodel import Session

from app.db.database import get_async_session
from app.services.ai.service import get_ai_service
from app.services.ai.types import ImageGenerationRequest, LLMMessage
from app.services.asset_hub import AssetHubFacade
from app.services.asset_hub.reference_resolver import merge_reference_images
from app.services.creative_project.service import loads_json
from app.services.creative_project.visual_baseline import resolve_visual_baseline_asset_ids
from app.services.novel_source.world_map import (
    WorldMapDocument,
    WorldMapService,
    build_map_visual_prompt,
    render_map_svg,
)

logger = logging.getLogger("ylcraft.novel_source.world_map_visual")

WORLD_MAP_PROMPT_OPTIMIZE_SYSTEM = (
    "你是世界地图视觉提示词优化助手。把用户给的地图提示词改写成对图像模型更友好、"
    "且严格忠于原始地点/区域/坐标关系的中文描述。不得增删或改动任何地名、区域归属与"
    "坐标约束，不得虚构地点。只输出改写后的提示词正文，不要解释、不要代码块。"
)


def resolve_prompt(
    document: WorldMapDocument,
    *,
    prompt: str = "",
    style: str = "",
) -> str:
    """优先使用调用方确认过的提示词，否则从结构化数据确定性生成。"""
    return (prompt or "").strip() or build_map_visual_prompt(document, style=style)


async def optimize_map_visual_prompt(
    document: WorldMapDocument,
    *,
    prompt: str = "",
    style: str = "",
    focus: str = "",
    provider: str = "",
    model: str = "",
) -> dict[str, Any]:
    """用 LLM 润色生图提示词，返回原文与优化文；不落库、不生成图。"""
    raw = resolve_prompt(document, prompt=prompt, style=style)
    ai = get_ai_service()
    if not ai.is_loaded():
        raise RuntimeError("AIService 未初始化，请先配置 LLM Provider")

    focus_line = f"希望强调或修正：{focus.strip()}。" if (focus or "").strip() else "无额外强调项。"
    user_text = (
        "原始地图提示词：\n"
        f"{raw}\n\n"
        f"{focus_line}\n\n"
        "优化要求：\n"
        "1. 保留所有地点名称、坐标约束 (x,y) 与相对方位、区域划分、通行路线走向。\n"
        "2. 增强对图像模型友好的构图、景深、光影、材质与文字标签清晰度描述。\n"
        "3. 中文输出，地图标题与地名一律用原文。\n"
        "4. 只输出优化后的提示词正文。"
    )
    response = await ai.chat(
        messages=[
            LLMMessage(role="system", content=WORLD_MAP_PROMPT_OPTIMIZE_SYSTEM),
            LLMMessage(role="user", content=user_text),
        ],
        provider=provider or None,
        model=model or None,
        temperature=0.7,
        max_tokens=1800,
    )
    if getattr(response, "success", True) is False:
        raise RuntimeError(getattr(response, "error", "") or "LLM 优化失败")
    optimized = str(getattr(response, "content", "") or "").strip()
    if not optimized:
        raise RuntimeError("LLM 未返回优化结果")
    return {"prompt": raw, "optimized_prompt": optimized}


def _local_file_url(path_or_url: str) -> str:
    """本地已落盘时转成平台内部下载地址，避免供应商临时图床过期。"""
    if not path_or_url:
        return ""
    if path_or_url.startswith(("/api/", "http://", "https://", "data:")):
        return path_or_url
    from app.services.asset_file_resolver import to_asset_download_url

    return to_asset_download_url(path_or_url)


async def generate_map_visual(
    session: Session,
    document: WorldMapDocument,
    *,
    prompt: str = "",
    style: str = "",
    negative_prompt: str = "",
    size: str = "1024x1024",
    n: int = 1,
    provider: str = "",
    model: str = "",
    reference_images: list[str] | None = None,
    reference_asset_ids: list[str] | None = None,
    save_to_asset_hub: bool = True,
) -> dict[str, Any]:
    """调用生图 Provider 生成地图视觉成图，并按需入资产中枢、回写引用。

    参考图优先传**素材库 ID**（稳定引用，服务端解析为本地图片路径），
    与 AI 图片链路同一套解析器；直接的 URL/base64 作为兜底保留。
    """
    manager = get_ai_service()
    if not manager.is_loaded():
        raise RuntimeError("AIService 未初始化，请先在 AI 连接器配置生图 Provider")

    resolved_prompt = resolve_prompt(document, prompt=prompt, style=style)
    # 项目视觉基准自动注入：页面与 Agent 都无需各自记得传，没设置也不阻塞生图。
    baseline_ids = resolve_visual_baseline_asset_ids(session, document.project_id)
    resolved_references = await merge_reference_images(
        reference_images=list(reference_images or []),
        # 调用方显式指定的参考图在前，项目基准在后，去重后不会重复占位。
        reference_asset_ids=[*list(reference_asset_ids or []), *baseline_ids],
    )
    result = await manager.generate_image(
        ImageGenerationRequest(
            prompt=resolved_prompt,
            negative_prompt=negative_prompt or "",
            size=size or "1024x1024",
            n=n or 1,
            style=style or "",
            provider=provider or "",
            model=model or "",
            reference_images=resolved_references,
        )
    )
    if not result.success:
        raise RuntimeError(f"生图失败: {result.error or 'unknown error'}")

    urls = result.urls or ([result.url] if result.url else [])
    local_paths = result.all_local_paths or ([result.local_path] if result.local_path else [])
    if not urls and not local_paths:
        raise RuntimeError("生图成功但未返回图片")

    local_path = local_paths[0] if local_paths else ""
    url = _local_file_url(local_path) if local_path else (urls[0] if urls else "")

    node_id = ""
    if save_to_asset_hub:
        try:
            async with get_async_session() as asset_session:
                created = await AssetHubFacade(asset_session).create_generated_image(
                    file_path=local_path or url,
                    prompt=resolved_prompt,
                    provider=result.provider or provider or "",
                    model=result.model or model or "",
                    source_url=url,
                    negative_prompt=negative_prompt or "",
                    size=size or "",
                    seed=result.seed,
                    generation_params={
                        "style": style or "",
                        "reference_images_count": len(reference_images or []),
                    },
                    lineage={
                        "source": "world_map_visual",
                        "map_id": document.id,
                        "map_title": str(document.title or ""),
                    },
                    tags=["world_map_visual", *(["style:" + style] if style else [])],
                )
                node_id = created.node_id
        except Exception as exc:  # 生图本身已成功，入库失败不回滚成图。
            logger.warning("world map visual asset hub sync failed: %s", exc)

    # 成图只作为派生引用记回地图，不改结构化空间关系。
    service = WorldMapService(session)
    data = loads_json(document.map_json, {})
    if isinstance(data, dict):
        visuals = data.get("visuals")
        if not isinstance(visuals, list):
            visuals = []
        visuals.append(
            {
                "url": url,
                "local_path": local_path,
                "node_id": node_id,
                "provider": result.provider or provider or "",
                "model": result.model or model or "",
                "style": style or "",
                "prompt": resolved_prompt,
                "created_at": datetime.now().isoformat(),
            }
        )
        data["visuals"] = visuals
        try:
            service.update_map(
                document.id,
                map_json=data,
                expected_revision=int(document.revision or 1),
            )
        except ValueError:
            # 并发已被他人编辑时，放弃回写引用，不影响已生成的成图。
            logger.warning("world map visual reference not persisted (revision conflict)")

    return {
        "prompt": resolved_prompt,
        "url": url,
        "local_path": local_path,
        "node_id": node_id,
        "provider": result.provider,
        "model": result.model,
        "task_id": result.task_id,
        "status": result.status,
    }


def render_map_svg_text(document: WorldMapDocument) -> str:
    """确定性渲染入口（不调用模型），供导出与 Agent 复用。"""
    return render_map_svg(document)
