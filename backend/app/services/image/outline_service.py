"""
多平台生图 — 大纲生成服务

借鉴 yiliu/yiliu 的设计：topic → LLM 用平台模板生成结构化大纲
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlmodel import select
from jinja2 import Template

from app.core.contracts.types import LLMMessage
from app.services.llm.manager import get_manager
from app.db.models.platform_template import PlatformTemplate

logger = logging.getLogger("ylcraft.image.outline")


async def generate_outline(
    session,
    topic: str,
    platforms: list[str],
    llm_model: Optional[str] = None,
    reference_images: Optional[list[str]] = None,
) -> dict:
    """
    为一个主题生成多平台结构化大纲。

    Args:
        session: 数据库会话
        topic: 用户输入的主题
        platforms: 平台列表，如 ["xiaohongshu", "douyin"]
        llm_model: 指定使用的 LLM 模型（可选）
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
    """
    manager = get_manager()

    # 1. 查 DB 获取平台模板（只要 is_active 的）
    stmt = select(PlatformTemplate).where(
        PlatformTemplate.platform.in_(platforms),
        PlatformTemplate.is_active == True,
    ).order_by(PlatformTemplate.sort_order)
    result = await session.exec(stmt)
    templates = result.all()

    if not templates:
        logger.warning(f"No active platform templates found for: {platforms}")
        return {}

    # 2. 调用 LLM 为每个平台生成大纲
    outlines = {}
    for tmpl in templates:
        try:
            # 渲染 outline_template 为 system prompt，传入 topic 和 page_structure
            import json
            page_structure_json = json.dumps(tmpl.page_structure, ensure_ascii=False) if tmpl.page_structure else ""
            system_prompt = Template(tmpl.outline_template).render(
                topic=topic,
                page_structure=page_structure_json,
            )
            
            # 构建消息（支持多模态）
            messages: list[dict] = []
            if reference_images and len(reference_images) > 0:
                # 多模态消息格式：[ {"type": "text", "text": ...}, {"type": "image_url", "image_url": {"url": ...}} ]
                content = [{"type": "text", "text": system_prompt}]
                for img in reference_images:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": img}
                    })
                messages = [{"role": "user", "content": content}]
            else:
                # 纯文本
                messages = [{"role": "user", "content": system_prompt}]
            
            # 调用 LLM（支持指定模型）
            resp = await manager.chat(
                messages=[LLMMessage(role=m["role"], content=m["content"]) for m in messages],
                model=llm_model or "",
            )
            
            if resp and resp.content:
                # 解析 LLM 返回的结构化内容
                parsed = _parse_outline_text(resp.content)
                parsed["platform"] = tmpl.platform
                parsed["platform_name"] = tmpl.name
                outlines[tmpl.platform] = parsed
                logger.info(f"Generated outline for {tmpl.platform} ({len(parsed.get('pages', []))} pages)")
            else:
                logger.warning(f"LLM returned empty content for platform {tmpl.platform}")
                outlines[tmpl.platform] = {"title": topic, "copywriting": "", "pages": [], "platform": tmpl.platform, "platform_name": tmpl.name}
        
        except Exception as e:
            logger.error(f"Failed to generate outline for {tmpl.platform}: {e}")
            outlines[tmpl.platform] = {"title": topic, "copywriting": "", "pages": [], "platform": tmpl.platform, "platform_name": tmpl.name, "error": str(e)}

    return outlines


def _parse_outline_text(text: str) -> dict:
    """解析 LLM 返回的大纲文本为结构化数据
    
    支持格式：
    - 【标题】：xxx
    - 【文案】：xxx（可选，用于小红书等平台的完整文案/话题标签）
    - 【图片提示词】：[封面] xxx <page> 【图片提示词】：[内容] xxx
    """
    result = {"title": "", "copywriting": "", "pages": []}

    # 提取标题：【标题】xxx
    title_match = re.search(r'【标题】[:：]?\s*(.+?)(?:\n|【|$)', text, re.DOTALL)
    if title_match:
        result["title"] = title_match.group(1).strip()

    # 提取文案（copywriting）：【文案】xxx
    copywriting_match = re.search(r'【文案】[:：]?\s*(.+?)(?:\n\s*【|$)', text, re.DOTALL)
    if copywriting_match:
        result["copywriting"] = copywriting_match.group(1).strip()

    # 提取每页：【图片提示词】xxx --- 【图片提示词】xxx
    # 先按 【图片提示词】 分割
    pages_raw = re.split(r'【图片提示词】[:：]?', text)
    for part in pages_raw[1:]:  # 跳过第一个（在第一个【图片提示词】之前的内容）
        part = part.strip()
        if not part:
            continue

        # 提取页面类型：[封面]/[内容]/[总结]/[标题]/[正文]/[引言]/[案例]/[导语]/[结尾]/[图片说明]
        type_match = re.match(r'\[(.+?)\]', part)
        page_type = type_match.group(1) if type_match else "内容"

        # 去掉类型标记和后续的 --- 分隔符（如果还有下一页）
        prompt = re.sub(r'^\[.+?\]\s*', '', part)
        prompt = re.split(r'\n\s*---', prompt)[0].strip()

        if prompt:
            result["pages"].append({
                "type": page_type,
                "prompt": prompt,
            })

    return result


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
    成功后自动入库到 AssetService。

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
    from app.core.contracts.types import ImageGenerationRequest
    from app.services.asset.service import AssetService

    manager = get_manager()

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

                # 入库到资产库
                if result.local_path:
                    try:
                        asset_service = AssetService(session)
                        # 构建多平台生图元数据
                        extra_metadata = {
                            "topic": topic or "",
                            "template_id": template_id or "",
                            "outline_title": outline_title or "",
                            "outline_copywriting": outline_copywriting or "",
                            "page_type": page.get("type", ""),
                            "content_platform": page.get("platform", ""),  # 目标内容平台
                        }
                        await asset_service.create_from_image_generation(
                            image_path=str(result.local_path),
                            prompt=page.get("prompt", ""),
                            provider=result.provider or provider,
                            model=result.model or model,
                            seed=result.seed,
                            url=result.url or "",
                            size=page.get("size", "1024x1024"),
                            metadata=extra_metadata,
                        )
                        logger.info(f"Batch image saved to asset library: {result.local_path}")
                    except Exception as asset_err:
                        logger.warning(f"Failed to save batch image to asset library: {asset_err}")

                return {
                    "platform": page.get("platform", ""),
                    "prompt": page.get("prompt", ""),
                    "urls": urls,
                    "success": True,
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
