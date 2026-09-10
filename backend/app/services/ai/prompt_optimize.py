"""生图提示词的 LLM 优化：只润色文字，不生成图片、不落库。

与地图生图提示词优化（world_map_visual.optimize_map_visual_prompt）同构，
但面向通用文生图：不强求保留地图坐标/地名，而是强化图像模型友好的描述
（构图、光影、材质、风格与画质）。
"""

from __future__ import annotations

from typing import Any

from app.services.ai import get_ai_service
from app.services.ai.service import ai_call_context
from app.services.ai.types import LLMMessage

IMAGE_PROMPT_OPTIMIZE_SYSTEM = (
    "你是资深 AI 绘画提示词工程师，擅长把朴素的描述改写成图像生成模型"
    "能稳定理解的高质量提示词。\n"
    "规则：\n"
    "1. 完整保留用户的核心意图：主体、动作、场景、情绪与关键细节，不得增删事实。\n"
    "2. 补充对图像模型友好的描述：镜头与构图、光线方向与质感、材质细节、"
    "风格取向、色彩倾向、画质与分辨率词。\n"
    "3. 用户给了「修改描述」时，优先按其要求调整，再考虑其它增强项。\n"
    "4. 输出语言跟随用户原文（中文为主）；若原文是结构化 JSON，保持原有结构，"
    "只重写其中的自然语言字段值。\n"
    "5. 只输出优化后的提示词正文：不要解释、不要前后缀说明、不要 Markdown 代码块围栏。"
)


async def optimize_image_prompt(
    *,
    prompt: str = "",
    instruction: str = "",
    provider: str = "",
    model: str = "",
) -> dict[str, Any]:
    """用 LLM 润色生图提示词，返回原文与优化文。

    Args:
        prompt: 原始提示词。
        instruction: 单独的修改描述（可选），如"改成雨天、加广角镜头"。
        provider / model: 指定用于优化的 LLM；留空走默认后端。
    """
    raw = (prompt or "").strip()
    if not raw:
        raise ValueError("请先填写提示词")

    ai = get_ai_service()
    if not ai.is_loaded():
        raise RuntimeError("AIService 未初始化，请先配置 LLM Provider")

    instruction_line = (
        f"修改描述（优先满足）：{(instruction or '').strip()}。"
        if (instruction or "").strip()
        else "无额外修改描述，按通用增强原则优化。"
    )
    user_text = (
        "原始提示词：\n"
        f"{raw}\n\n"
        f"{instruction_line}\n\n"
        "请输出优化后的提示词正文。"
    )

    with ai_call_context(
        scene="image",
        task_type="image_prompt_optimize",
        label="生图提示词优化",
        retry_payload={
            "prompt": raw,
            "instruction": instruction or "",
            "provider": provider or "",
            "model": model or "",
        },
    ):
        response = await ai.chat(
            messages=[
                LLMMessage(role="system", content=IMAGE_PROMPT_OPTIMIZE_SYSTEM),
                LLMMessage(role="user", content=user_text),
            ],
            provider=provider or None,
            model=model or None,
            temperature=0.7,
            max_tokens=2000,
        )

    if getattr(response, "success", True) is False:
        raise RuntimeError(getattr(response, "error", "") or "LLM 优化失败")
    optimized = str(getattr(response, "content", "") or "").strip()
    if not optimized:
        raise RuntimeError("LLM 未返回优化结果")
    return {"prompt": raw, "optimized_prompt": optimized}
