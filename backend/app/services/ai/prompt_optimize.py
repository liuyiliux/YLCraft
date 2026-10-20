"""生图提示词的 LLM 优化：只润色文字，不生成图片、不落库。

与地图生图提示词优化（world_map_visual.optimize_map_visual_prompt）同构，
但面向通用文生图：不强求保留地图坐标/地名，而是强化图像模型友好的描述
（构图、光影、材质、风格与画质）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.ai import get_ai_service
from app.services.ai.service import ai_call_context
from app.services.ai.types import LLMMessage

logger = logging.getLogger("ylcraft.ai.prompt_optimize")

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

#: 动图优化时的附加约束。
#:
#: 为什么要单独一段：动图不是"生成一张图"，而是**一次性画好多格连续画面**再拼成动画。
#: 按静态图思路优化会产出「一个蓝狗不想上班的表情包立绘，高清细节，8K」这种**单张图**
#: 描述，模型完全不知道要画成多格连贯的分格图。
#:
#: 更糟的是前端会把"已优化"当作**不再追加系统技术规则**的依据，于是连多格图约束
#: 一起丢掉 —— 这是一条真实的逻辑冲突，不只是"AI 不知道动图"。
MOTION_GIF_OPTIMIZE_SYSTEM = (
    "你正在优化的是**多格图（frame sheet）**的提示词，不是单张图片的提示词。\n"
    "多格图会被切成若干格、依次连成一个循环动画，因此提示词必须满足：\n"
    "1. 明确要求输出为一张**分格图**：{rows} 行 × {cols} 列、共 {cells} 格、"
    "从左到右从上到下阅读、格子等大、无可见网格线。\n"
    "2. 明确说明这 {cells} 格表现的是**同一主体的一段连续动作**，"
    "不是 {cells} 张互相独立的图片。\n"
    "3. 强调相邻两格之间的变化量**完全相同**，动作匀速、不得在换行处重新开始。\n"
    "4. 按动效类型「{motion_label}」的写法来写：{motion_hint}。\n"
    "5. 补充「同一主体、同一画风、同一光位」这类跨格一致性的约束。\n"
    "6. 若用户提供了参考图，按图中主体来写描述。\n"
    "仍然只输出优化后的提示词正文，不要解释、不要围栏。"
)


async def optimize_image_prompt(
    *,
    prompt: str = "",
    instruction: str = "",
    provider: str = "",
    model: str = "",
    motion_gif: dict[str, Any] | None = None,
    reference_images: list[str] | None = None,
) -> dict[str, Any]:
    """用 LLM 润色生图提示词，返回原文与优化文。

    Args:
        prompt: 原始提示词。
        instruction: 单独的修改描述（可选），如"改成雨天、加广角镜头"。
        provider / model: 指定用于优化的 LLM；留空走默认后端。
        motion_gif: 动图参数 `{motion_kind, rows, cols, cells}`。给了就按**多格图**
            的思路优化，而不是按单张图。
        reference_images: 参考图（data URL 或 http(s) URL），**多张按顺序全传**。
            仅当该连接器 `support_vision_input=true` 时才真正带上——不支持时
            直接忽略，不报错（用户选了不支持视觉的模型也不该整单失败）。
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

    system_prompt = IMAGE_PROMPT_OPTIMIZE_SYSTEM
    motion_note = ""
    if motion_gif:
        from app.services.image.motion_prompt import motion_kind_spec

        try:
            kind_spec = motion_kind_spec(str(motion_gif.get("motion_kind") or "orbit"))
        except ValueError:
            kind_spec = None
        rows = int(motion_gif.get("rows") or 0)
        cols = int(motion_gif.get("cols") or 0)
        cells = int(motion_gif.get("cells") or (rows * cols if rows and cols else 8))
        system_prompt = (
            IMAGE_PROMPT_OPTIMIZE_SYSTEM
            + "\n\n"
            + MOTION_GIF_OPTIMIZE_SYSTEM.format(
                rows=rows or "?",
                cols=cols or "?",
                cells=cells,
                motion_label=(kind_spec.label if kind_spec else "按用户描述"),
                motion_hint=(
                    _motion_rule_zh(kind_spec.key, rows, cols) if kind_spec else "按用户的动作描述"
                ),
            )
        )
        motion_note = (
            f"\n注意：本次是为**多格图**写提示词（{rows}×{cols}={cells} 格，"
            f"动效类型「{kind_spec.label if kind_spec else '未指定'}」），"
            f"不是单张图片。"
        )

    user_text = (
        "原始提示词：\n"
        f"{raw}\n\n"
        f"{instruction_line}{motion_note}\n\n"
        "请输出优化后的提示词正文。"
    )

    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=_build_user_content(user_text, reference_images, provider)),
    ]

    with ai_call_context(
        scene="image",
        task_type="image_prompt_optimize",
        label="生图提示词优化",
        retry_payload={
            "prompt": raw,
            "instruction": instruction or "",
            "provider": provider or "",
            "model": model or "",
            "motion_gif": motion_gif or {},
            # 只记张数不记图片本体：base64 动辄几十万字符，重发载荷会炸
            "reference_image_count": len(reference_images or []),
        },
    ):
        response = await ai.chat(
            messages=messages,
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


#: 单次优化最多带几张参考图。
#:
#: 上限的理由：图片进 prompt 会显著增加 token 与耗时（实测纯文本优化已要 ~20s），
#: 且页面上参考图本来就有张数上限；这里再兜一层，防止误传一大串 base64。
MAX_REFERENCE_IMAGES = 6


def _connector_supports_vision(provider: str) -> bool:
    """该连接器是否声明支持视觉输入。

    查不到就按**不支持**处理：宁可少带图，也不要让一个不支持视觉的模型
    收到 image_url 后整单报错——用户只是选了别的模型，不该因此优化失败。
    """
    if not provider:
        return False
    try:
        from app.db.database import SessionLocal
        from app.db.models.ai_connector import AIConnector

        with SessionLocal() as db:
            conn = (
                db.query(AIConnector)
                .filter(AIConnector.provider_type == "llm")
                .filter(
                    (AIConnector.name == provider) | (AIConnector.provider == provider)
                )
                .first()
            )
            return bool(getattr(conn, "support_vision_input", False)) if conn else False
    except Exception:
        return False


def _motion_rule_zh(kind: str, rows: int = 0, cols: int = 0) -> str:
    """动效类型的一句话写法提示。

    直接取 `motion_prompt` 里已有的规则，保证优化提示词与实际追加的系统块
    **同一份来源** —— 两处各写一遍必然漂移。
    """
    from app.services.image import motion_prompt

    try:
        spec = motion_prompt.motion_kind_spec(kind)  # type: ignore[arg-type]
    except ValueError:
        return "按用户的动作描述"
    # 格数按实际排布取：环绕类的角度步长依赖格数（8 格 vs 16 格步长不同）
    if rows and cols:
        layout = motion_prompt.GridSpec(  # type: ignore[arg-type]
            key=spec.key if spec.key in {g.key for g in motion_prompt.GRID_LAYOUTS} else "2x4",
            label="",
            rows=rows,
            cols=cols,
            note="",
        )
    else:
        layout = motion_prompt.grid_spec("2x4")
    return motion_prompt._motion_rule_zh(spec.key, layout)


def _build_user_content(
    text: str,
    reference_images: list[str] | None,
    provider: str,
) -> str | list[dict]:
    """构造 user 消息内容：有可用参考图时用多模态数组，否则纯文本。

    多模态格式沿用 `content_package_planner.build_outline_messages` 的约定：
    ``[{"type": "text", ...}, {"type": "image_url", "image_url": {"url": ...}}]``

    **多张按传入顺序全传**（用户勾选顺序即模型看到的顺序，与生图链路一致）。
    """
    images = [u for u in (reference_images or []) if isinstance(u, str) and u.strip()]
    if not images:
        return text
    if not _connector_supports_vision(provider):
        logger.info(
            "[prompt_optimize] 连接器 %s 未声明支持视觉输入，忽略 %d 张参考图",
            provider,
            len(images),
        )
        return text

    usable = images[:MAX_REFERENCE_IMAGES]
    if len(images) > len(usable):
        logger.info(
            "[prompt_optimize] 参考图 %d 张超过上限，只传前 %d 张",
            len(images),
            len(usable),
        )
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for url in usable:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content
