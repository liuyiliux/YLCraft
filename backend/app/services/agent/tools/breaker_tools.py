"""Viral content breaker tools exposed to the Agent Center."""

from __future__ import annotations

import asyncio
import logging

from app.services.agent.registry import register_tool
from app.services.ai import get_ai_service
from app.services.ai.types import LLMMessage, MediaType
from app.services.breaker import create_task, get_task, run_analysis

logger = logging.getLogger("ylcraft.agent.tools.breaker")


@register_tool(
    name="analyze_viral_content",
    description="分析爆款视频或内容链接，提取文案结构、角色、分镜、情绪曲线和仿写提示。",
    category="breaker",
    input_schema_note="必须提供 http/https 视频或内容链接；当前会创建异步分析任务。",
    output_schema_note="返回 task_id/url/status/message；需要继续调用 get_breaker_task_status 查询结构化分析结果。",
    risk_level="external",
    output_type="breaker_task_started",
)
async def analyze_viral_content(url: str) -> dict:
    try:
        if not url or not url.startswith(("http://", "https://")):
            return {"success": False, "error": "无效的视频或内容链接"}

        break_task = await create_task(url)
        asyncio.create_task(run_analysis(break_task))

        return {
            "success": True,
            "data": {
                "task_id": break_task.task_id,
                "url": url,
                "status": break_task.status.value,
                "message": "爆款分析任务已启动，请使用 get_breaker_task_status 查询进度。",
            },
        }
    except Exception as exc:
        logger.error("analyze_viral_content failed: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool(
    name="get_breaker_task_status",
    description="查询爆款分析异步任务状态和结果。",
    category="breaker",
    input_schema_note="必须提供 analyze_viral_content 返回的 task_id。",
    output_schema_note="返回 status/progress/result/error；result 含标题、平台、钩子、情绪曲线、角色、分镜、仿写提示词和 transcript 摘要。",
    risk_level="read",
    output_type="breaker_analysis_status",
)
async def get_breaker_task_status(task_id: str) -> dict:
    try:
        break_task = await get_task(task_id)
        if not break_task:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        result_data = None
        if break_task.result:
            transcript = break_task.result.transcript or ""
            result_data = {
                "title": break_task.result.title,
                "author": break_task.result.author,
                "platform": break_task.result.platform,
                "video_url": break_task.result.video_url,
                "cover_url": break_task.result.cover_url,
                "duration_estimate": break_task.result.duration_estimate,
                "hook_analysis": break_task.result.hook_analysis,
                "structure": break_task.result.structure,
                "emotion_curve": break_task.result.emotion_curve,
                "key_elements": break_task.result.key_elements,
                "style_tags": break_task.result.style_tags,
                "viral_factors": break_task.result.viral_factors,
                "characters": [
                    {
                        "name": character.name,
                        "role": character.role,
                        "appearance": character.appearance,
                        "traits": character.traits,
                    }
                    for character in break_task.result.characters
                ],
                "shots": [
                    {
                        "order": shot.order,
                        "description": shot.description,
                        "shot_type": shot.shot_type,
                        "characters": shot.characters,
                        "dialogue": shot.dialogue,
                        "emotion": shot.emotion,
                    }
                    for shot in break_task.result.shots
                ],
                "rewrite_prompts": break_task.result.rewrite_prompts,
                "transcript": transcript[:1000] + "..." if len(transcript) > 1000 else transcript,
            }

        return {
            "success": True,
            "data": {
                "task_id": break_task.task_id,
                "url": break_task.url,
                "status": break_task.status.value,
                "progress": break_task.progress,
                "progress_message": break_task.progress_message,
                "result": result_data,
                "error": break_task.error,
            },
        }
    except Exception as exc:
        logger.error("get_breaker_task_status failed: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool(
    name="generate_script",
    description="基于主题和可选爆款分析结果生成短视频仿写脚本。",
    category="breaker",
    input_schema_note="必须提供 topic；style/duration 可选；reference_task_id 可引用爆款分析任务作为风格参考。",
    output_schema_note="返回 topic/style/duration/script/reference_used；script 为文本脚本，不会自动写入创作项目。",
    risk_level="costly",
    output_type="script_text_result",
    cost_hint="会调用文本模型生成脚本，可能产生模型费用，执行前需要确认。",
)
async def generate_script(
    topic: str,
    style: str = "",
    duration: str = "30秒",
    reference_task_id: str = "",
) -> dict:
    try:
        manager = get_ai_service()
        if not manager.is_loaded() or not manager.get_default(MediaType.LLM):
            return {"success": False, "error": "LLM 服务不可用，无法生成脚本"}

        reference_analysis = ""
        if reference_task_id:
            break_task = await get_task(reference_task_id)
            if break_task and break_task.result:
                ref = break_task.result
                reference_analysis = f"""
参考爆款视频分析：
- 标题：{ref.title}
- 平台：{ref.platform}
- 钩子手法：{ref.hook_analysis}
- 情绪曲线：{' -> '.join(ref.emotion_curve)}
- 核心要素：{ref.key_elements}
- 风格标签：{', '.join(ref.style_tags)}
- 爆款因子：{', '.join(ref.viral_factors)}
"""

        prompt = f"""你是一位短视频脚本创作专家。请根据以下要求创作一个短视频脚本：

## 创作要求

**主题**：{topic}
**目标时长**：{duration}
**风格**：{style if style else "参考爆款风格"}

{reference_analysis}

## 输出格式

请输出以下结构的脚本：
1. 标题：吸引人的标题，15字以内。
2. 钩子：前3秒如何抓住观众注意力。
3. 分镜脚本：镜号 | 画面描述 | 对白/字幕 | 时长。
4. 情绪节奏：开头 -> 中段 -> 结尾的情绪变化。
5. 拍摄建议：景别、运镜、特效建议。
6. 文案金句：3-5 个可复用金句模板。

请用中文输出，确保脚本结构清晰、有爆款潜质。"""

        result = await manager.chat([LLMMessage(role="user", content=prompt)])

        if not result.success:
            return {"success": False, "error": f"LLM 调用失败: {result.error}"}

        return {
            "success": True,
            "data": {
                "topic": topic,
                "style": style,
                "duration": duration,
                "script": result.content,
                "reference_used": bool(reference_task_id),
            },
        }
    except Exception as exc:
        logger.error("generate_script failed: %s", exc)
        return {"success": False, "error": str(exc)}


logger.info("[breaker_tools] registered: analyze_viral_content, get_breaker_task_status, generate_script")
