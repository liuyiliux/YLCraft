"""Video clipping tools exposed to the Agent Center."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.services.agent.registry import register_tool
from app.services.clip.cutclaw_service import CutClawConfig, get_cutclaw_service
from app.services.clip.moe_service import get_moe_service
from app.services.clip.narrato_service import NarratoConfig, get_narrato_service

logger = logging.getLogger("ylcraft.agent.tools.clip")

DEFAULT_CLIP_INSTRUCTION = "请帮我拆出最精彩的片段，适合短视频分发。"


@register_tool(
    name="start_cutclaw_clip",
    description="启动 CutClaw Agent 智能剪辑，按自然语言目标分析并剪辑本地视频。",
    category="clip",
    input_schema_note="必须提供本地 video_path；instruction 为自然语言剪辑目标；options 可含 max_turns/auto_cut/output_format/provider/model。",
    output_schema_note="返回 task_id/task_type/video_path/instruction；这是异步任务，需要继续调用 get_clip_task_status 查询。",
    risk_level="costly",
    output_type="clip_task_started",
    cost_hint="会启动剪辑智能体和可能的 LLM/视频处理任务，执行前需要确认。",
)
async def start_cutclaw_clip(video_path: str, instruction: Optional[str] = None, options: Optional[dict] = None) -> dict:
    try:
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            return {"success": False, "error": f"视频文件不存在: {video_path}"}

        service = get_cutclaw_service()
        config = CutClawConfig()
        if options:
            if "max_turns" in options:
                config.max_turns = options["max_turns"]
            if "auto_cut" in options:
                config.auto_cut = options["auto_cut"]
            if "output_format" in options:
                config.output_format = options["output_format"]
            if "provider" in options:
                config.provider = options["provider"]
            if "model" in options:
                config.model = options["model"]

        final_instruction = instruction or DEFAULT_CLIP_INSTRUCTION
        task_id = await service.start_agent_task(
            video_path=str(video_path_obj),
            instruction=final_instruction,
            config=config,
            auto_cut=config.auto_cut,
        )

        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "task_type": "cutclaw_agent",
                "video_path": str(video_path_obj),
                "instruction": final_instruction,
                "message": "CutClaw Agent 剪辑任务已启动，请使用 get_clip_task_status 查询进度。",
            },
        }
    except Exception as exc:
        logger.error("start_cutclaw_clip failed: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool(
    name="start_narrato_clip",
    description="启动 NarratoAI Pipeline 自动剪辑，按卖点和美学评分选择候选片段。",
    category="clip",
    input_schema_note="必须提供本地 video_path；target_duration 为目标秒数；num_clips 为候选片段数；output_dir 可为空。",
    output_schema_note="返回 task_id/task_type/video_path/config；这是异步任务，需要继续调用 get_clip_task_status 查询。",
    risk_level="costly",
    output_type="clip_task_started",
    cost_hint="会启动 Narrato 剪辑任务，可能调用模型并生成新视频文件，执行前需要确认。",
)
async def start_narrato_clip(
    video_path: str,
    target_duration: float = 60.0,
    num_clips: int = 5,
    output_dir: Optional[str] = None,
) -> dict:
    try:
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            return {"success": False, "error": f"视频文件不存在: {video_path}"}

        service = get_narrato_service()
        config = NarratoConfig(
            target_duration=target_duration,
            num_clips=num_clips,
            output_dir=output_dir or str(video_path_obj.parent),
        )

        task_id = await service.start_pipeline_task(
            video_path=str(video_path_obj),
            config=config,
        )

        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "task_type": "narrato_pipeline",
                "video_path": str(video_path_obj),
                "config": {
                    "target_duration": target_duration,
                    "num_clips": num_clips,
                    "output_dir": output_dir or str(video_path_obj.parent),
                },
                "message": "NarratoAI Pipeline 剪辑任务已启动，请使用 get_clip_task_status 查询进度。",
            },
        }
    except Exception as exc:
        logger.error("start_narrato_clip failed: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool(
    name="start_moe_clip",
    description="启动 MoE 多专家并行剪辑，按策略从本地视频中选择最佳片段。",
    category="clip",
    input_schema_note="必须提供本地 video_path；strategy 默认 auto；min_clip_duration/max_clips 控制片段范围。",
    output_schema_note="返回 task_id/task_type/video_path/strategy；这是异步任务，需要继续调用 get_clip_task_status 查询。",
    risk_level="costly",
    output_type="clip_task_started",
    cost_hint="会启动 MoE 剪辑任务并占用视频处理资源，执行前需要确认。",
)
async def start_moe_clip(
    video_path: str,
    strategy: str = "auto",
    min_clip_duration: float = 5.0,
    max_clips: int = 10,
) -> dict:
    try:
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            return {"success": False, "error": f"视频文件不存在: {video_path}"}

        service = get_moe_service()
        task_id = await service.start_moe_task(
            video_path=str(video_path_obj),
            strategy=strategy,
            min_clip_duration=min_clip_duration,
            max_clips=max_clips,
        )

        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "task_type": "moe_clip",
                "video_path": str(video_path_obj),
                "strategy": strategy,
                "message": "MoE 剪辑任务已启动，请使用 get_clip_task_status 查询进度。",
            },
        }
    except Exception as exc:
        logger.error("start_moe_clip failed: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool(
    name="get_clip_task_status",
    description="查询视频剪辑异步任务状态和结果。",
    category="clip",
    input_schema_note="必须提供 start_cutclaw_clip/start_narrato_clip/start_moe_clip 返回的 task_id。",
    output_schema_note="返回 source 和 data；data 通常含 status/progress/result/output_path/片段列表，失败时含 error。",
    risk_level="read",
    output_type="clip_task_status",
)
async def get_clip_task_status(task_id: str) -> dict:
    try:
        cutclaw = get_cutclaw_service()
        status = await cutclaw.get_task_status(task_id)
        if status:
            return {"success": True, "source": "cutclaw", "data": status}
    except Exception:
        pass

    try:
        narrato = get_narrato_service()
        status = await narrato.get_task_status(task_id)
        if status:
            return {"success": True, "source": "narrato", "data": status}
    except Exception:
        pass

    try:
        moe = get_moe_service()
        status = await moe.get_task_status(task_id)
        if status:
            return {"success": True, "source": "moe", "data": status}
    except Exception:
        pass

    return {"success": False, "error": f"未找到任务: {task_id}"}
