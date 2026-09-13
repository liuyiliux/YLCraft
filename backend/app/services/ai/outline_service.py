"""多平台生图 — 大纲生成服务（兼容层）。

主题 → 平台大纲的规划能力已提取到
``app.services.ai.content_package_planner.ContentPackagePlanner``。本模块保留为**兼容层**：

- ``generate_outline`` 的入参、返回值结构与逐平台兜底行为**逐字段不变**，
  ``/images/generate-outline`` 无需任何改动；
- ``_parse_outline_text`` 保留为兼容别名（实现已迁移）；
- 批量生图与资产入库（``batch_generate_images``）仍在本模块——规划与生成分离，
  便于内容包路径只复用规划而不连带触发消耗型操作。

原设计借鉴 yiliu/yiliu：topic → LLM 用平台模板生成结构化大纲。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.ai import get_ai_service
from app.services.ai.content_package_planner import ContentPackagePlanner

logger = logging.getLogger("ylcraft.image.outline")


async def generate_outline(
    session,
    topic: str,
    platforms: list[str],
    backend_name: Optional[str] = None,
    model: Optional[str] = None,
    reference_images: Optional[list[str]] = None,
) -> dict:
    """
    为一个主题生成多平台结构化大纲（委托给 ContentPackagePlanner）。

    Args:
        session: 数据库会话
        topic: 用户输入的主题
        platforms: 平台列表，如 ["xiaohongshu", "douyin"]
        backend_name: 指定 Backend 名称（如"小米2.5pro"），使用该 Backend 的默认模型
        model: 指定模型（如"mimo-v2.5-pro"），覆盖 Backend 默认模型
        reference_images: 参考图列表（base64 编码，可选，用于多模态 LLM 反推）

    Returns:
        {
            "xiaohongshu": {
                "title": "...",
                "description": "...",
                "pages": [{"type": "封面", "prompt": "..."}, ...]
            },
            ...
        }
        无可用平台模板时返回 {}。
    """
    return await ContentPackagePlanner().plan_platform_outlines(
        session,
        topic,
        platforms,
        backend_name=backend_name,
        model=model,
        reference_images=reference_images,
    )


def _parse_outline_text(text: str) -> dict:
    """兼容别名：实现已迁至 ``ContentPackagePlanner.parse_structured_text``。"""
    return ContentPackagePlanner.parse_structured_text(text)


async def batch_generate_images(
    session,
    pages: list[dict],
    provider: str = "",
    model: str = "",
    topic: Optional[str] = None,
    template_id: Optional[str] = None,
    outline_title: Optional[str] = None,
    outline_copywriting: Optional[str] = None,
    reference_images: list[str] = [],
) -> dict:
    """
    批量生成图片：对每一页调用现有的 generate_image。
    成功后自动入库到 Asset Hub。

    Args:
        pages: [{ "prompt", "platform", "size", "n" }]
        provider: AI 提供商
        model: 模型名
        topic: 多平台生图主题（可选，用于资产库记录）
        template_id: 平台模板 ID（可选）
        outline_title: 大纲标题（可选）
        outline_copywriting: 大纲文案（可选）
        reference_images: 参考图（base64 编码，支持反推人物特征）

    Returns:
        { "results": [{ "platform", "images": [urls] }] }
    """
    import asyncio
    from app.services.ai.types import ImageGenerationRequest
    from app.services.asset_hub import AssetHubFacade

    manager = get_ai_service()

    async def generate_single(page: dict) -> dict:
        try:
            req = ImageGenerationRequest(
                prompt=page.get("prompt", ""),
                size=page.get("size", "1024x1024"),
                n=page.get("n", 1),
                provider=provider or "",
                model=model or "",
                reference_images=reference_images,
            )
            result = await manager.generate_image(req)
            if result.success:
                urls = result.urls or [result.url] if result.url else []

                asset_hub_node_id = ""
                # 入库到资产中枢
                if result.local_path:
                    try:
                        # 构建多平台生图元数据
                        extra_metadata = {
                            "topic": topic or "",
                            "template_id": page.get("template_id", "") or template_id or "",
                            "outline_title": outline_title or "",
                            "outline_copywriting": outline_copywriting or "",
                            "page_type": page.get("type", ""),
                            "content_platform": page.get("platform", ""),  # 目标内容平台
                        }
                        hub_result = await AssetHubFacade(session).create_generated_image(
                            file_path=str(result.local_path),
                            prompt=page.get("prompt", ""),
                            provider=result.provider or provider,
                            model=result.model or model,
                            seed=result.seed,
                            source_url=result.url or "",
                            size=page.get("size", "1024x1024"),
                            generation_params=extra_metadata,
                            lineage={
                                "topic": topic or "",
                                "template_id": page.get("template_id", "") or template_id or "",
                                "outline_title": outline_title or "",
                                "page_type": page.get("type", ""),
                                "content_platform": page.get("platform", ""),
                            },
                            tags=[page.get("platform", ""), page.get("type", "")],
                        )
                        asset_hub_node_id = hub_result.node_id
                        logger.info(f"Batch image saved to asset library: {result.local_path}")
                    except Exception as asset_err:
                        logger.warning(f"Failed to save batch image to asset library: {asset_err}")

                return {
                    "platform": page.get("platform", ""),
                    "prompt": page.get("prompt", ""),
                    "urls": urls,
                    "success": True,
                    "asset_id": asset_hub_node_id,
                }
            return {
                "platform": page.get("platform", ""),
                "prompt": page.get("prompt", ""),
                "urls": [],
                "success": False,
                "error": result.error or "Generation failed",
            }
        except Exception as e:
            logger.error(f"Batch image generation failed for page: {e}")
            return {
                "platform": page.get("platform", ""),
                "prompt": page.get("prompt", ""),
                "urls": [],
                "success": False,
                "error": str(e),
            }

    # 并行执行所有生成任务（限制并发 3 个）
    semaphore = asyncio.Semaphore(3)

    async def generate_with_limit(page):
        async with semaphore:
            return await generate_single(page)

    tasks = [generate_with_limit(p) for p in pages]
    all_results = await asyncio.gather(*tasks)

    # 按平台分组
    grouped = {}
    for r in all_results:
        plat = r["platform"]
        if plat not in grouped:
            grouped[plat] = []
        grouped[plat].append(r)

    return {"results": grouped}
