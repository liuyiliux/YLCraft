"""
YLCraft — 爆款拆解工具封装

封装 BreakerService 为 Agent 可调用的工具
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.agent.registry import register_tool
from app.services.breaker import (
    create_task,
    get_task,
    run_analysis,
    BreakTask,
    AnalysisStatus,
)
from app.services.ai import get_ai_service
from app.services.ai.types import MediaType

logger = logging.getLogger("ylcraft.agent.tools.breaker")


@register_tool(
    name="analyze_viral_content",
    description="分析爆款视频内容（输入链接，输出文案结构、角色、分镜、仿写提示词）",
    category="breaker"
)
async def analyze_viral_content(url: str) -> dict:
    """分析爆款内容"""
    try:
        if not url or not url.startswith("http"):
            return {"success": False, "error": "无效的视频链接"}

        # 创建任务
        break_task = await create_task(url)

        # 启动分析（异步执行）
        import asyncio
        asyncio.create_task(run_analysis(break_task))

        return {
            "success": True,
            "data": {
                "task_id": break_task.task_id,
                "url": url,
                "status": break_task.status.value,
                "message": "爆款分析任务已启动，请使用 get_breaker_task_status 查询进度",
            }
        }
    except Exception as e:
        logger.error(f"analyze_viral_content failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="get_breaker_task_status",
    description="查询爆款分析任务状态",
    category="breaker"
)
async def get_breaker_task_status(task_id: str) -> dict:
    """查询爆款分析任务状态"""
    try:
        break_task = await get_task(task_id)
        if not break_task:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        result_data = None
        if break_task.result:
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
                        "name": c.name,
                        "role": c.role,
                        "appearance": c.appearance,
                        "traits": c.traits,
                    }
                    for c in break_task.result.characters
                ],
                "shots": [
                    {
                        "order": s.order,
                        "description": s.description,
                        "shot_type": s.shot_type,
                        "characters": s.characters,
                        "dialogue": s.dialogue,
                        "emotion": s.emotion,
                    }
                    for s in break_task.result.shots
                ],
                "rewrite_prompts": break_task.result.rewrite_prompts,
                "transcript": break_task.result.transcript[:1000] + "..." if len(break_task.result.transcript) > 1000 else break_task.result.transcript,
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
            }
        }
    except Exception as e:
        logger.error(f"get_breaker_task_status failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="generate_script",
    description="基于爆款分析生成仿写脚本",
    category="breaker"
)
async def generate_script(
    topic: str,
    style: str = "",
    duration: str = "30秒",
    reference_task_id: str = "",
) -> dict:
    """生成仿写脚本"""
    try:
        manager = get_ai_service()
        if not manager.is_loaded() or not manager.get_default(MediaType.LLM):
            return {"success": False, "error": "LLM 服务不可用，无法生成脚本"}

        # 如果有参考任务，获取其分析结果
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

        # 构建提示词
        prompt = f"""你是一位短视频脚本创作专家。请根据以下要求创作一个短视频脚本：

## 创作要求

**主题**：{topic}
**目标时长**：{duration}
**风格**：{style if style else "参考爆款风格"}

{reference_analysis}

## 输出格式

请输出以下结构的脚本：

1. **标题**：吸引人的标题（15字以内）
2. **钩子**（前3秒）：如何抓住观众注意力
3. **分镜脚本**：
   - 镜号 | 画面描述 | 对白/字幕 | 时长
4. **情绪节奏**：开头->中段->结尾的情绪变化
5. **拍摄建议**：景别、运镜、特效建议
6. **文案金句**：3-5个可复用的金句模板

请用中文输出，确保脚本结构清晰、有爆款潜质。"""

        from app.services.ai.types import LLMMessage
        result = await manager.chat(
            [LLMMessage(role="user", content=prompt)],
        )

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
            }
        }
    except Exception as e:
        logger.error(f"generate_script failed: {e}")
        return {"success": False, "error": str(e)}


logger.info("[breaker_tools] 爆款拆解工具注册完成: analyze_viral_content, get_breaker_task_status, generate_script")
