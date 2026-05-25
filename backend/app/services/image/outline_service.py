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
) -> dict:
    """
    为一个主题生成多平台结构化大纲。

    Args:
        session: 数据库会话
        topic: 用户输入的主题
        platforms: 平台列表，如 ["xiaohongshu", "douyin"]

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
            # 渲染 outline_template 为 system prompt
            system_prompt = Template(tmpl.outline_template).render(topic=topic)
            
            # 调用 LLM
            resp = await manager.chat(
                messages=[LLMMessage(role="user", content=system_prompt)],
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
                outlines[tmpl.platform] = {"title": topic, "description": "", "pages": [], "platform": tmpl.platform, "platform_name": tmpl.name}
        
        except Exception as e:
            logger.error(f"Failed to generate outline for {tmpl.platform}: {e}")
            outlines[tmpl.platform] = {"title": topic, "description": "", "pages": [], "platform": tmpl.platform, "platform_name": tmpl.name, "error": str(e)}

    return outlines


def _parse_outline_text(text: str) -> dict:
    """解析 LLM 返回的大纲文本为结构化数据"""
    result = {"title": "", "description": "", "pages": []}

    # 提取标题：【标题】xxx
    title_match = re.search(r'【标题】[:：]?\s*(.+?)(?:\n|【|$)', text, re.DOTALL)
    if title_match:
        result["title"] = title_match.group(1).strip()

    # 提取文案：【文案】xxx
    desc_match = re.search(r'【文案】[:：]?\s*(.+?)(?:\n\s*【|$)', text, re.DOTALL)
    if desc_match:
        result["description"] = desc_match.group(1).strip()

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
) -> dict:
    """
    批量生成图片：对每一页调用现有的 generate_image。

    Args:
        pages: [{ "prompt", "platform", "size", "n" }]
        provider: AI 提供商
        model: 模型名

    Returns:
        { "results": [{ "platform", "images": [urls] }] }
    """
    import asyncio
    from app.core.contracts.types import ImageGenerationRequest

    manager = get_manager()

    async def generate_single(page: dict) -> dict:
        try:
            req = ImageGenerationRequest(
                prompt=page.get("prompt", ""),
                size=page.get("size", "1024x1024"),
                n=page.get("n", 1),
                provider=provider or "",
                model=model or "",
            )
            result = await manager.generate_image(req)
            if result.success:
                return {
                    "platform": page.get("platform", ""),
                    "prompt": page.get("prompt", ""),
                    "urls": result.urls or [result.url] if result.url else [],
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
