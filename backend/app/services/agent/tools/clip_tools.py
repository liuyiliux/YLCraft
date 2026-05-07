"""
YLCraft — 剪辑工具封装

封装 CutClawAgent、NarratoService、MoEService 为 Agent 可调用的工具
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.services.agent.registry import register_tool
from app.services.clip.cutclaw_service import get_cutclaw_service, CutClawConfig
from app.services.clip.narrato_service import get_narrato_service, NarratoConfig
from app.services.clip.moe_service import get_moe_service

logger = logging.getLogger("ylcraft.agent.tools.clip")


@register_tool(
    name="start_cutclaw_clip",
    description="启动 CutClaw Agent 智能剪辑（基于 LLM 的自然语言剪辑）",
    category="clip"
)
async def start_cutclaw_clip(video_path: str, instruction: Optional[str] = None, options: Optional[dict] = None) -> dict:
    """启动 CutClaw Agent 剪辑任务"""
    try:
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            return {"success": False, "error": f"视频文件不存在: {video_path}"}

        service = get_cutclaw_service()

        # 构建配置
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

        # 启动任务
        task_id = await service.start_agent_task(
            video_path=str(video_path_obj),
            instruction=instruction or "请帮我拆出最精彩的片段，适合短视频分发",
            config=config,
            auto_cut=config.auto_cut,
        )

        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "task_type": "cutclaw_agent",
                "video_path": str(video_path_obj),
                "instruction": instruction or "请帮我拆出最精彩的片段，适合短视频分发",
                "message": "CutClaw Agent 剪辑任务已启动，请使用 get_clip_task_status 查询进度",
            }
        }
    except Exception as e:
        logger.error(f"start_cutclaw_clip failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="start_narrato_clip",
    description="启动 NarratoAI Pipeline 自动剪辑（节选卖点 + VLM 美学评分）",
    category="clip"
)
async def start_narrato_clip(
    video_path: str,
    target_duration: float = 60.0,
    num_clips: int = 5,
    output_dir: Optional[str] = None,
) -> dict:
    """启动 NarratoAI Pipeline 剪辑任务"""
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
                    "output_dir": output_dir,
                },
                "message": "NarratoAI Pipeline 剪辑任务已启动",
            }
        }
    except Exception as e:
        logger.error(f"start_narrato_clip failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="start_moe_clip",
    description="启动 MoE 多专家并行剪辑（多模型协同选出最佳片段）",
    category="clip"
)
async def start_moe_clip(
    video_path: str,
    strategy: str = "auto",
    min_clip_duration: float = 5.0,
    max_clips: int = 10,
) -> dict:
    """启动 MoE 多专家并行剪辑任务"""
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
                "message": "MoE 剪辑任务已启动",
            }
        }
    except Exception as e:
        logger.error(f"start_moe_clip failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="get_clip_task_status",
    description="查询视频剪辑任务状态和结果",
    category="clip"
)
async def get_clip_task_status(task_id: str) -> dict:
    """查询剪辑任务状态"""
    # 优先查 CutClaw
    try:
        cutclaw = get_cutclaw_service()
        status = await cutclaw.get_task_status(task_id)
        if status:
            return {"success": True, "source": "cutclaw", "data": status}
    except Exception:
        pass

    # 尝试 Narrato
    try:
        narrato = get_narrato_service()
        status = await narrato.get_task_status(task_id)
        if status:
            return {"success": True, "source": "narrato", "data": status}
    except Exception:
        pass

    # 尝试 MoE
    try:
        moe = get_moe_service()
        status = await moe.get_task_status(task_id)
        if status:
            return {"success": True, "source": "moe", "data": status}
    except Exception:
        pass

    return {"success": False, "error": f"未找到任务: {task_id}"}
